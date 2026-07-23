import sqlite3
from collections.abc import Callable, Sequence
from pathlib import Path
from typing import Protocol

from cyberbrein.ingestion.service import IngestionService
from cyberbrein.processing.models import ApprovedZone, ProcessingPolicy, ScoredNetworkFinding
from cyberbrein.processing.service import ProcessingService
from cyberbrein.storage.repository import StorageRepository

from .models import PipelineResult, PipelineRuntimeError


class StoragePort(Protocol):
    def initialize(self) -> None: ...

    def replace_measurement_round(
        self,
        measurement_round_id: str,
        findings: Sequence[ScoredNetworkFinding],
    ) -> None: ...

    def load_measurement_round(
        self,
        measurement_round_id: str,
    ) -> tuple[ScoredNetworkFinding, ...]: ...

    def close(self) -> None: ...


StorageFactory = Callable[[str], StoragePort]


class PipelineService:
    def __init__(self, storage_factory: StorageFactory = StorageRepository) -> None:
        self._storage_factory = storage_factory

    def run(
        self,
        *,
        source_database_path: str | Path,
        measurement_round_id: str,
        zones: Sequence[ApprovedZone],
        secret: str,
        storage_database_path: str | Path,
        max_gps_accuracy_m: float,
    ) -> PipelineResult:
        if not measurement_round_id.strip():
            raise PipelineRuntimeError("invalid_measurement_round_id")

        source_path = Path(source_database_path)
        storage_path = Path(storage_database_path)
        if _same_path(source_path, storage_path):
            raise PipelineRuntimeError("invalid_storage_configuration")

        _validate_source_round(source_path, measurement_round_id)
        try:
            ingestion_result = IngestionService(source_path).ingest(secret)
        except Exception as error:
            raise PipelineRuntimeError("ingestion_failed") from error

        if any(
            observation.measurement_round_id != measurement_round_id
            for observation in ingestion_result.accepted
        ):
            raise PipelineRuntimeError("measurement_round_mismatch")

        try:
            processing_result = ProcessingService(
                zones,
                ProcessingPolicy(max_gps_accuracy_m=max_gps_accuracy_m),
            ).process(ingestion_result.accepted)
        except Exception as error:
            raise PipelineRuntimeError("processing_failed") from error

        try:
            storage_path.parent.mkdir(parents=True, exist_ok=True)
            storage = self._storage_factory(f"sqlite:///{storage_path.resolve()}")
        except Exception as error:
            raise PipelineRuntimeError("storage_failed") from error
        try:
            storage.initialize()
            storage.replace_measurement_round(measurement_round_id, processing_result.findings)
            stored_findings = storage.load_measurement_round(measurement_round_id)
        except Exception as error:
            try:
                storage.close()
            except Exception:
                pass
            raise PipelineRuntimeError("storage_failed") from error
        try:
            storage.close()
        except Exception as error:
            raise PipelineRuntimeError("storage_failed") from error

        if stored_findings != processing_result.findings:
            raise PipelineRuntimeError("storage_verification_failed")

        return PipelineResult(
            measurement_round_id=measurement_round_id,
            ingestion_accepted_count=ingestion_result.accepted_count,
            ingestion_rejected_count=ingestion_result.rejected_count,
            ingestion_rejection_reasons=ingestion_result.rejection_reasons,
            processing_accepted_count=processing_result.accepted_observation_count,
            processing_rejected_count=processing_result.rejected_observation_count,
            processing_rejection_reasons=processing_result.rejection_reasons,
            finding_count=len(processing_result.findings),
        )


def _validate_source_round(source_path: Path, measurement_round_id: str) -> None:
    try:
        with sqlite3.connect(f"file:{source_path.resolve()}?mode=ro", uri=True) as connection:
            rows = connection.execute(
                "SELECT DISTINCT measurement_round_id FROM raw_observation"
            ).fetchall()
    except sqlite3.Error as error:
        raise PipelineRuntimeError("invalid_source_buffer") from error
    round_ids = {row[0] for row in rows}
    if round_ids != {measurement_round_id}:
        raise PipelineRuntimeError("measurement_round_mismatch")


def _same_path(first: Path, second: Path) -> bool:
    try:
        return first.resolve() == second.resolve()
    except OSError as error:
        raise PipelineRuntimeError("invalid_storage_configuration") from error
