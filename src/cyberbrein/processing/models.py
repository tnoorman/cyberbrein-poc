import math
from dataclasses import dataclass
from enum import StrEnum


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

