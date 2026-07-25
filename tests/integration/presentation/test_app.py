from datetime import datetime, timezone
from pathlib import Path

from shapely.geometry import Polygon
from streamlit.testing.v1 import AppTest

from cyberbrein.processing.models import (
    ApprovedZone,
    AttentionLevel,
    EncryptionCategory,
    NetworkFinding,
    ScoredNetworkFinding,
    ScoreFactor,
)
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


def test_selected_finding_opens_dedicated_explainable_detail(
    clean_postgis: str,
    monkeypatch,
) -> None:
    observed_at = datetime(2026, 1, 1, 12, 0, tzinfo=timezone.utc)
    finding = NetworkFinding(
        measurement_round_id="round-with-detail",
        zone_id="zone-a",
        network_id="abcdefghijklmnop",
        observation_count=3,
        first_observed_at_utc=observed_at,
        last_observed_at_utc=observed_at,
        representative_observed_at_utc=observed_at,
        representative_latitude=0.5,
        representative_longitude=0.5,
        average_rssi_dbm=-70,
        strongest_rssi_dbm=-65,
        representative_channel=36,
        representative_frequency_mhz=5180,
        representative_band="5GHz",
        encryption=EncryptionCategory.WPA2,
        ssid_present=False,
    )
    scored = ScoredNetworkFinding(
        finding,
        3,
        AttentionLevel.YELLOW,
        (
            ScoreFactor("signal_strength", "-65 dBm", "strong", 2, 1),
            ScoreFactor("encryption", "WPA2", "current", 0, 2),
            ScoreFactor("observation_frequency", "3", "multiple", 1, 1),
        ),
    )
    storage = StorageRepository(clean_postgis)
    storage.initialize()
    storage.replace_measurement_round(
        "round-with-detail",
        [ApprovedZone("zone-a", Polygon([(0, 0), (1, 0), (1, 1), (0, 1)]))],
        [scored],
    )
    storage.close()
    monkeypatch.setenv("CYBERBREIN_DATABASE_URL", clean_postgis)

    app = AppTest.from_file("src/cyberbrein/presentation/app.py")
    app.session_state["selected_network_id"] = "abcdefghijklmnop"
    app.run()

    assert not app.exception
    assert any(title.value == "abcdefghijkl…" for title in app.title)
    assert [heading.value for heading in app.subheader] == [
        "Scorefactoren",
        "Technische metadata",
    ]
    assert any(button.label == "← Terug naar overzicht" for button in app.button)
    assert not app.dataframe


def test_pdf_action_opens_preview_with_download(
    clean_postgis: str,
    monkeypatch,
) -> None:
    storage = StorageRepository(clean_postgis)
    storage.initialize()
    storage.replace_measurement_round(
        "round-for-pdf",
        [ApprovedZone("zone-a", Polygon([(0, 0), (1, 0), (1, 1), (0, 1)]))],
        [],
    )
    storage.close()
    monkeypatch.setenv("CYBERBREIN_DATABASE_URL", clean_postgis)

    app = AppTest.from_file("src/cyberbrein/presentation/app.py").run()
    export_button = next(button for button in app.button if button.label == "Exporteer PDF")
    export_button.click().run(timeout=15)

    assert not app.exception
    assert any(button.label == "Download PDF" for button in app.get("download_button"))

    delete_button = next(button for button in app.button if button.label == "Meetdata verwijderen")
    delete_button.click().run()

    assert not app.exception
    assert any(button.label == "Bevestig verwijdering" for button in app.button)


def test_filter_form_only_changes_results_after_apply_and_can_reset(
    clean_postgis: str,
    monkeypatch,
) -> None:
    storage = StorageRepository(clean_postgis)
    storage.initialize()
    storage.replace_measurement_round(
        "round-for-filters",
        [ApprovedZone("zone-a", Polygon([(0, 0), (1, 0), (1, 1), (0, 1)]))],
        [],
    )
    storage.close()
    monkeypatch.setenv("CYBERBREIN_DATABASE_URL", clean_postgis)

    app = AppTest.from_file("src/cyberbrein/presentation/app.py").run()
    zone_filter = next(widget for widget in app.multiselect if widget.label == "Zone")
    zone_filter.select("zone-a").run()

    assert app.session_state["applied_filters"].zone_ids == frozenset()

    apply_button = next(button for button in app.button if button.label == "Filters toepassen")
    apply_button.click().run()
    assert app.session_state["applied_filters"].zone_ids == frozenset({"zone-a"})

    reset_button = next(button for button in app.button if button.label == "Filters wissen")
    reset_button.click().run()
    assert app.session_state["applied_filters"].zone_ids == frozenset()
