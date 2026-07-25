from pathlib import Path

from shapely.geometry import Polygon
from streamlit.testing.v1 import AppTest

from cyberbrein.processing.models import ApprovedZone
from cyberbrein.storage.repository import StorageRepository


def test_delete_dialog_requires_confirmation_and_removes_round(
    clean_postgis: str,
    tmp_path: Path,
    monkeypatch,
) -> None:
    storage = StorageRepository(clean_postgis)
    storage.initialize()
    storage.replace_measurement_round(
        "round-to-delete",
        [ApprovedZone("zone-a", Polygon([(0, 0), (1, 0), (1, 1), (0, 1)]))],
        [],
    )
    storage.close()
    monkeypatch.setenv("CYBERBREIN_DATABASE_URL", clean_postgis)
    monkeypatch.setenv(
        "CYBERBREIN_ACTIVITY_LOG_PATH",
        str(tmp_path / "operations.jsonl"),
    )

    app = AppTest.from_file("src/cyberbrein/presentation/app.py").run()
    assert not app.exception

    delete_button = next(button for button in app.button if button.label == "Meetdata verwijderen")
    delete_button.click().run()
    assert not app.exception
    confirmation_button = next(
        button for button in app.button if button.label == "Bevestig verwijdering"
    )
    assert confirmation_button.disabled

    app.checkbox[0].check().run()
    confirmation_button = next(
        button for button in app.button if button.label == "Bevestig verwijdering"
    )
    assert not confirmation_button.disabled
    confirmation_button.click().run()

    assert not app.exception
    assert any("definitief verwijderd" in success.value for success in app.success)
    assert any("geen verwerkte meetronde" in info.value for info in app.info)
