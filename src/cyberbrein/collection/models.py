from dataclasses import dataclass
from datetime import datetime


@dataclass(frozen=True, slots=True)
class GpsFix:
    latitude: float
    longitude: float
    mode: int
    accuracy_m: float | None
    observed_at_utc: datetime


@dataclass(frozen=True, slots=True)
class WifiFrameMetadata:
    observed_at_utc: datetime
    bssid: str
    ssid: str | None
    rssi_dbm: int
    channel: int
    frequency_mhz: int | None
    band: str
    encryption: str
    frame_type: str


@dataclass(frozen=True, slots=True)
class RawObservation:
    measurement_round_id: str
    observed_at_utc: datetime
    bssid: str
    ssid: str | None
    rssi_dbm: int
    channel: int
    frequency_mhz: int | None
    band: str
    encryption: str
    frame_type: str
    latitude: float | None
    longitude: float | None
    gps_mode: int | None
    gps_accuracy_m: float | None
