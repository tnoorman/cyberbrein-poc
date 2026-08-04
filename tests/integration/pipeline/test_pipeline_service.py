from dataclasses import replace
from datetime import datetime, timezone
from pathlib import Path

import pytest
from shapely.geometry import Polygon

from cyberbrein.collection.models import RawObservation
from cyberbrein.collection.sqlite_writer import SQLiteObservationWriter
from cyberbrein.pipeline.models import PipelineRuntimeError
from cyberbrein.pipeline.service import PipelineService
from cyberbrein.processing.models import ApprovedZone, ScoredNetworkFinding
from cyberbrein.storage.repository import StorageRepository


def _raw_observation(**changes: object) -> RawObservation:
    observation = RawObservation(
        measurement_round_id="synthetic-round",
        observed_at_utc=datetime(2026, 1, 1, 12, 0, tzinfo=timezone.utc),
        bssid="02:00:00:00:00:01",
        ssid="SYNTHETIC",
        rssi_dbm=-50,
        channel=36,
        frequency_mhz=5180,
        band="5GHz",
        encryption="WPA2/PSK",
        frame_type="BEACON",
        latitude=0.5,
        longitude=0.5,
        gps_mode=3,
        gps_accuracy_m=3.0,
    )
    return replace(observation, **changes)


def _write_source(path: Path, observations: list[RawObservation]) -> None:
    writer = SQLiteObservationWriter(path)
    with writer.transaction() as transaction:
        for observation in observations:
            transaction.add(observation)


def _zone() -> ApprovedZone:
    return ApprovedZone("zone-a", Polygon([(0, 0), (1, 0), (1, 1), (0, 1)]))


def _run(
    service: PipelineService,
    source: Path,
    storage_database_url: str = "postgresql+psycopg2:///unused",
):
    return service.run(
        source_database_path=source,
        measurement_round_id="synthetic-round",
        zones=[_zone()],
        secret="a" * 64,
        storage_database_url=storage_database_url,
        max_gps_accuracy_m=15.0,
    )


def test_complete_round_is_processed_verified_and_stored(
    tmp_path: Path,
    clean_postgis: str,
) -> None:
    source = tmp_path / "source.sqlite"
    _write_source(source, [_raw_observation(), _raw_observation(rssi_dbm=-40)])

    result = _run(PipelineService(), source, clean_postgis)

    assert result.ingestion_accepted_count == 2
    assert result.ingestion_rejected_count == 0
    assert result.processing_accepted_count == 2
    assert result.processing_rejected_count == 0
    assert result.finding_count == 1
    repository = StorageRepository(clean_postgis)
    try:
        assert len(repository.load_measurement_round("synthetic-round")) == 1
    finally:
        repository.close()


def test_complete_processing_rejection_fails_before_empty_storage(tmp_path: Path) -> None:
    source = tmp_path / "source.sqlite"
    _write_source(source, [_raw_observation(gps_accuracy_m=30.0)])

    with pytest.raises(PipelineRuntimeError, match="no_usable_observations"):
        _run(PipelineService(), source)


def test_mixed_measurement_rounds_are_rejected_before_storage(tmp_path: Path) -> None:
    source = tmp_path / "source.sqlite"
    _write_source(
        source,
        [_raw_observation(), _raw_observation(measurement_round_id="other-round")],
    )

    with pytest.raises(PipelineRuntimeError, match="measurement_round_mismatch"):
        _run(PipelineService(), source)


def test_invalid_source_schema_has_safe_category(tmp_path: Path) -> None:
    source = tmp_path / "source.sqlite"
    source.touch()

    with pytest.raises(PipelineRuntimeError, match="invalid_source_buffer"):
        _run(PipelineService(), source)


class _VerifyingStorage:
    def __init__(self, findings: tuple[ScoredNetworkFinding, ...] = ()) -> None:
        self._findings = findings

    def initialize(self) -> None:
        pass

    def replace_measurement_round(
        self,
        measurement_round_id: str,
        zones: list[ApprovedZone] | tuple[ApprovedZone, ...],
        findings: list[ScoredNetworkFinding] | tuple[ScoredNetworkFinding, ...],
    ) -> None:
        del measurement_round_id, zones, findings

    def load_measurement_round(
        self,
        measurement_round_id: str,
    ) -> tuple[ScoredNetworkFinding, ...]:
        del measurement_round_id
        return self._findings

    def close(self) -> None:
        pass


def test_storage_verification_mismatch_is_reported_safely(tmp_path: Path) -> None:
    source = tmp_path / "source.sqlite"
    _write_source(source, [_raw_observation()])
    service = PipelineService(storage_factory=lambda url: _VerifyingStorage())

    with pytest.raises(PipelineRuntimeError, match="storage_verification_failed"):
        _run(service, source)


def test_storage_factory_failure_is_reported_safely(tmp_path: Path) -> None:
    source = tmp_path / "source.sqlite"
    _write_source(source, [_raw_observation()])

    def fail_safely(url: str):
        del url
        raise RuntimeError("internal storage detail")

    service = PipelineService(storage_factory=fail_safely)
    with pytest.raises(PipelineRuntimeError, match="storage_failed") as captured:
        _run(service, source)
    assert "internal storage detail" not in str(captured.value)
