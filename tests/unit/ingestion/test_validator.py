from dataclasses import replace
from datetime import datetime, timezone

import pytest

from cyberbrein.collection.models import RawObservation
from cyberbrein.ingestion.validator import (
    INVALID_BAND,
    INVALID_CHANNEL,
    INVALID_GPS_MODE,
    INVALID_LATITUDE,
    INVALID_LONGITUDE,
    INVALID_RSSI,
    MISSING_BSSID,
    MISSING_OBSERVED_AT,
    validate_observation,
)


def _valid_observation(**changes: object) -> RawObservation:
    observation = RawObservation(
        measurement_round_id="synthetic-round-validator",
        observed_at_utc=datetime(2026, 1, 1, 12, 0, tzinfo=timezone.utc),
        bssid="02:00:00:00:00:30",
        ssid="SYNTHETIC-VALIDATOR-NETWORK",
        rssi_dbm=-50,
        channel=6,
        frequency_mhz=2437,
        band="2.4GHz",
        encryption="WPA2/802.1X",
        frame_type="BEACON",
        latitude=0.0,
        longitude=0.0,
        gps_mode=3,
        gps_accuracy_m=5.0,
    )
    return replace(observation, **changes)


def test_valid_observation_is_accepted() -> None:
    assert validate_observation(_valid_observation()) is None


@pytest.mark.parametrize("bssid", ["", "   "])
def test_bssid_is_required(bssid: str) -> None:
    assert validate_observation(_valid_observation(bssid=bssid)) == MISSING_BSSID


def test_observed_at_is_required() -> None:
    assert validate_observation(_valid_observation(observed_at_utc=None)) == MISSING_OBSERVED_AT


@pytest.mark.parametrize("rssi_dbm", [-121, 1])
def test_rssi_must_be_in_allowed_range(rssi_dbm: int) -> None:
    assert validate_observation(_valid_observation(rssi_dbm=rssi_dbm)) == INVALID_RSSI


def test_gps_mode_two_is_rejected() -> None:
    assert validate_observation(_valid_observation(gps_mode=2)) == INVALID_GPS_MODE


@pytest.mark.parametrize(
    ("changes", "expected_reason"),
    [
        ({"latitude": -91.0}, INVALID_LATITUDE),
        ({"latitude": 91.0}, INVALID_LATITUDE),
        ({"longitude": -181.0}, INVALID_LONGITUDE),
        ({"longitude": 181.0}, INVALID_LONGITUDE),
    ],
)
def test_coordinates_must_be_in_allowed_ranges(
    changes: dict[str, object],
    expected_reason: str,
) -> None:
    assert validate_observation(_valid_observation(**changes)) == expected_reason


def test_channel_must_be_positive() -> None:
    assert validate_observation(_valid_observation(channel=0)) == INVALID_CHANNEL


def test_band_must_be_supported() -> None:
    assert validate_observation(_valid_observation(band="6GHz")) == INVALID_BAND


def test_missing_gps_accuracy_is_allowed() -> None:
    assert validate_observation(_valid_observation(gps_accuracy_m=None)) is None
