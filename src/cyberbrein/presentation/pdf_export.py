import math
from collections.abc import Callable
from concurrent.futures import ThreadPoolExecutor
from functools import lru_cache
from io import BytesIO

import requests
from PIL import Image
from reportlab.lib import colors
from reportlab.lib.enums import TA_CENTER
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import mm
from reportlab.lib.utils import ImageReader
from reportlab.platypus import (
    Flowable,
    KeepTogether,
    Paragraph,
    SimpleDocTemplate,
    Spacer,
    Table,
    TableStyle,
)

from .map_view import MARKER_COLORS, ZONE_FILL_OPACITY
from .models import DashboardData, DashboardFilters

TileFetcher = Callable[[str], bytes | None]
TILE_SIZE = 256
MAX_TILE_ZOOM = 20

COLOR_TEXT = {
    "GREEN": "Groen – beperkte aandacht",
    "YELLOW": "Geel – verhoogde aandacht",
    "RED": "Rood – hoge aandacht",
}
FACTOR_TEXT = {
    "signal_strength": "Signaalsterkte",
    "encryption": "Encryptietype",
    "observation_frequency": "Waarnemingsfrequentie",
}
CATEGORY_TEXT = {
    "weak": "zwak ontvangen",
    "medium": "middelsterk ontvangen",
    "strong": "sterk ontvangen",
    "current": "actueel beveiligd",
    "outdated_or_unknown": "verouderd of onbekend",
    "open": "open netwerk",
    "incidental": "incidenteel waargenomen",
    "multiple": "meerdere keren waargenomen",
    "frequent": "vaak waargenomen",
}


def generate_pdf(
    data: DashboardData,
    filters: DashboardFilters,
    *,
    tile_fetcher: TileFetcher | None = None,
) -> bytes:
    """Create a privacy-bounded in-memory PDF of the currently filtered dashboard."""
    output = BytesIO()
    document = SimpleDocTemplate(
        output,
        pagesize=A4,
        rightMargin=18 * mm,
        leftMargin=18 * mm,
        topMargin=16 * mm,
        bottomMargin=16 * mm,
        title="Cyberbrein Wi-Fi-exposurerapport",
        author="Cyberbrein",
    )
    styles = getSampleStyleSheet()
    styles.add(
        ParagraphStyle(
            name="CenteredNote",
            parent=styles["BodyText"],
            alignment=TA_CENTER,
            textColor=colors.HexColor("#455a64"),
            fontSize=8,
            leading=11,
        )
    )
    story: list[Flowable] = [
        Paragraph("Wi-Fi-exposure: meetronde", styles["Title"]),
        Paragraph(f"Meetronde: {data.measurement_round.name}", styles["BodyText"]),
        Paragraph(_filter_description(filters), styles["BodyText"]),
        Spacer(1, 4 * mm),
        _summary_table(data),
        Spacer(1, 5 * mm),
        Paragraph("Kaartweergave", styles["Heading2"]),
        _MapDrawing(
            data,
            width=170 * mm,
            height=90 * mm,
            tile_fetcher=tile_fetcher or _fetch_tile,
        ),
        Paragraph(
            "De posities zijn indicatieve netwerkvondsten binnen de meetcontext en bewijzen "
            "niet waar een access point fysiek aanwezig is. Kaartgegevens: "
            "OpenStreetMap-bijdragers en CARTO.",
            styles["CenteredNote"],
        ),
        Spacer(1, 5 * mm),
        Paragraph("Netwerkvondsten en scorefactoren", styles["Heading2"]),
    ]
    if not data.findings:
        story.append(
            Paragraph(
                "Voor deze selectie zijn geen netwerkvondsten beschikbaar.", styles["BodyText"]
            )
        )
    for position, finding in enumerate(data.findings, start=1):
        factor_rows = [
            ["Factor", "Waarde", "Categorie", "Punten", "Weging", "Gewogen"],
            *[
                [
                    FACTOR_TEXT[factor.factor_type],
                    factor.observed_value,
                    CATEGORY_TEXT[factor.category],
                    str(factor.points),
                    str(factor.weight),
                    str(factor.weighted_points),
                ]
                for factor in finding.factors
            ],
        ]
        story.append(
            KeepTogether(
                [
                    Paragraph(
                        f"Vondst {position}: {COLOR_TEXT[finding.score_color]} ({finding.score}/8)",
                        styles["Heading3"],
                    ),
                    Paragraph(
                        f"Zone {finding.zone_id}; {finding.band}; kanaal {finding.channel}; "
                        f"{finding.encryption}; gemiddeld {finding.average_rssi_dbm:.1f} dBm; "
                        f"{finding.observation_count} waarnemingen.",
                        styles["BodyText"],
                    ),
                    _styled_table(
                        factor_rows,
                        widths=[36 * mm, 26 * mm, 40 * mm, 16 * mm, 16 * mm, 20 * mm],
                    ),
                    Spacer(1, 3 * mm),
                ]
            )
        )
    story.extend(
        [
            Spacer(1, 3 * mm),
            Paragraph("Toelichting", styles["Heading2"]),
            Paragraph(
                "De exposure-score is gebaseerd op passief waargenomen metadata. "
                "Signaalsterkte en waarnemingsfrequentie wegen één keer; encryptietype weegt "
                "twee keer. De score is geen volledig beveiligingsoordeel over een netwerk, "
                "organisatie of locatie.",
                styles["BodyText"],
            ),
        ]
    )
    document.build(story)
    return output.getvalue()


