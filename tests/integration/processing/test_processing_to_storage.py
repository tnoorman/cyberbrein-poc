from dataclasses import replace
from datetime import datetime, timedelta, timezone

from shapely.geometry import Polygon

from cyberbrein.ingestion.models import AcceptedObservation
from cyberbrein.processing.models import ApprovedZone, ProcessingPolicy
from cyberbrein.processing.service import ProcessingService
from cyberbrein.storage.repository import StorageRepository

OBSERVED_AT = datetime(2026, 1, 1, 12, 0, tzinfo=timezone.utc)


def _observation(**changes: object) -> AcceptedObservation:
    observation = AcceptedObservation(
        measurement_round_id="synthetic-round",
        observed_at_utc=OBSERVED_AT,
        network_id="pseudonymized-network-id",
        ssid_present=True,
        rssi_dbm=-65,
        channel=36,
        frequency_mhz=5180,
        band="5GHz",
        encryption="WPA2/PSK",
        latitude=0.5,
        longitude=0.5,
        gps_mode=3,
        gps_accuracy_m=3.0,
    )
    return replace(observation, **changes)


def test_accepted_observations_flow_through_processing_into_storage(
    clean_postgis: str,
) -> None:
    zone = ApprovedZone("zone-a", Polygon([(0, 0), (1, 0), (1, 1), (0, 1)]))
    processing = ProcessingService([zone], ProcessingPolicy(max_gps_accuracy_m=10.0))
    result = processing.process(
        [
            _observation(),
            _observation(
                observed_at_utc=OBSERVED_AT + timedelta(seconds=1),
                rssi_dbm=-45,
            ),
            _observation(network_id="outside-zone", longitude=2.0),
        ]
    )

    assert result.accepted_observation_count == 2
    assert result.rejected_observation_count == 1
    assert result.rejection_reasons == {"outside_approved_zone": 1}

    storage = StorageRepository(clean_postgis)
    storage.initialize()
    try:
        storage.replace_measurement_round("synthetic-round", [zone], result.findings)
        assert storage.load_measurement_round("synthetic-round") == result.findings
    finally:
        storage.close()
