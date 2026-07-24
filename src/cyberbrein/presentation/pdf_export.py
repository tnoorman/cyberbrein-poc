from io import BytesIO

from reportlab.lib import colors
from reportlab.lib.enums import TA_CENTER
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import mm
from reportlab.platypus import (
    Flowable,
    KeepTogether,
    Paragraph,
    SimpleDocTemplate,
    Spacer,
    Table,
    TableStyle,
)

from .map_view import MARKER_COLORS
from .models import DashboardData, DashboardFilters

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


def generate_pdf(data: DashboardData, filters: DashboardFilters) -> bytes:
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
        _MapDrawing(data, width=170 * mm, height=90 * mm),
        Paragraph(
            "De posities zijn indicatieve netwerkvondsten binnen de meetcontext en bewijzen "
            "niet waar een access point fysiek aanwezig is.",
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
    def __init__(self, data: DashboardData, *, width: float, height: float) -> None:
        super().__init__()
        self.data = data
        self.width = width
        self.height = height

    def draw(self) -> None:
        self.canv.setStrokeColor(colors.HexColor("#90a4ae"))
        self.canv.setFillColor(colors.HexColor("#fafafa"))
        self.canv.rect(0, 0, self.width, self.height, fill=1, stroke=1)
        bounds = _map_bounds(self.data)
        if bounds is None:
            return
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
                self.canv.setStrokeColor(colors.HexColor("#455a64"))
                self.canv.setFillColor(colors.HexColor("#cfd8dc"))
                self.canv.drawPath(path, stroke=1, fill=1, fillMode=0)
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
    return (
        (longitude - min_x) / (max_x - min_x) * width,
        (latitude - min_y) / (max_y - min_y) * height,
    )
