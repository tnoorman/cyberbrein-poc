from datetime import datetime, timezone

from shapely.geometry import Polygon

from cyberbrein.presentation.map_view import build_map, findings_at_map_click
from cyberbrein.presentation.models import (
    DashboardData,
    FactorView,
    FilterOptions,
    FindingView,
    MeasurementRoundSummary,
    ZoneView,
)


def _finding(network_id: str = "private-pseudonym") -> FindingView:
    return FindingView(
        measurement_round_id="round-a",
        zone_id="zone-a",
        network_id=network_id,
        latitude=52.0,
        longitude=5.0,
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


def _dashboard() -> DashboardData:
    now = datetime(2026, 1, 1, tzinfo=timezone.utc)
    return DashboardData(
        measurement_round=MeasurementRoundSummary("round-a", "round-a", "COMPLETED", now, now),
        zones=(
            ZoneView(
                "zone-a",
                Polygon(
                    [
                        (4.99, 51.99),
                        (5.01, 51.99),
                        (5.01, 52.01),
                        (4.99, 52.01),
                    ]
                ),
            ),
        ),
        findings=(_finding(),),
        filter_options=FilterOptions(
            ("zone-a",),
            ("5GHz",),
            (36,),
            ("WPA2",),
            ("YELLOW",),
            ("strong",),
        ),
    )


def test_map_has_no_basemap_labels_or_network_identifier() -> None:
    rendered = build_map(_dashboard()).get_root().render()
    assert "tileLayer" not in rendered
    assert "private-pseudonym" not in rendered
    assert "#f9a825" in rendered
    assert "Selecteer netwerkvondst" in rendered


def test_map_click_resolves_finding_without_exposing_it_in_marker() -> None:
    finding = _finding()
    assert findings_at_map_click((finding,), 52.0, 5.0) == (finding,)
    assert findings_at_map_click((finding,), 52.1, 5.0) == ()
