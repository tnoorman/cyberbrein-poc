import json
import os
from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Protocol

from cyberbrein.storage.repository import StorageDeletionResult


class MeasurementRoundDeleter(Protocol):
    def delete_measurement_round(self, measurement_round_id: str) -> StorageDeletionResult: ...


@dataclass(frozen=True, slots=True)
class DeletionResult:
    deleted_zones: int
    deleted_findings: int
    deleted_scores: int
    deleted_score_factors: int
    verified: bool


class ActivityLog:
    """Append-only, privacy-safe lifecycle event log."""

    def __init__(
        self,
        path: str | Path,
        *,
        clock: Callable[[], datetime] | None = None,
    ) -> None:
        self._path = Path(path)
        self._clock = clock or (lambda: datetime.now(timezone.utc))

    def record(self, *, status: str, result: DeletionResult | None = None) -> None:
        event: dict[str, object] = {
            "action": "delete_measurement_round",
            "status": status,
            "timestamp_utc": self._clock().astimezone(timezone.utc).isoformat(),
        }
        if result is not None:
            event.update(
                {
                    "deleted_findings": result.deleted_findings,
                    "deleted_score_factors": result.deleted_score_factors,
                    "deleted_scores": result.deleted_scores,
                    "deleted_zones": result.deleted_zones,
                    "verification_remaining": 0 if result.verified else 1,
                }
            )

        self._path.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
        descriptor = os.open(
            self._path,
            os.O_APPEND | os.O_CREAT | os.O_WRONLY,
            0o600,
        )
        os.fchmod(descriptor, 0o600)
        with os.fdopen(descriptor, "a", encoding="utf-8") as stream:
            stream.write(json.dumps(event, sort_keys=True))
            stream.write("\n")


class OperationsService:
    def __init__(
        self,
        repository: MeasurementRoundDeleter,
        activity_log: ActivityLog,
    ) -> None:
        self._repository = repository
        self._activity_log = activity_log

    def delete_measurement_round(self, measurement_round_id: str) -> DeletionResult:
        try:
            storage_result = self._repository.delete_measurement_round(measurement_round_id)
        except Exception:
            self._activity_log.record(status="FAILED")
            raise

        result = _deletion_result(storage_result)
        self._activity_log.record(status="SUCCEEDED", result=result)
        return result


def _deletion_result(storage_result: StorageDeletionResult) -> DeletionResult:
    return DeletionResult(
        deleted_zones=storage_result.before.zones,
        deleted_findings=storage_result.before.network_findings,
        deleted_scores=storage_result.before.network_scores,
        deleted_score_factors=storage_result.before.score_factors,
        verified=storage_result.after.all_zero,
    )
