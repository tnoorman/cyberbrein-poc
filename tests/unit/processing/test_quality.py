from dataclasses import replace
from datetime import datetime, timezone

import pytest

from cyberbrein.ingestion.models import AcceptedObservation
from cyberbrein.processing.models import ProcessingPolicy, ProcessingRejectionReason
from cyberbrein.processing.quality import validate_processing_quality


def _observation(**changes: object) -> AcceptedObservation:
    observation = AcceptedObservation(
        measurement_round_id="synthetic-round",
        observed_at_utc=datetime(2026, 1, 1, 12, 0, tzinfo=timezone.utc),
        network_id="synthetic-network-id",
        ssid_present=True,
        rssi_dbm=-50,
        channel=36,
        frequency_mhz=5180,
        band="5GHz",
        encryption="WPA2/PSK",
        latitude=0.0,
        longitude=0.0,
        gps_mode=3,
        gps_accuracy_m=4.0,
    )
    return replace(observation, **changes)


@pytest.mark.parametrize(
    ("changes", "reason"),
    [
        ({"frequency_mhz": 0}, ProcessingRejectionReason.INVALID_FREQUENCY),
        ({"frequency_mhz": 5900}, ProcessingRejectionReason.INVALID_FREQUENCY),
        (
            {"frequency_mhz": 2412, "band": "5GHz"},
            ProcessingRejectionReason.FREQUENCY_BAND_MISMATCH,
        ),
        ({"gps_mode": 2}, ProcessingRejectionReason.INVALID_GPS_MODE),
        ({"gps_accuracy_m": None}, ProcessingRejectionReason.MISSING_GPS_ACCURACY),
        ({"gps_accuracy_m": -1.0}, ProcessingRejectionReason.INVALID_GPS_ACCURACY),
        ({"gps_accuracy_m": float("inf")}, ProcessingRejectionReason.INVALID_GPS_ACCURACY),
        ({"gps_accuracy_m": 25.1}, ProcessingRejectionReason.GPS_ACCURACY_EXCEEDED),
    ],
)
def test_quality_rejections(
    changes: dict[str, object],
    reason: ProcessingRejectionReason,
) -> None:
    assert validate_processing_quality(_observation(**changes), ProcessingPolicy()) is reason


@pytest.mark.parametrize(
    "changes",
    [
        {},
        {"frequency_mhz": None},
        {"frequency_mhz": 2412, "band": "2.4GHz", "channel": 1},
        {"gps_accuracy_m": 25.0},
    ],
)
def test_quality_accepts_supported_observations(changes: dict[str, object]) -> None:
    assert validate_processing_quality(_observation(**changes), ProcessingPolicy()) is None


@pytest.mark.parametrize("value", [-1.0, float("inf"), True, "25"])
def test_policy_rejects_invalid_accuracy_limit(value: object) -> None:
    with pytest.raises(ValueError, match="max_gps_accuracy_m"):
        ProcessingPolicy(max_gps_accuracy_m=value)  # type: ignore[arg-type]
