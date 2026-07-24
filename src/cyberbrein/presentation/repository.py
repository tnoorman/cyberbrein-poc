from collections import defaultdict
from datetime import datetime, timezone
from typing import Any

from geoalchemy2.shape import to_shape
from sqlalchemy import create_engine, select
from sqlalchemy.engine import Engine, make_url

from cyberbrein.storage.repository import (
    measurement_rounds,
    network_findings,
    network_scores,
    score_factors,
    zones,
)

from .models import (
    DashboardData,
    DashboardFilters,
    FactorView,
    FilterOptions,
    FindingView,
    MeasurementRoundSummary,
    ZoneView,
)


class PresentationRepository:
    """Read-only query boundary between PostGIS Storage and Presentation."""

    def __init__(self, database_url: str) -> None:
        if make_url(database_url).get_backend_name() != "postgresql":
            raise ValueError("presentation requires PostgreSQL/PostGIS")
        self._engine: Engine = create_engine(database_url, pool_pre_ping=True)

    def list_measurement_rounds(self) -> tuple[MeasurementRoundSummary, ...]:
        with self._engine.connect() as connection:
            rows = connection.execute(
                select(measurement_rounds).order_by(
                    measurement_rounds.c.started_at_utc.desc().nullslast(),
                    measurement_rounds.c.measurement_round_id,
                )
            ).mappings()
            return tuple(_round_from_row(row) for row in rows)

    def load_dashboard(
        self,
        measurement_round_id: str,
        filters: DashboardFilters | None = None,
    ) -> DashboardData:
        filters = filters or DashboardFilters()
        with self._engine.connect() as connection:
            round_row = (
                connection.execute(
                    select(measurement_rounds).where(
                        measurement_rounds.c.measurement_round_id == measurement_round_id
                    )
                )
                .mappings()
                .one()
            )
            zone_rows = tuple(
                connection.execute(
                    select(zones)
                    .where(zones.c.measurement_round_id == measurement_round_id)
                    .order_by(zones.c.zone_id)
                ).mappings()
            )
            finding_rows = tuple(
                connection.execute(
                    select(
                        network_findings,
                        network_scores.c.total_points,
                        network_scores.c.score_color,
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
            )
            factor_rows = tuple(
                connection.execute(
                    select(score_factors)
                    .where(score_factors.c.measurement_round_id == measurement_round_id)
                    .order_by(
                        score_factors.c.zone_id,
                        score_factors.c.network_id,
                        score_factors.c.position,
                    )
                ).mappings()
            )

        factors_by_finding: dict[tuple[str, str], list[FactorView]] = defaultdict(list)
        for row in factor_rows:
            factors_by_finding[(row["zone_id"], row["network_id"])].append(
                FactorView(
                    factor_type=row["factor_type"],
                    observed_value=row["observed_value"],
                    category=row["category"],
                    points=row["points"],
                    weight=row["weight"],
                    weighted_points=row["weighted_points"],
                )
            )
        all_findings = tuple(
            _finding_from_row(
                row,
                tuple(factors_by_finding[(row["zone_id"], row["network_id"])]),
            )
            for row in finding_rows
        )
        selected_zone_ids = filters.zone_ids
        zone_views = tuple(
            ZoneView(row["zone_id"], to_shape(row["polygon"]))
            for row in zone_rows
            if not selected_zone_ids or row["zone_id"] in selected_zone_ids
        )
        return DashboardData(
            measurement_round=_round_from_row(round_row),
            zones=zone_views,
            findings=tuple(finding for finding in all_findings if filters.matches(finding)),
            filter_options=_filter_options(zone_rows, all_findings),
        )

    def close(self) -> None:
        self._engine.dispose()


def _round_from_row(row: Any) -> MeasurementRoundSummary:
    return MeasurementRoundSummary(
        measurement_round_id=row["measurement_round_id"],
        name=row["name"],
        status=row["status"],
        started_at_utc=_optional_utc(row["started_at_utc"]),
        ended_at_utc=_optional_utc(row["ended_at_utc"]),
    )


def _finding_from_row(row: Any, factors: tuple[FactorView, ...]) -> FindingView:
    point = to_shape(row["display_point"])
    return FindingView(
        measurement_round_id=row["measurement_round_id"],
        zone_id=row["zone_id"],
        network_id=row["network_id"],
        latitude=point.y,
        longitude=point.x,
        score=row["total_points"],
        score_color=row["score_color"],
        observation_count=row["observation_count"],
        average_rssi_dbm=row["average_rssi_dbm"],
        strongest_rssi_dbm=row["strongest_rssi_dbm"],
        channel=row["representative_channel"],
        frequency_mhz=row["representative_frequency_mhz"],
        band=row["representative_band"],
        encryption=row["encryption"],
        factors=factors,
    )


def _filter_options(zone_rows: tuple[Any, ...], findings: tuple[FindingView, ...]) -> FilterOptions:
    return FilterOptions(
        zone_ids=tuple(row["zone_id"] for row in zone_rows),
        bands=tuple(sorted({finding.band for finding in findings})),
        channels=tuple(sorted({finding.channel for finding in findings})),
        encryptions=tuple(sorted({finding.encryption for finding in findings})),
        score_colors=tuple(
            color
            for color in ("GREEN", "YELLOW", "RED")
            if any(finding.score_color == color for finding in findings)
        ),
        signal_categories=tuple(
            category
            for category in ("weak", "medium", "strong")
            if any(finding.signal_category == category for finding in findings)
        ),
    )


def _optional_utc(value: datetime | None) -> datetime | None:
    if value is None:
        return None
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc)
