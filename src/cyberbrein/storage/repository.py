from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any

from geoalchemy2 import Geometry
from geoalchemy2.shape import from_shape, to_shape
from shapely.geometry import MultiPolygon, Point, Polygon
from sqlalchemy import (
    Boolean,
    CheckConstraint,
    Column,
    DateTime,
    Float,
    ForeignKey,
    ForeignKeyConstraint,
    Integer,
    MetaData,
    String,
    Table,
    create_engine,
    delete,
    func,
    insert,
    select,
    text,
)
from sqlalchemy.engine import Connection, Engine, make_url

from cyberbrein.processing.models import (
    ApprovedZone,
    AttentionLevel,
    EncryptionCategory,
    NetworkFinding,
    ScoredNetworkFinding,
    ScoreFactor,
)

SRID = 4326
metadata = MetaData()

measurement_rounds = Table(
    "measurement_round",
    metadata,
    Column("measurement_round_id", String, primary_key=True),
    Column("name", String, nullable=False),
    Column("status", String, nullable=False),
    Column("started_at_utc", DateTime(timezone=True)),
    Column("ended_at_utc", DateTime(timezone=True)),
    CheckConstraint("status IN ('COMPLETED')", name="ck_measurement_round_status"),
)

zones = Table(
    "zone",
    metadata,
    Column(
        "measurement_round_id",
        String,
        ForeignKey("measurement_round.measurement_round_id", ondelete="CASCADE"),
        primary_key=True,
    ),
    Column("zone_id", String, primary_key=True),
    Column(
        "polygon",
        Geometry("MULTIPOLYGON", srid=SRID, spatial_index=True),
        nullable=False,
    ),
)

network_findings = Table(
    "network_finding",
    metadata,
    Column("measurement_round_id", String, primary_key=True),
    Column("zone_id", String, primary_key=True),
    Column("network_id", String, primary_key=True),
    Column("observation_count", Integer, nullable=False),
    Column("first_observed_at_utc", DateTime(timezone=True), nullable=False),
    Column("last_observed_at_utc", DateTime(timezone=True), nullable=False),
    Column("representative_observed_at_utc", DateTime(timezone=True), nullable=False),
    Column(
        "display_point",
        Geometry("POINT", srid=SRID, spatial_index=True),
        nullable=False,
    ),
    Column("average_rssi_dbm", Float, nullable=False),
    Column("strongest_rssi_dbm", Integer, nullable=False),
    Column("representative_channel", Integer, nullable=False),
    Column("representative_frequency_mhz", Integer),
    Column("representative_band", String, nullable=False),
    Column("encryption", String, nullable=False),
    Column("ssid_present", Boolean, nullable=False),
    ForeignKeyConstraint(
        ["measurement_round_id", "zone_id"],
        ["zone.measurement_round_id", "zone.zone_id"],
        ondelete="CASCADE",
    ),
    CheckConstraint("observation_count > 0", name="ck_network_finding_observation_count"),
)

network_scores = Table(
    "network_score",
    metadata,
    Column("measurement_round_id", String, primary_key=True),
    Column("zone_id", String, primary_key=True),
    Column("network_id", String, primary_key=True),
    Column("total_points", Integer, nullable=False),
    Column("score_color", String, nullable=False),
    ForeignKeyConstraint(
        ["measurement_round_id", "zone_id", "network_id"],
        [
            "network_finding.measurement_round_id",
            "network_finding.zone_id",
            "network_finding.network_id",
        ],
        ondelete="CASCADE",
    ),
    CheckConstraint("total_points BETWEEN 0 AND 8", name="ck_network_score_points"),
    CheckConstraint(
        "score_color IN ('GREEN', 'YELLOW', 'RED')",
        name="ck_network_score_color",
    ),
)

