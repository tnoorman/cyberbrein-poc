import os
from collections.abc import Mapping, Sequence
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from sqlalchemy import (
    Boolean,
    Column,
    Float,
    ForeignKey,
    ForeignKeyConstraint,
    Integer,
    MetaData,
    String,
    Table,
    create_engine,
    delete,
    insert,
    select,
)
from sqlalchemy.engine import Engine, make_url

from cyberbrein.processing.models import (
    AttentionLevel,
    EncryptionCategory,
    NetworkFinding,
    ScoredNetworkFinding,
    ScoreFactor,
)

metadata = MetaData()

measurement_rounds = Table(
    "measurement_rounds",
    metadata,
    Column("measurement_round_id", String, primary_key=True),
)

network_findings = Table(
    "network_findings",
    metadata,
    Column(
        "measurement_round_id",
        String,
        ForeignKey("measurement_rounds.measurement_round_id"),
        primary_key=True,
    ),
    Column("zone_id", String, primary_key=True),
    Column("network_id", String, primary_key=True),
    Column("observation_count", Integer, nullable=False),
    Column("first_observed_at_utc", String, nullable=False),
    Column("last_observed_at_utc", String, nullable=False),
    Column("representative_observed_at_utc", String, nullable=False),
    Column("representative_latitude", Float, nullable=False),
    Column("representative_longitude", Float, nullable=False),
    Column("average_rssi_dbm", Float, nullable=False),
    Column("strongest_rssi_dbm", Integer, nullable=False),
    Column("representative_channel", Integer, nullable=False),
    Column("representative_frequency_mhz", Integer),
    Column("representative_band", String, nullable=False),
    Column("encryption", String, nullable=False),
    Column("ssid_present", Boolean, nullable=False),
    Column("score", Integer, nullable=False),
    Column("attention_level", String, nullable=False),
)

score_factors = Table(
    "score_factors",
    metadata,
    Column("measurement_round_id", String, primary_key=True),
    Column("zone_id", String, primary_key=True),
    Column("network_id", String, primary_key=True),
    Column("name", String, primary_key=True),
    Column("position", Integer, nullable=False),
    Column("observed_value", String, nullable=False),
    Column("category", String, nullable=False),
    Column("contribution", Integer, nullable=False),
    Column("weight", Integer, nullable=False),
    Column("weighted_points", Integer, nullable=False),
    ForeignKeyConstraint(
        ["measurement_round_id", "zone_id", "network_id"],
        [
            "network_findings.measurement_round_id",
            "network_findings.zone_id",
            "network_findings.network_id",
        ],
    ),
)


class StorageRepository:
    def __init__(self, database_url: str) -> None:
        self._database_url = database_url
        self._engine: Engine = create_engine(database_url)

    def initialize(self) -> None:
        metadata.create_all(self._engine)
        self._restrict_sqlite_file()

    def replace_measurement_round(
        self,
        measurement_round_id: str,
        findings: Sequence[ScoredNetworkFinding],
    ) -> None:
        """Atomically replace all processed findings belonging to one measurement round."""
        self._validate_round(measurement_round_id, findings)
        with self._engine.begin() as connection:
            connection.execute(
                delete(score_factors).where(
                    score_factors.c.measurement_round_id == measurement_round_id
                )
            )
            connection.execute(
                delete(network_findings).where(
                    network_findings.c.measurement_round_id == measurement_round_id
                )
            )
            connection.execute(
                delete(measurement_rounds).where(
                    measurement_rounds.c.measurement_round_id == measurement_round_id
                )
            )
            connection.execute(
                insert(measurement_rounds).values(measurement_round_id=measurement_round_id)
            )
            for scored in findings:
                connection.execute(insert(network_findings).values(_finding_values(scored)))
                factor_rows = _factor_values(scored)
                if factor_rows:
                    connection.execute(insert(score_factors), factor_rows)

    def load_measurement_round(
        self,
        measurement_round_id: str,
    ) -> tuple[ScoredNetworkFinding, ...]:
        with self._engine.connect() as connection:
            finding_rows = connection.execute(
                select(network_findings)
                .where(network_findings.c.measurement_round_id == measurement_round_id)
                .order_by(network_findings.c.zone_id, network_findings.c.network_id)
            ).mappings()
            loaded: list[ScoredNetworkFinding] = []
            for row in finding_rows:
                factor_rows = connection.execute(
                    select(score_factors)
                    .where(
                        score_factors.c.measurement_round_id == measurement_round_id,
                        score_factors.c.zone_id == row["zone_id"],
                        score_factors.c.network_id == row["network_id"],
                    )
                    .order_by(score_factors.c.position)
                ).mappings()
                factors = tuple(
                    ScoreFactor(
                        name=factor["name"],
                        observed_value=factor["observed_value"],
                        category=factor["category"],
                        contribution=factor["contribution"],
                        weight=factor["weight"],
                    )
                    for factor in factor_rows
                )
                loaded.append(_scored_finding_from_row(row, factors))
            return tuple(loaded)

    def close(self) -> None:
        self._engine.dispose()

    def _restrict_sqlite_file(self) -> None:
        url = make_url(self._database_url)
        if url.get_backend_name() != "sqlite" or not url.database or url.database == ":memory:":
            return
        os.chmod(Path(url.database), 0o600)

    @staticmethod
    def _validate_round(
        measurement_round_id: str,
        findings: Sequence[ScoredNetworkFinding],
    ) -> None:
        if not measurement_round_id.strip():
            raise ValueError("measurement_round_id is required")
        keys: set[tuple[str, str]] = set()
        for scored in findings:
            finding = scored.finding
            if finding.measurement_round_id != measurement_round_id:
                raise ValueError("all findings must belong to the requested measurement round")
            key = (finding.zone_id, finding.network_id)
            if key in keys:
                raise ValueError("findings must have unique zone and network keys")
            keys.add(key)
            factor_names = [factor.name for factor in scored.score_factors]
            if len(factor_names) != len(set(factor_names)):
                raise ValueError("score factor names must be unique per finding")


