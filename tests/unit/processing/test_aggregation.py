from dataclasses import replace
from datetime import datetime, timedelta, timezone

from cyberbrein.ingestion.models import AcceptedObservation
from cyberbrein.processing.aggregation import aggregate_network_findings
from cyberbrein.processing.models import EncryptionCategory, ZonedObservation

OBSERVED_AT = datetime(2026, 1, 1, 12, 0, tzinfo=timezone.utc)


def _observation(**changes: object) -> AcceptedObservation:
    observation = AcceptedObservation(
        measurement_round_id="synthetic-round",
        observed_at_utc=OBSERVED_AT,
        network_id="network-a",
        ssid_present=False,
        rssi_dbm=-70,
        channel=1,
        frequency_mhz=2412,
        band="2.4GHz",
        encryption="WPA2",
        latitude=1.0,
        longitude=2.0,
        gps_mode=3,
        gps_accuracy_m=2.0,
    )
    return replace(observation, **changes)


def _zoned(
    observation: AcceptedObservation,
    zone_id: str = "zone-a",
    encryption: EncryptionCategory = EncryptionCategory.WPA2,
) -> ZonedObservation:
    return ZonedObservation(observation, zone_id, encryption)


def test_strongest_observation_supplies_one_consistent_representative_measurement() -> None:
    weaker = _observation()
    stronger = _observation(
        observed_at_utc=OBSERVED_AT + timedelta(seconds=1),
        rssi_dbm=-40,
        channel=36,
        frequency_mhz=5180,
        band="5GHz",
        latitude=3.0,
        longitude=4.0,
        ssid_present=True,
    )

    finding = aggregate_network_findings([_zoned(weaker), _zoned(stronger)])[0]

    assert finding.observation_count == 2
    assert finding.representative_rssi_dbm == -40
    assert finding.representative_channel == 36
    assert finding.representative_frequency_mhz == 5180
    assert finding.representative_band == "5GHz"
    assert finding.representative_latitude == 3.0
    assert finding.representative_longitude == 4.0
    assert finding.ssid_present is True


def test_weakest_encryption_is_retained_conservatively() -> None:
    finding = aggregate_network_findings(
        [
            _zoned(_observation(), encryption=EncryptionCategory.WPA3),
            _zoned(_observation(), encryption=EncryptionCategory.OUTDATED),
        ]
    )[0]
    assert finding.encryption is EncryptionCategory.OUTDATED


def test_equal_signal_uses_earliest_observation_independent_of_input_order() -> None:
    early = _observation(latitude=1.0)
    late = _observation(observed_at_utc=OBSERVED_AT + timedelta(seconds=1), latitude=2.0)
    forward = aggregate_network_findings([_zoned(late), _zoned(early)])
    reverse = aggregate_network_findings([_zoned(early), _zoned(late)])
    assert forward == reverse
    assert forward[0].representative_latitude == 1.0


def test_findings_are_separate_per_round_zone_and_network() -> None:
    observations = [
        _zoned(_observation()),
        _zoned(_observation(), zone_id="zone-b"),
        _zoned(_observation(network_id="network-b")),
        _zoned(_observation(measurement_round_id="round-b")),
    ]

    findings = aggregate_network_findings(reversed(observations))

    assert len(findings) == 4
    assert [(item.measurement_round_id, item.zone_id, item.network_id) for item in findings] == [
        ("round-b", "zone-a", "network-a"),
        ("synthetic-round", "zone-a", "network-a"),
        ("synthetic-round", "zone-a", "network-b"),
        ("synthetic-round", "zone-b", "network-a"),
    ]
