from dataclasses import replace
from datetime import datetime, timezone

import pytest

from cyberbrein.processing.models import AttentionLevel, EncryptionCategory, NetworkFinding
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
        representative_rssi_dbm=-81,
        representative_channel=36,
        representative_frequency_mhz=5180,
        representative_band="5GHz",
        encryption=EncryptionCategory.WPA3,
        ssid_present=False,
    )
    return replace(finding, **changes)


def test_maximum_score_is_sum_of_three_report_factors() -> None:
    scored = score_network_finding(
        _finding(
            observation_count=10,
            representative_rssi_dbm=-66,
            encryption=EncryptionCategory.OPEN,
        )
    )

    assert scored.score == 8
    assert scored.attention_level is AttentionLevel.RED
    assert [
        (factor.name, factor.contribution, factor.weight, factor.weighted_points)
        for factor in scored.score_factors
    ] == [
        ("signal_strength", 2, 1, 2),
        ("encryption", 2, 2, 4),
        ("observation_frequency", 2, 1, 2),
    ]


@pytest.mark.parametrize(
    ("encryption", "contribution"),
    [
        (EncryptionCategory.WPA3, 0),
        (EncryptionCategory.WPA2, 0),
        (EncryptionCategory.ENTERPRISE, 0),
        (EncryptionCategory.OUTDATED, 1),
        (EncryptionCategory.UNKNOWN, 1),
        (EncryptionCategory.OPEN, 2),
    ],
)
def test_encryption_contribution_matches_report(
    encryption: EncryptionCategory,
    contribution: int,
) -> None:
    scored = score_network_finding(_finding(encryption=encryption))
    factor = next(item for item in scored.score_factors if item.name == "encryption")
    assert factor.contribution == contribution
    assert factor.weight == 2
    assert factor.weighted_points == contribution * 2


@pytest.mark.parametrize(
    ("rssi", "contribution"),
    [(-81, 0), (-80, 1), (-67, 1), (-66, 2)],
)
def test_signal_boundaries_match_report(rssi: int, contribution: int) -> None:
    scored = score_network_finding(_finding(representative_rssi_dbm=rssi))
    factor = next(item for item in scored.score_factors if item.name == "signal_strength")
    assert factor.contribution == contribution
    assert factor.weight == 1


@pytest.mark.parametrize(
    ("count", "contribution"),
    [(1, 0), (2, 1), (9, 1), (10, 2), (300, 2)],
)
def test_frequency_boundaries_are_bounded(count: int, contribution: int) -> None:
    scored = score_network_finding(_finding(observation_count=count))
    factor = next(item for item in scored.score_factors if item.name == "observation_frequency")
    assert factor.contribution == contribution
    assert factor.weight == 1


def test_frequency_rejects_impossible_observation_count() -> None:
    with pytest.raises(ValueError, match="observation_count"):
        score_network_finding(_finding(observation_count=0))


@pytest.mark.parametrize(
    ("expected_score", "expected_level"),
    [
        (0, AttentionLevel.GREEN),
        (2, AttentionLevel.GREEN),
        (3, AttentionLevel.YELLOW),
        (5, AttentionLevel.YELLOW),
        (6, AttentionLevel.RED),
        (8, AttentionLevel.RED),
    ],
)
def test_attention_boundaries(expected_score: int, expected_level: AttentionLevel) -> None:
    examples = {
        0: _finding(),
        2: _finding(encryption=EncryptionCategory.OUTDATED),
        3: _finding(
            representative_rssi_dbm=-80,
            encryption=EncryptionCategory.OUTDATED,
        ),
        5: _finding(
            representative_rssi_dbm=-66,
            encryption=EncryptionCategory.OUTDATED,
            observation_count=2,
        ),
        6: _finding(
            encryption=EncryptionCategory.OPEN,
            observation_count=10,
        ),
        8: _finding(
            representative_rssi_dbm=-66,
            encryption=EncryptionCategory.OPEN,
            observation_count=10,
        ),
    }
    scored = score_network_finding(examples[expected_score])
    assert scored.score == expected_score
    assert scored.attention_level is expected_level