def _summary_table(data: DashboardData) -> Table:
    return _styled_table(
        [
            ["Netwerkvondsten", "Verhoogde aandacht", "Hoge aandacht"],
            [str(data.total_count), str(data.elevated_count), str(data.high_count)],
        ],
        widths=[55 * mm, 55 * mm, 55 * mm],
        centered=True,
    )


def _styled_table(
    rows: list[list[str]],
    *,
    widths: list[float],
    centered: bool = False,
) -> Table:
    table = Table(rows, colWidths=widths, hAlign="CENTER" if centered else "LEFT", repeatRows=1)
    table.setStyle(
        TableStyle(
            [
                ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#263238")),
                ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
                ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
                ("FONTNAME", (0, 1), (-1, -1), "Helvetica"),
                ("ALIGN", (0, 0), (-1, -1), "CENTER"),
                ("GRID", (0, 0), (-1, -1), 0.5, colors.HexColor("#90a4ae")),
                ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
                ("FONTSIZE", (0, 0), (-1, -1), 8),
                ("LEADING", (0, 0), (-1, -1), 10),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
                ("TOPPADDING", (0, 0), (-1, -1), 4),
            ]
        )
    )
    return table


def _filter_description(filters: DashboardFilters) -> str:
    active: list[str] = []
    if filters.zone_ids:
        active.append(f"zones: {', '.join(sorted(filters.zone_ids))}")
    if filters.bands:
        active.append(f"banden: {', '.join(sorted(filters.bands))}")
    if filters.channels:
        active.append(f"kanalen: {', '.join(map(str, sorted(filters.channels)))}")
    if filters.encryptions:
        active.append(f"encryptie: {', '.join(sorted(filters.encryptions))}")
    if filters.score_colors:
        active.append(f"scorekleuren: {', '.join(sorted(filters.score_colors))}")
    if filters.signal_categories:
        active.append(f"signaalklassen: {', '.join(sorted(filters.signal_categories))}")
    return "Actieve filters: " + ("; ".join(active) if active else "geen")


class _MapDrawing(Flowable):
    def __init__(
        self,
        data: DashboardData,
        *,
        width: float,
        height: float,
        tile_fetcher: TileFetcher,
    ) -> None:
        super().__init__()
        self.data = data
        self.width = width
        self.height = height
        self.tile_fetcher = tile_fetcher

    def draw(self) -> None:
        self.canv.setStrokeColor(colors.HexColor("#90a4ae"))
        self.canv.setFillColor(colors.HexColor("#fafafa"))
        self.canv.rect(0, 0, self.width, self.height, fill=1, stroke=1)
        bounds = _map_bounds(self.data)
        if bounds is None:
            return
        basemap = _build_basemap_image(
            self.data,
            self.tile_fetcher,
            width=max(1, round(self.width * 2)),
            height=max(1, round(self.height * 2)),
        )
        if basemap is not None:
            image_buffer = BytesIO()
            basemap.save(image_buffer, format="PNG")
            image_buffer.seek(0)
            self.canv.drawImage(
                ImageReader(image_buffer),
                0,
                0,
                width=self.width,
                height=self.height,
                preserveAspectRatio=False,
                mask="auto",
            )
        for zone in self.data.zones:
            geometries = (
                zone.geometry.geoms
                if zone.geometry.geom_type == "MultiPolygon"
                else (zone.geometry,)
            )
            for polygon in geometries:
                points = [
                    _project(x, y, bounds, self.width, self.height)
                    for x, y in polygon.exterior.coords
                ]
                path = self.canv.beginPath()
                path.moveTo(*points[0])
                for point in points[1:]:
                    path.lineTo(*point)
                path.close()
                self.canv.saveState()
                self.canv.setStrokeColor(colors.HexColor("#455a64"))
                self.canv.setFillColor(colors.HexColor("#cfd8dc"))
                self.canv.setFillAlpha(ZONE_FILL_OPACITY)
                self.canv.drawPath(path, stroke=1, fill=1, fillMode=0)
                self.canv.restoreState()
        for finding in self.data.findings:
            x, y = _project(
                finding.longitude,
                finding.latitude,
                bounds,
                self.width,
                self.height,
            )
            self.canv.setFillColor(colors.HexColor(MARKER_COLORS[finding.score_color]))
            self.canv.setStrokeColor(colors.white)
            self.canv.circle(x, y, 3.5, fill=1, stroke=1)


