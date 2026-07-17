from datetime import datetime

from cyberbrein.collection.models import RawObservation

MISSING_BSSID = "missing_bssid"
MISSING_OBSERVED_AT = "missing_observed_at_utc"
INVALID_RSSI = "invalid_rssi"
INVALID_LATITUDE = "invalid_latitude"
INVALID_LONGITUDE = "invalid_longitude"
INVALID_GPS_MODE = "invalid_gps_mode"
INVALID_CHANNEL = "invalid_channel"
INVALID_BAND = "invalid_band"

ALLOWED_BANDS = {"2.4GHz", "5GHz"}


def _is_number(value: object) -> bool:
    return isinstance(value, (int, float)) and not isinstance(value, bool)


def validate_observation(observation: RawObservation) -> str | None:
    """Return one safe rejection category, or None when the observation is valid."""
    if not isinstance(observation.bssid, str) or not observation.bssid.strip():
        return MISSING_BSSID
    if not isinstance(observation.observed_at_utc, datetime):
        return MISSING_OBSERVED_AT
    if (
        not isinstance(observation.rssi_dbm, int)
        or isinstance(observation.rssi_dbm, bool)
        or not -120 <= observation.rssi_dbm <= 0
    ):
        return INVALID_RSSI
    if not _is_number(observation.latitude) or not -90 <= observation.latitude <= 90:
        return INVALID_LATITUDE
    if not _is_number(observation.longitude) or not -180 <= observation.longitude <= 180:
        return INVALID_LONGITUDE
    if (
        not isinstance(observation.gps_mode, int)
        or isinstance(observation.gps_mode, bool)
        or observation.gps_mode < 3
    ):
        return INVALID_GPS_MODE
    if (
        not isinstance(observation.channel, int)
        or isinstance(observation.channel, bool)
        or observation.channel <= 0
    ):
        return INVALID_CHANNEL
    if observation.band not in ALLOWED_BANDS:
        return INVALID_BAND
    return None
