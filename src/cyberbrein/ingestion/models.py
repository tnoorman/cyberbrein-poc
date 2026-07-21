from dataclasses import dataclass
from datetime import datetime


@dataclass(frozen=True, slots=True)
class AcceptedObservation:
    measurement_round_id: str
    observed_at_utc: datetime
    network_id: str
    ssid_present: bool
    rssi_dbm: int
    channel: int
    frequency_mhz: int | None
    band: str
    encryption: str
    latitude: float
    longitude: float
    gps_mode: int
    gps_accuracy_m: float | None


@dataclass(frozen=True, slots=True)
class IngestionResult:
    accepted: tuple[AcceptedObservation, ...]
    accepted_count: int
    rejected_count: int
    rejection_reasons: dict[str, int]