def _finding_values(scored: ScoredNetworkFinding) -> dict[str, object]:
    finding = scored.finding
    return {
        "measurement_round_id": finding.measurement_round_id,
        "zone_id": finding.zone_id,
        "network_id": finding.network_id,
        "observation_count": finding.observation_count,
        "first_observed_at_utc": finding.first_observed_at_utc.isoformat(),
        "last_observed_at_utc": finding.last_observed_at_utc.isoformat(),
        "representative_observed_at_utc": finding.representative_observed_at_utc.isoformat(),
        "representative_latitude": finding.representative_latitude,
        "representative_longitude": finding.representative_longitude,
        "average_rssi_dbm": finding.average_rssi_dbm,
        "strongest_rssi_dbm": finding.strongest_rssi_dbm,
        "representative_channel": finding.representative_channel,
        "representative_frequency_mhz": finding.representative_frequency_mhz,
        "representative_band": finding.representative_band,
        "encryption": finding.encryption.value,
        "ssid_present": finding.ssid_present,
        "score": scored.score,
        "attention_level": scored.attention_level.value,
    }


def _factor_values(scored: ScoredNetworkFinding) -> list[dict[str, object]]:
    finding = scored.finding
    return [
        {
            "measurement_round_id": finding.measurement_round_id,
            "zone_id": finding.zone_id,
            "network_id": finding.network_id,
            "name": factor.name,
            "position": position,
            "observed_value": factor.observed_value,
            "category": factor.category,
            "contribution": factor.contribution,
            "weight": factor.weight,
            "weighted_points": factor.weighted_points,
        }
        for position, factor in enumerate(scored.score_factors)
    ]


def _scored_finding_from_row(
    row: Mapping[str, Any],
    factors: tuple[ScoreFactor, ...],
) -> ScoredNetworkFinding:
    finding = NetworkFinding(
        measurement_round_id=row["measurement_round_id"],
        zone_id=row["zone_id"],
        network_id=row["network_id"],
        observation_count=row["observation_count"],
        first_observed_at_utc=_parse_datetime(row["first_observed_at_utc"]),
        last_observed_at_utc=_parse_datetime(row["last_observed_at_utc"]),
        representative_observed_at_utc=_parse_datetime(row["representative_observed_at_utc"]),
        representative_latitude=row["representative_latitude"],
        representative_longitude=row["representative_longitude"],
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
        score=row["score"],
        attention_level=AttentionLevel(row["attention_level"]),
        score_factors=factors,
    )


def _parse_datetime(value: str) -> datetime:
    parsed = datetime.fromisoformat(value)
    if parsed.tzinfo is None:
        return parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)
