import folium

from .models import DashboardData, FindingView

MARKER_COLORS = {
    "GREEN": "#2e7d32",
    "YELLOW": "#f9a825",
    "RED": "#c62828",
}


def build_map(data: DashboardData) -> folium.Map:
    """Build a label-free map without embedding network identifiers."""
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
    for finding in data.findings:
        folium.CircleMarker(
            location=(finding.latitude, finding.longitude),
            radius=7,
            color="#ffffff",
            weight=1,
            fill=True,
            fill_color=MARKER_COLORS[finding.score_color],
            fill_opacity=0.95,
            tooltip="Selecteer netwerkvondst",
        ).add_to(map_view)
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