score_factors = Table(
    "score_factor",
    metadata,
    Column("measurement_round_id", String, primary_key=True),
    Column("zone_id", String, primary_key=True),
    Column("network_id", String, primary_key=True),
    Column("factor_type", String, primary_key=True),
    Column("position", Integer, nullable=False),
    Column("observed_value", String, nullable=False),
    Column("category", String, nullable=False),
    Column("points", Integer, nullable=False),
    Column("weight", Integer, nullable=False),
    Column("weighted_points", Integer, nullable=False),
    ForeignKeyConstraint(
        ["measurement_round_id", "zone_id", "network_id"],
        [
            "network_finding.measurement_round_id",
            "network_finding.zone_id",
            "network_finding.network_id",
        ],
        ondelete="CASCADE",
    ),
    CheckConstraint("points BETWEEN 0 AND 2", name="ck_score_factor_points"),
    CheckConstraint("weight > 0", name="ck_score_factor_weight"),
)


@dataclass(frozen=True, slots=True)
class MeasurementRoundRecordCounts:
    measurement_rounds: int
    zones: int
    network_findings: int
    network_scores: int
    score_factors: int

    @property
    def all_zero(self) -> bool:
        return not any(
            (
                self.measurement_rounds,
                self.zones,
                self.network_findings,
                self.network_scores,
                self.score_factors,
            )
        )


@dataclass(frozen=True, slots=True)
class StorageDeletionResult:
    before: MeasurementRoundRecordCounts
    after: MeasurementRoundRecordCounts


class ActiveMeasurementRoundError(RuntimeError):
    """Raised when a different retained measurement round already exists."""


class MeasurementRoundNotFoundError(RuntimeError):
    """Raised when the requested measurement round is not retained."""


class DeletionVerificationError(RuntimeError):
    """Raised when records remain after a measurement-round deletion."""


