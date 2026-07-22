import math
from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum

from shapely.geometry.base import BaseGeometry

from cyberbrein.ingestion.models import AcceptedObservation


class EncryptionCategory(StrEnum):
    OPEN = "OPEN"
    WEP = "WEP"
    WPA = "WPA"
    WPA2 = "WPA2"
    WPA3 = "WPA3"
    UNKNOWN = "UNKNOWN"


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
    max_gps_accuracy_m: float = 25.0

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
    representative_rssi_dbm: int
    representative_channel: int
    representative_frequency_mhz: int | None
    representative_band: str
    encryption: EncryptionCategory
    ssid_present: bool
