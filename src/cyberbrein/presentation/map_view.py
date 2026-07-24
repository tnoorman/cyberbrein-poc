import folium
from folium.plugins import MarkerCluster

from .models import DashboardData, FindingView

LABEL_FREE_TILE_URL = "https://{s}.basemaps.cartocdn.com/light_nolabels/{z}/{x}/{y}{r}.png"
TILE_ATTRIBUTION = (
    '&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a> '
    'contributors &copy; <a href="https://carto.com/attributions">CARTO</a>'
)
MARKER_COLORS = {
    "GREEN": "#2e7d32",
    "YELLOW": "#f9a825",
    "RED": "#c62828",
}
SELECTION_PREFIX = "Selecteer netwerkvondst "


def build_map(data: DashboardData) -> folium.Map:
    """Build a label-free road map without embedding network identifiers."""
    bounds = _bounds(data)
    center = (
        ((bounds[1] + bounds[3]) / 2, (bounds[0] + bounds[2]) / 2)
        if bounds is not None
        else (52.1, 5.3)
    )
    map_view = folium.Map(
        location=center,
        zoom_start=16,
        tiles=None,
        control_scale=True,
        prefer_canvas=True,
    )
    folium.TileLayer(
        tiles=LABEL_FREE_TILE_URL,
        attr=TILE_ATTRIBUTION,
        name="Wegen zonder labels",
        max_zoom=20,
        subdomains="abcd",
    ).add_to(map_view)
    for zone in data.zones:
        folium.GeoJson(
            zone.geometry.__geo_interface__,
            style_function=lambda _feature: {
                "color": "#455a64",
                "weight": 2,
                "fillColor": "#cfd8dc",
                "fillOpacity": 0.25,
            },
        ).add_to(map_view)
    marker_cluster = MarkerCluster(
        name="Netwerkvondsten",
        overlay=True,
        control=False,
        options={
            "showCoverageOnHover": False,
            "spiderfyOnMaxZoom": True,
            "spiderfyDistanceMultiplier": 1.5,
            "maxClusterRadius": 35,
        },
    ).add_to(map_view)
    for position, finding in enumerate(data.findings, start=1):
        color = MARKER_COLORS[finding.score_color]
        folium.Marker(
            location=(finding.latitude, finding.longitude),
            icon=folium.DivIcon(
                icon_size=(16, 16),
                icon_anchor=(8, 8),
                class_name="cyberbrein-finding-marker",
                html=(
                    '<span aria-hidden="true" style="display:block;width:16px;height:16px;'
                    f"border-radius:50%;background:{color};border:2px solid #fff;"
                    'box-shadow:0 1px 3px rgba(0,0,0,.45)"></span>'
                ),
            ),
            tooltip=f"{SELECTION_PREFIX}{position}",
        ).add_to(marker_cluster)
    if bounds is not None:
        map_view.fit_bounds([[bounds[1], bounds[0]], [bounds[3], bounds[2]]])
    return map_view


def findings_at_map_click(
    findings: tuple[FindingView, ...],
    latitude: float,
    longitude: float,
    tolerance: float = 1e-8,
) -> tuple[FindingView, ...]:
    return tuple(
        finding
        for finding in findings
        if abs(finding.latitude - latitude) <= tolerance
        and abs(finding.longitude - longitude) <= tolerance
    )


def finding_from_selection_label(
    findings: tuple[FindingView, ...],
    label: str | None,
) -> FindingView | None:
    if not label or not label.startswith(SELECTION_PREFIX):
        return None
    try:
        position = int(label.removeprefix(SELECTION_PREFIX))
    except ValueError:
        return None
    if not 1 <= position <= len(findings):
        return None
    return findings[position - 1]


def _bounds(data: DashboardData) -> tuple[float, float, float, float] | None:
    if data.zones:
        min_x = min(zone.geometry.bounds[0] for zone in data.zones)
        min_y = min(zone.geometry.bounds[1] for zone in data.zones)
        max_x = max(zone.geometry.bounds[2] for zone in data.zones)
        max_y = max(zone.geometry.bounds[3] for zone in data.zones)
        return min_x, min_y, max_x, max_y
    if data.findings:
        longitudes = [finding.longitude for finding in data.findings]
        latitudes = [finding.latitude for finding in data.findings]
        return min(longitudes), min(latitudes), max(longitudes), max(latitudes)
    return None
