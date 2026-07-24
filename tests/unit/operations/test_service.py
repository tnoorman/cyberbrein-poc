import json
import stat
from datetime import datetime, timezone
from pathlib import Path

import pytest

from cyberbrein.operations.service import ActivityLog, OperationsService
from cyberbrein.storage.repository import (
    MeasurementRoundRecordCounts,
    StorageDeletionResult,
)


class FakeRepository:
    def __init__(self, *, error: Exception | None = None) -> None:
        self.error = error
        self.requested_round: str | None = None

    def delete_measurement_round(self, measurement_round_id: str) -> StorageDeletionResult:
        self.requested_round = measurement_round_id
        if self.error is not None:
            raise self.error
        return StorageDeletionResult(
            before=MeasurementRoundRecordCounts(1, 1, 2, 2, 6),
            after=MeasurementRoundRecordCounts(0, 0, 0, 0, 0),
        )


def _activity_log(path: Path) -> ActivityLog:
    return ActivityLog(
        path,
        clock=lambda: datetime(2026, 7, 25, 10, 30, tzinfo=timezone.utc),
    )


def test_successful_deletion_returns_safe_counts_and_writes_private_log(tmp_path: Path) -> None:
    path = tmp_path / "operations" / "activity.jsonl"
    repository = FakeRepository()
    service = OperationsService(repository, _activity_log(path))

    result = service.delete_measurement_round("private-round-reference")

    assert repository.requested_round == "private-round-reference"
    assert result.deleted_findings == 2
    assert result.deleted_score_factors == 6
    assert result.verified
    assert stat.S_IMODE(path.stat().st_mode) == 0o600
    event = json.loads(path.read_text(encoding="utf-8"))
    assert event == {
        "action": "delete_measurement_round",
        "deleted_findings": 2,
        "deleted_score_factors": 6,
        "deleted_scores": 2,
        "deleted_zones": 1,
        "status": "SUCCEEDED",
        "timestamp_utc": "2026-07-25T10:30:00+00:00",
        "verification_remaining": 0,
    }
    assert "private-round-reference" not in path.read_text(encoding="utf-8")


def test_failed_deletion_is_logged_without_identifier_or_exception_text(tmp_path: Path) -> None:
    path = tmp_path / "activity.jsonl"
    repository = FakeRepository(error=RuntimeError("private-round-reference"))
    service = OperationsService(repository, _activity_log(path))

    with pytest.raises(RuntimeError, match="private-round-reference"):
        service.delete_measurement_round("private-round-reference")

    content = path.read_text(encoding="utf-8")
    event = json.loads(content)
    assert event["status"] == "FAILED"
    assert "private-round-reference" not in content
    assert set(event) == {"action", "status", "timestamp_utc"}
