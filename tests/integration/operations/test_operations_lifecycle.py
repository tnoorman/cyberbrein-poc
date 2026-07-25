from pathlib import Path

from shapely.geometry import Polygon

from cyberbrein.operations.service import ActivityLog, OperationsService
from cyberbrein.presentation.repository import PresentationRepository
from cyberbrein.processing.models import ApprovedZone
from cyberbrein.storage.repository import StorageRepository


def test_operations_deletes_active_round_and_presentation_becomes_empty(
    clean_postgis: str,
    tmp_path: Path,
) -> None:
    storage = StorageRepository(clean_postgis)
    storage.initialize()
    storage.replace_measurement_round(
        "round-to-delete",
        [ApprovedZone("zone-a", Polygon([(0, 0), (1, 0), (1, 1), (0, 1)]))],
        [],
    )
    try:
        result = OperationsService(
            storage,
            ActivityLog(tmp_path / "operations.jsonl"),
        ).delete_measurement_round("round-to-delete")
    finally:
        storage.close()

    presentation = PresentationRepository(clean_postgis)
    try:
        assert presentation.list_measurement_rounds() == ()
    finally:
        presentation.close()
    assert result.deleted_zones == 1
    assert result.deleted_findings == 0
    assert result.verified