class StorageRepository:
    def __init__(self, database_url: str) -> None:
        url = make_url(database_url)
        if url.get_backend_name() != "postgresql":
            raise ValueError("processed storage requires PostgreSQL/PostGIS")
        self._engine: Engine = create_engine(database_url, pool_pre_ping=True)

    def initialize(self) -> None:
        with self._engine.begin() as connection:
            if (
                connection.execute(
                    text("SELECT 1 FROM pg_extension WHERE extname = 'postgis'")
                ).scalar_one_or_none()
                is None
            ):
                raise RuntimeError("PostGIS extension is required")
        metadata.create_all(self._engine)

    def has_retained_measurement_round(self) -> bool:
        """Return whether Storage already contains the single retained round."""
        with self._engine.connect() as connection:
            return (
                connection.execute(
                    select(measurement_rounds.c.measurement_round_id).limit(1)
                ).scalar_one_or_none()
                is not None
            )

    def replace_measurement_round(
        self,
        measurement_round_id: str,
        approved_zones: Sequence[ApprovedZone],
        findings: Sequence[ScoredNetworkFinding],
    ) -> None:
        """Atomically store one active processed round and its approved zone snapshot."""
        self._validate_round(measurement_round_id, approved_zones, findings)
        started_at, ended_at = _round_bounds(findings)
        with self._engine.begin() as connection:
            other_round = connection.execute(
                select(measurement_rounds.c.measurement_round_id)
                .where(measurement_rounds.c.measurement_round_id != measurement_round_id)
                .limit(1)
            ).scalar_one_or_none()
            if other_round is not None:
                raise ActiveMeasurementRoundError("a different active measurement round exists")

            connection.execute(
                delete(measurement_rounds).where(
                    measurement_rounds.c.measurement_round_id == measurement_round_id
                )
            )
            connection.execute(
                insert(measurement_rounds).values(
                    measurement_round_id=measurement_round_id,
                    name=measurement_round_id,
                    status="COMPLETED",
                    started_at_utc=started_at,
                    ended_at_utc=ended_at,
                )
            )
            connection.execute(
                insert(zones),
                [_zone_values(measurement_round_id, zone) for zone in approved_zones],
            )
            for scored in findings:
                connection.execute(insert(network_findings).values(_finding_values(scored)))
                connection.execute(insert(network_scores).values(_score_values(scored)))
                connection.execute(insert(score_factors), _factor_values(scored))

    def load_measurement_round(
        self,
        measurement_round_id: str,
    ) -> tuple[ScoredNetworkFinding, ...]:
        with self._engine.connect() as connection:
            rows = connection.execute(
                select(
                    network_findings, network_scores.c.total_points, network_scores.c.score_color
                )
                .join(
                    network_scores,
                    (
                        network_findings.c.measurement_round_id
                        == network_scores.c.measurement_round_id
                    )
                    & (network_findings.c.zone_id == network_scores.c.zone_id)
                    & (network_findings.c.network_id == network_scores.c.network_id),
                )
                .where(network_findings.c.measurement_round_id == measurement_round_id)
                .order_by(network_findings.c.zone_id, network_findings.c.network_id)
            ).mappings()
            loaded: list[ScoredNetworkFinding] = []
            for row in rows:
                factor_rows = connection.execute(
                    select(score_factors)
                    .where(
                        score_factors.c.measurement_round_id == measurement_round_id,
                        score_factors.c.zone_id == row["zone_id"],
                        score_factors.c.network_id == row["network_id"],
                    )
                    .order_by(score_factors.c.position)
                ).mappings()
                factors = tuple(_factor_from_row(factor) for factor in factor_rows)
                loaded.append(_scored_finding_from_row(row, factors))
            return tuple(loaded)

    def load_zones(self, measurement_round_id: str) -> tuple[ApprovedZone, ...]:
        with self._engine.connect() as connection:
            rows = connection.execute(
                select(zones)
                .where(zones.c.measurement_round_id == measurement_round_id)
                .order_by(zones.c.zone_id)
            ).mappings()
            return tuple(
                ApprovedZone(zone_id=row["zone_id"], geometry=to_shape(row["polygon"]))
                for row in rows
            )

    def delete_measurement_round(self, measurement_round_id: str) -> StorageDeletionResult:
        """Hard-delete one round and verify every related Storage table afterwards."""
        if not measurement_round_id.strip():
            raise ValueError("measurement_round_id is required")

        with self._engine.begin() as connection:
            before = _measurement_round_record_counts(connection, measurement_round_id)
            if before.measurement_rounds != 1:
                raise MeasurementRoundNotFoundError("measurement round does not exist")
            connection.execute(
                delete(measurement_rounds).where(
                    measurement_rounds.c.measurement_round_id == measurement_round_id
                )
            )

        with self._engine.connect() as connection:
            after = _measurement_round_record_counts(connection, measurement_round_id)
        if not after.all_zero:
            raise DeletionVerificationError("measurement round deletion could not be verified")
        return StorageDeletionResult(before=before, after=after)

    def close(self) -> None:
        self._engine.dispose()

    @staticmethod
    def _validate_round(
        measurement_round_id: str,
        approved_zones: Sequence[ApprovedZone],
        findings: Sequence[ScoredNetworkFinding],
    ) -> None:
        if not measurement_round_id.strip():
            raise ValueError("measurement_round_id is required")
        if not approved_zones:
            raise ValueError("at least one approved zone is required")
        zone_ids = [zone.zone_id for zone in approved_zones]
        if len(zone_ids) != len(set(zone_ids)):
            raise ValueError("approved zone IDs must be unique")
        approved_zone_ids = set(zone_ids)
        keys: set[tuple[str, str]] = set()
        for scored in findings:
            finding = scored.finding
            if finding.measurement_round_id != measurement_round_id:
                raise ValueError("all findings must belong to the requested measurement round")
            if finding.zone_id not in approved_zone_ids:
                raise ValueError("every finding must reference an approved zone")
            key = (finding.zone_id, finding.network_id)
            if key in keys:
                raise ValueError("findings must have unique zone and network keys")
            keys.add(key)


def _round_bounds(
    findings: Sequence[ScoredNetworkFinding],
) -> tuple[datetime | None, datetime | None]:
    if not findings:
        return None, None
    return (
        min(item.finding.first_observed_at_utc for item in findings),
        max(item.finding.last_observed_at_utc for item in findings),
    )


def _measurement_round_record_counts(
    connection: Connection,
    measurement_round_id: str,
) -> MeasurementRoundRecordCounts:
    def count(table: Table) -> int:
        return connection.execute(
            select(func.count())
            .select_from(table)
            .where(table.c.measurement_round_id == measurement_round_id)
        ).scalar_one()

    return MeasurementRoundRecordCounts(
        measurement_rounds=count(measurement_rounds),
        zones=count(zones),
        network_findings=count(network_findings),
        network_scores=count(network_scores),
        score_factors=count(score_factors),
    )