def _map_bounds(data: DashboardData) -> tuple[float, float, float, float] | None:
    if data.zones:
        min_x = min(zone.geometry.bounds[0] for zone in data.zones)
        min_y = min(zone.geometry.bounds[1] for zone in data.zones)
        max_x = max(zone.geometry.bounds[2] for zone in data.zones)
        max_y = max(zone.geometry.bounds[3] for zone in data.zones)
    elif data.findings:
        min_x = min(finding.longitude for finding in data.findings)
        min_y = min(finding.latitude for finding in data.findings)
        max_x = max(finding.longitude for finding in data.findings)
        max_y = max(finding.latitude for finding in data.findings)
    else:
        return None
    padding_x = max((max_x - min_x) * 0.05, 1e-6)
    padding_y = max((max_y - min_y) * 0.05, 1e-6)
    return min_x - padding_x, min_y - padding_y, max_x + padding_x, max_y + padding_y


def _project(
    longitude: float,
    latitude: float,
    bounds: tuple[float, float, float, float],
    width: float,
    height: float,
) -> tuple[float, float]:
    min_x, min_y, max_x, max_y = bounds
    left = _world_x(min_x)
    right = _world_x(max_x)
    top = _world_y(max_y)
    bottom = _world_y(min_y)
    return (
        (_world_x(longitude) - left) / (right - left) * width,
        (bottom - _world_y(latitude)) / (bottom - top) * height,
    )


def _build_basemap_image(
    data: DashboardData,
    tile_fetcher: TileFetcher,
    *,
    width: int,
    height: int,
) -> Image.Image | None:
    bounds = _map_bounds(data)
    if bounds is None:
        return None
    min_lon, min_lat, max_lon, max_lat = bounds
    zoom = _tile_zoom(bounds, width, height)
    world_size = TILE_SIZE * (2**zoom)
    left = _world_x(min_lon) * world_size
    right = _world_x(max_lon) * world_size
    top = _world_y(max_lat) * world_size
    bottom = _world_y(min_lat) * world_size
    min_tile_x = math.floor(left / TILE_SIZE)
    max_tile_x = math.floor((right - 1e-9) / TILE_SIZE)
    min_tile_y = math.floor(top / TILE_SIZE)
    max_tile_y = math.floor((bottom - 1e-9) / TILE_SIZE)
    tile_coordinates = [
        (tile_x, tile_y)
        for tile_y in range(min_tile_y, max_tile_y + 1)
        for tile_x in range(min_tile_x, max_tile_x + 1)
    ]
    urls = [_tile_url(zoom, tile_x, tile_y) for tile_x, tile_y in tile_coordinates]
    with ThreadPoolExecutor(max_workers=min(8, len(urls))) as executor:
        tile_bytes = tuple(executor.map(tile_fetcher, urls))
    if any(content is None for content in tile_bytes):
        return None

    mosaic = Image.new(
        "RGB",
        (
            (max_tile_x - min_tile_x + 1) * TILE_SIZE,
            (max_tile_y - min_tile_y + 1) * TILE_SIZE,
        ),
        color="white",
    )
    try:
        for (tile_x, tile_y), content in zip(tile_coordinates, tile_bytes, strict=True):
            assert content is not None
            with Image.open(BytesIO(content)) as tile:
                mosaic.paste(
                    tile.convert("RGB"),
                    ((tile_x - min_tile_x) * TILE_SIZE, (tile_y - min_tile_y) * TILE_SIZE),
                )
        crop = mosaic.crop(
            (
                round(left - min_tile_x * TILE_SIZE),
                round(top - min_tile_y * TILE_SIZE),
                round(right - min_tile_x * TILE_SIZE),
                round(bottom - min_tile_y * TILE_SIZE),
            )
        )
        return crop.resize((width, height), Image.Resampling.LANCZOS)
    except (OSError, ValueError):
        return None


def _tile_zoom(
    bounds: tuple[float, float, float, float],
    width: int,
    height: int,
) -> int:
    min_lon, min_lat, max_lon, max_lat = bounds
    chosen = 0
    for zoom in range(MAX_TILE_ZOOM + 1):
        world_size = TILE_SIZE * (2**zoom)
        span_x = (_world_x(max_lon) - _world_x(min_lon)) * world_size
        span_y = (_world_y(min_lat) - _world_y(max_lat)) * world_size
        if span_x > width or span_y > height:
            break
        chosen = zoom
    return chosen


def _tile_url(zoom: int, tile_x: int, tile_y: int) -> str:
    subdomain = "abcd"[(tile_x + tile_y) % 4]
    return f"https://{subdomain}.basemaps.cartocdn.com/light_nolabels/{zoom}/{tile_x}/{tile_y}.png"


@lru_cache(maxsize=256)
def _fetch_tile(url: str) -> bytes | None:
    try:
        response = requests.get(url, timeout=3)
        response.raise_for_status()
        return response.content
    except requests.RequestException:
        return None


def _world_x(longitude: float) -> float:
    return (longitude + 180.0) / 360.0


def _world_y(latitude: float) -> float:
    clipped = min(max(latitude, -85.05112878), 85.05112878)
    sine = math.sin(math.radians(clipped))
    return 0.5 - math.log((1 + sine) / (1 - sine)) / (4 * math.pi)
