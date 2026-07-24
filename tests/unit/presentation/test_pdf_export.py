from datetime import datetime, timezone
from io import BytesIO
from time import monotonic

from pypdf import PdfReader
from shapely.geometry import Polygon

from cyberbrein.presentation.models import (
    DashboardData,
    DashboardFilters,
    FactorView,
    FilterOptions,
    FindingView,
    MeasurementRoundSummary,
    ZoneView,
)
from cyberbrein.presentation.pdf_export import generate_pdf


def _dashboard(findings: tuple[FindingView, ...] | None = None) -> DashboardData:
    now = datetime(2026, 1, 1, tzinfo=timezone.utc)
    finding = FindingView(
        measurement_round_id="round-a",
        zone_id="zone-a",
        network_id="pseudonym-must-not-be-exported",
        latitude=52.123456,
        longitude=5.123456,
        score=3,
        score_color="YELLOW",
        observation_count=2,
        average_rssi_dbm=-70.0,
        strongest_rssi_dbm=-65,
        channel=36,
        frequency_mhz=5180,
        band="5GHz",
        encryption="WPA2",
        factors=(
            FactorView("signal_strength", "-65 dBm", "strong", 2, 1, 2),
            FactorView("encryption", "WPA2", "current", 0, 2, 0),
            FactorView("observation_frequency", "2", "multiple", 1, 1, 1),
        ),
    )
    return DashboardData(
        measurement_round=MeasurementRoundSummary("round-a", "round-a", "COMPLETED", now, now),
        zones=(
            ZoneView(
                "zone-a",
                Polygon(
                    [
                        (5.12, 52.12),
                        (5.13, 52.12),
                        (5.13, 52.13),
                        (5.12, 52.13),
                    ]
                ),
            ),
        ),
        findings=(finding,) if findings is None else findings,
        filter_options=FilterOptions(
            ("zone-a",),
            ("5GHz",),
            (36,),
            ("WPA2",),
            ("YELLOW",),
            ("strong",),
        ),
    )


def _text(pdf: bytes) -> str:
    return "\n".join(page.extract_text() or "" for page in PdfReader(BytesIO(pdf)).pages)


def test_pdf_matches_active_filters_and_contains_explainable_result() -> None:
    filters = DashboardFilters(
        zone_ids=frozenset({"zone-a"}),
        bands=frozenset({"5GHz"}),
        score_colors=frozenset({"YELLOW"}),
    )
    started = monotonic()
    pdf = generate_pdf(_dashboard(), filters)
    elapsed = monotonic() - started
    text = _text(pdf)

    assert pdf.startswith(b"%PDF")
    assert elapsed < 10
    assert "Actieve filters:" in text
    assert "zones: zone-a" in text
    assert "banden: 5GHz" in text
    assert "scorekleuren: YELLOW" in text
    assert "Signaalsterkte" in text
    assert "Encryptietype" in text
    assert "Waarnemingsfrequentie" in text
    assert "geen volledig beveiligingsoordeel" in " ".join(text.split())


def test_pdf_excludes_identifiers_and_numeric_coordinates() -> None:
    text = _text(generate_pdf(_dashboard(), DashboardFilters()))
    assert "pseudonym-must-not-be-exported" not in text
    assert "52.123456" not in text
    assert "5.123456" not in text
    assert "BSSID" not in text
    assert "SSID" not in text


def test_empty_filtered_result_generates_explanatory_pdf() -> None:
    pdf = generate_pdf(_dashboard(findings=()), DashboardFilters())
    assert "geen netwerkvondsten beschikbaar" in _text(pdf)