def _zone_values(measurement_round_id: str, zone: ApprovedZone) -> dict[str, object]:
    polygon = zone.geometry
    if isinstance(polygon, Polygon):
        polygon = MultiPolygon([polygon])
    return {
        "measurement_round_id": measurement_round_id,
        "zone_id": zone.zone_id,
        "polygon": from_shape(polygon, srid=SRID),
    }


def _finding_values(scored: ScoredNetworkFinding) -> dict[str, object]:
    finding = scored.finding
    return {
        "measurement_round_id": finding.measurement_round_id,
        "zone_id": finding.zone_id,
        "network_id": finding.network_id,
        "observation_count": finding.observation_count,
        "first_observed_at_utc": finding.first_observed_at_utc,
        "last_observed_at_utc": finding.last_observed_at_utc,
        "representative_observed_at_utc": finding.representative_observed_at_utc,
        "display_point": from_shape(
            Point(finding.representative_longitude, finding.representative_latitude),
            srid=SRID,
        ),
        "average_rssi_dbm": finding.average_rssi_dbm,
        "strongest_rssi_dbm": finding.strongest_rssi_dbm,
        "representative_channel": finding.representative_channel,
        "representative_frequency_mhz": finding.representative_frequency_mhz,
        "representative_band": finding.representative_band,
        "encryption": finding.encryption.value,
        "ssid_present": finding.ssid_present,
    }


def _score_values(scored: ScoredNetworkFinding) -> dict[str, object]:
    finding = scored.finding
    return {
        "measurement_round_id": finding.measurement_round_id,
        "zone_id": finding.zone_id,
        "network_id": finding.network_id,
        "total_points": scored.score,
        "score_color": scored.attention_level.value,
    }


def _factor_values(scored: ScoredNetworkFinding) -> list[dict[str, object]]:
    finding = scored.finding
    return [
        {
            "measurement_round_id": finding.measurement_round_id,
            "zone_id": finding.zone_id,
            "network_id": finding.network_id,
            "factor_type": factor.name,
            "position": position,
            "observed_value": factor.observed_value,
            "category": factor.category,
            "points": factor.contribution,
            "weight": factor.weight,
            "weighted_points": factor.weighted_points,
        }
        for position, factor in enumerate(scored.score_factors)
    ]


def _factor_from_row(row: Mapping[str, Any]) -> ScoreFactor:
    return ScoreFactor(
        name=row["factor_type"],
        observed_value=row["observed_value"],
        category=row["category"],
        contribution=row["points"],
        weight=row["weight"],
    )


def _scored_finding_from_row(
    row: Mapping[str, Any],
    factors: tuple[ScoreFactor, ...],
) -> ScoredNetworkFinding:
    display_point = to_shape(row["display_point"])
    finding = NetworkFinding(
        measurement_round_id=row["measurement_round_id"],
        zone_id=row["zone_id"],
        network_id=row["network_id"],
        observation_count=row["observation_count"],
        first_observed_at_utc=_as_utc(row["first_observed_at_utc"]),
        last_observed_at_utc=_as_utc(row["last_observed_at_utc"]),
        representative_observed_at_utc=_as_utc(row["representative_observed_at_utc"]),
        representative_latitude=display_point.y,
        representative_longitude=display_point.x,
        average_rssi_dbm=row["average_rssi_dbm"],
        strongest_rssi_dbm=row["strongest_rssi_dbm"],
        representative_channel=row["representative_channel"],
        representative_frequency_mhz=row["representative_frequency_mhz"],
        representative_band=row["representative_band"],
        encryption=EncryptionCategory(row["encryption"]),
        ssid_present=row["ssid_present"],
    )
    return ScoredNetworkFinding(
        finding=finding,
        score=row["total_points"],
        attention_level=AttentionLevel(row["score_color"]),
        score_factors=factors,
    )


def _as_utc(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc)
