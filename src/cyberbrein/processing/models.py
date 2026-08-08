import math
from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum

from shapely.geometry.base import BaseGeometry

from cyberbrein.ingestion.models import AcceptedObservation


class EncryptionCategory(StrEnum):
    OPEN = "OPEN"
    OUTDATED = "OUTDATED"
    WPA2 = "WPA2"
    WPA2_OR_WPA3 = "WPA2_OR_WPA3"
    WPA3 = "WPA3"
    ENTERPRISE = "ENTERPRISE"
    UNKNOWN = "UNKNOWN"


class AttentionLevel(StrEnum):
    GREEN = "GREEN"
    YELLOW = "YELLOW"
    RED = "RED"


class ProcessingRejectionReason(StrEnum):
    INVALID_FREQUENCY = "invalid_frequency"
    FREQUENCY_BAND_MISMATCH = "frequency_band_mismatch"
    INVALID_GPS_MODE = "invalid_gps_mode"
    MISSING_GPS_ACCURACY = "missing_gps_accuracy"
    INVALID_GPS_ACCURACY = "invalid_gps_accuracy"
    GPS_ACCURACY_EXCEEDED = "gps_accuracy_exceeded"
    OUTSIDE_APPROVED_ZONE = "outside_approved_zone"
    AMBIGUOUS_ZONE = "ambiguous_zone"


@dataclass(frozen=True, slots=True)
class ProcessingPolicy:
    max_gps_accuracy_m: float = 15.0

    def __post_init__(self) -> None:
        if (
            isinstance(self.max_gps_accuracy_m, bool)
            or not isinstance(self.max_gps_accuracy_m, (int, float))
            or not math.isfinite(self.max_gps_accuracy_m)
            or self.max_gps_accuracy_m < 0
        ):
            raise ValueError("max_gps_accuracy_m must be a finite non-negative number")


@dataclass(frozen=True, slots=True)
class ApprovedZone:
    zone_id: str
    geometry: BaseGeometry

    def __post_init__(self) -> None:
        if not self.zone_id.strip():
            raise ValueError("zone_id is required")
        if self.geometry.is_empty or not self.geometry.is_valid:
            raise ValueError("zone geometry must be non-empty and valid")
        if self.geometry.geom_type not in {"Polygon", "MultiPolygon"}:
            raise ValueError("zone geometry must be a polygon or multipolygon")


@dataclass(frozen=True, slots=True)
class ZoneMatch:
    zone_id: str | None = None
    rejection_reason: ProcessingRejectionReason | None = None

    def __post_init__(self) -> None:
        if (self.zone_id is None) == (self.rejection_reason is None):
            raise ValueError("zone match must contain exactly one outcome")


@dataclass(frozen=True, slots=True)
class ZonedObservation:
    observation: AcceptedObservation
    zone_id: str
    encryption: EncryptionCategory


@dataclass(frozen=True, slots=True)
class NetworkFinding:
    measurement_round_id: str
    zone_id: str
    network_id: str
    observation_count: int
    first_observed_at_utc: datetime
    last_observed_at_utc: datetime
    representative_observed_at_utc: datetime
    representative_latitude: float
    representative_longitude: float
    average_rssi_dbm: float
    strongest_rssi_dbm: int
    representative_channel: int
    representative_frequency_mhz: int | None
    representative_band: str
    encryption: EncryptionCategory
    ssid_present: bool


@dataclass(frozen=True, slots=True)
class ScoreFactor:
    name: str
    observed_value: str
    category: str
    contribution: int
    weight: int

    def __post_init__(self) -> None:
        if not self.name.strip():
            raise ValueError("score factor name is required")
        if not self.observed_value.strip():
            raise ValueError("score factor observed value is required")
        if not self.category.strip():
            raise ValueError("score factor category is required")
        if (
            not isinstance(self.contribution, int)
            or isinstance(self.contribution, bool)
            or self.contribution not in {0, 1, 2}
        ):
            raise ValueError("score factor contribution must be 0, 1, or 2")
        if not isinstance(self.weight, int) or isinstance(self.weight, bool) or self.weight <= 0:
            raise ValueError("score factor weight must be positive")

    @property
    def weighted_points(self) -> int:
        return self.contribution * self.weight


@dataclass(frozen=True, slots=True)
class ScoredNetworkFinding:
    finding: NetworkFinding
    score: int
    attention_level: AttentionLevel
    score_factors: tuple[ScoreFactor, ...]

    def __post_init__(self) -> None:
        factor_names = {factor.name for factor in self.score_factors}
        if len(self.score_factors) != 3 or factor_names != {
            "signal_strength",
            "encryption",
            "observation_frequency",
        }:
            raise ValueError("exactly the three report-defined score factors are required")
        if not 0 <= self.score <= 8:
            raise ValueError("score must be between 0 and 8")
        if self.score != sum(factor.weighted_points for factor in self.score_factors):
            raise ValueError("score must equal the sum of its factors")
        if self.attention_level is not attention_level_for_score(self.score):
            raise ValueError("attention level must match the score")


def attention_level_for_score(score: int) -> AttentionLevel:
    if 0 <= score <= 2:
        return AttentionLevel.GREEN
    if score <= 5:
        return AttentionLevel.YELLOW
    if score <= 8:
        return AttentionLevel.RED
    raise ValueError("score must be between 0 and 8")


@dataclass(frozen=True, slots=True)
class ProcessingResult:
    findings: tuple[ScoredNetworkFinding, ...]
    input_observation_count: int
    accepted_observation_count: int
    rejected_observation_count: int
    rejection_reasons: dict[str, int]

    def __post_init__(self) -> None:
        if self.input_observation_count != (
            self.accepted_observation_count + self.rejected_observation_count
        ):
            raise ValueError("processing counts must add up")
