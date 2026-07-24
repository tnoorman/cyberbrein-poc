from datetime import datetime, timezone
from io import BytesIO
from time import monotonic

from PIL import Image
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
from cyberbrein.presentation.pdf_export import _build_basemap_image, generate_pdf


def no_tiles(_url: str) -> None:
    return None


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
    pdf = generate_pdf(_dashboard(), filters, tile_fetcher=no_tiles)
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
    text = _text(generate_pdf(_dashboard(), DashboardFilters(), tile_fetcher=no_tiles))
    assert "pseudonym-must-not-be-exported" not in text
    assert "52.123456" not in text
    assert "5.123456" not in text
    assert "BSSID" not in text
    assert "SSID" not in text


def test_empty_filtered_result_generates_explanatory_pdf() -> None:
    pdf = generate_pdf(
        _dashboard(findings=()),
        DashboardFilters(),
        tile_fetcher=no_tiles,
    )
    assert "geen netwerkvondsten beschikbaar" in _text(pdf)


def test_pdf_basemap_stitches_label_free_road_tiles() -> None:
    tile_buffer = BytesIO()
    Image.new("RGB", (256, 256), "#dde7ed").save(tile_buffer, format="PNG")
    requested_urls: list[str] = []

    def fetch_tile(url: str) -> bytes:
        requested_urls.append(url)
        return tile_buffer.getvalue()

    image = _build_basemap_image(_dashboard(), fetch_tile, width=600, height=320)

    assert image is not None
    assert image.size == (600, 320)
    assert requested_urls
    assert all("light_nolabels" in url for url in requested_urls)


def test_pdf_basemap_falls_back_when_tiles_are_unavailable() -> None:
    assert _build_basemap_image(_dashboard(), no_tiles, width=600, height=320) is None
