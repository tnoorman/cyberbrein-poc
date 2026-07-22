from dataclasses import replace
from datetime import datetime, timedelta, timezone

from shapely.geometry import Polygon

from cyberbrein.ingestion.models import AcceptedObservation
from cyberbrein.processing.models import ApprovedZone, EncryptionCategory, ProcessingPolicy
from cyberbrein.processing.service import ProcessingService

OBSERVED_AT = datetime(2026, 1, 1, 12, 0, tzinfo=timezone.utc)


def _observation(**changes: object) -> AcceptedObservation:
    observation = AcceptedObservation(
        measurement_round_id="synthetic-round",
        observed_at_utc=OBSERVED_AT,
        network_id="network-a",
        ssid_present=True,
        rssi_dbm=-60,
        channel=36,
        frequency_mhz=5180,
        band="5GHz",
        encryption="WPA3",
        latitude=0.5,
        longitude=0.5,
        gps_mode=3,
        gps_accuracy_m=2.0,
    )
    return replace(observation, **changes)


def _service() -> ProcessingService:
    zone = ApprovedZone("zone-a", Polygon([(0, 0), (1, 0), (1, 1), (0, 1)]))
    return ProcessingService([zone], ProcessingPolicy(max_gps_accuracy_m=10.0))


def test_service_runs_quality_zone_normalization_aggregation_and_scoring() -> None:
    result = _service().process(
        [
            _observation(),
            _observation(
                observed_at_utc=OBSERVED_AT + timedelta(seconds=1),
                rssi_dbm=-40,
                encryption="OPEN",
            ),
            _observation(network_id="outside", longitude=2.0),
            _observation(network_id="inaccurate", gps_accuracy_m=11.0),
        ]
    )

    assert result.input_observation_count == 4
    assert result.accepted_observation_count == 2
    assert result.rejected_observation_count == 2
    assert result.rejection_reasons == {
        "gps_accuracy_exceeded": 1,
        "outside_approved_zone": 1,
    }
    assert len(result.findings) == 1
    scored = result.findings[0]
    assert scored.finding.observation_count == 2
    assert scored.finding.representative_rssi_dbm == -40
    assert scored.finding.encryption is EncryptionCategory.OPEN
    assert scored.score == sum(factor.points for factor in scored.score_factors)


def test_service_accepts_a_generator_and_empty_result() -> None:
    observations = (_observation(longitude=2.0) for _ in range(2))
    result = _service().process(observations)
    assert result.input_observation_count == 2
    assert result.accepted_observation_count == 0
    assert result.findings == ()


def test_service_rejects_duplicate_zone_ids() -> None:
    geometry = Polygon([(0, 0), (1, 0), (1, 1), (0, 1)])
    try:
        ProcessingService(
            [ApprovedZone("zone-a", geometry), ApprovedZone("zone-a", geometry)],
            ProcessingPolicy(),
        )
    except ValueError as error:
        assert str(error) == "zone IDs must be unique"
    else:
        raise AssertionError("duplicate zone IDs must be rejected")
