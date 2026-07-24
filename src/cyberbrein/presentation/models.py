from dataclasses import dataclass
from datetime import datetime

from shapely.geometry.base import BaseGeometry


@dataclass(frozen=True, slots=True)
class MeasurementRoundSummary:
    measurement_round_id: str
    name: str
    status: str
    started_at_utc: datetime | None
    ended_at_utc: datetime | None


@dataclass(frozen=True, slots=True)
class ZoneView:
    zone_id: str
    geometry: BaseGeometry


@dataclass(frozen=True, slots=True)
class FactorView:
    factor_type: str
    observed_value: str
    category: str
    points: int
    weight: int
    weighted_points: int


@dataclass(frozen=True, slots=True)
class FindingView:
    measurement_round_id: str
    zone_id: str
    network_id: str
    latitude: float
    longitude: float
    score: int
    score_color: str
    observation_count: int
    average_rssi_dbm: float
    strongest_rssi_dbm: int
    channel: int
    frequency_mhz: int | None
    band: str
    encryption: str
    factors: tuple[FactorView, ...]

    @property
    def signal_category(self) -> str:
        return next(
            factor.category for factor in self.factors if factor.factor_type == "signal_strength"
        )


@dataclass(frozen=True, slots=True)
class DashboardFilters:
    zone_ids: frozenset[str] = frozenset()
    bands: frozenset[str] = frozenset()
    channels: frozenset[int] = frozenset()
    encryptions: frozenset[str] = frozenset()
    score_colors: frozenset[str] = frozenset()
    signal_categories: frozenset[str] = frozenset()

    def matches(self, finding: FindingView) -> bool:
        return all(
            (
                not self.zone_ids or finding.zone_id in self.zone_ids,
                not self.bands or finding.band in self.bands,
                not self.channels or finding.channel in self.channels,
                not self.encryptions or finding.encryption in self.encryptions,
                not self.score_colors or finding.score_color in self.score_colors,
                not self.signal_categories or finding.signal_category in self.signal_categories,
            )
        )


@dataclass(frozen=True, slots=True)
class FilterOptions:
    zone_ids: tuple[str, ...]
    bands: tuple[str, ...]
    channels: tuple[int, ...]
    encryptions: tuple[str, ...]
    score_colors: tuple[str, ...]
    signal_categories: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class DashboardData:
    measurement_round: MeasurementRoundSummary
    zones: tuple[ZoneView, ...]
    findings: tuple[FindingView, ...]
    filter_options: FilterOptions

    @property
    def total_count(self) -> int:
        return len(self.findings)

    @property
    def elevated_count(self) -> int:
        return sum(finding.score_color == "YELLOW" for finding in self.findings)

    @property
    def high_count(self) -> int:
        return sum(finding.score_color == "RED" for finding in self.findings)
