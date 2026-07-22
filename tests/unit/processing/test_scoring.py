from dataclasses import replace
from datetime import datetime, timezone

import pytest

from cyberbrein.processing.models import EncryptionCategory, NetworkFinding
from cyberbrein.processing.scoring import score_network_finding


def _finding(**changes: object) -> NetworkFinding:
    observed_at = datetime(2026, 1, 1, tzinfo=timezone.utc)
    finding = NetworkFinding(
        measurement_round_id="synthetic-round",
        zone_id="zone-a",
        network_id="network-a",
        observation_count=1,
        first_observed_at_utc=observed_at,
        last_observed_at_utc=observed_at,
        representative_observed_at_utc=observed_at,
        representative_latitude=1.0,
        representative_longitude=2.0,
        representative_rssi_dbm=-80,
        representative_channel=36,
        representative_frequency_mhz=5180,
        representative_band="5GHz",
        encryption=EncryptionCategory.WPA3,
        ssid_present=False,
    )
    return replace(finding, **changes)


def test_score_is_sum_of_named_factors() -> None:
    scored = score_network_finding(
        _finding(
            observation_count=10,
            representative_rssi_dbm=-40,
            encryption=EncryptionCategory.OPEN,
            ssid_present=True,
        )
    )
    assert scored.score == 100
    assert [(factor.name, factor.points) for factor in scored.score_factors] == [
        ("encryption", 50),
        ("signal_strength", 30),
        ("ssid_present", 10),
        ("observation_count", 10),
    ]


@pytest.mark.parametrize(
    ("encryption", "points"),
    [
        (EncryptionCategory.WPA3, 0),
        (EncryptionCategory.WPA2, 10),
        (EncryptionCategory.WPA, 30),
        (EncryptionCategory.WEP, 45),
        (EncryptionCategory.OPEN, 50),
        (EncryptionCategory.UNKNOWN, 40),
    ],
)
def test_encryption_factor_is_explicit(encryption: EncryptionCategory, points: int) -> None:
    scored = score_network_finding(_finding(encryption=encryption))
    factor = next(item for item in scored.score_factors if item.name == "encryption")
    assert factor.points == points


@pytest.mark.parametrize(("rssi", "points"), [(-50, 30), (-51, 20), (-70, 20), (-71, 10)])
def test_signal_boundaries(rssi: int, points: int) -> None:
    scored = score_network_finding(_finding(representative_rssi_dbm=rssi))
    factor = next(item for item in scored.score_factors if item.name == "signal_strength")
    assert factor.points == points

