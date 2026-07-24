import os
import re

import streamlit as st
from sqlalchemy.exc import SQLAlchemyError
from streamlit_folium import st_folium

from cyberbrein.presentation.map_view import (
    build_map,
    finding_from_selection_label,
    findings_at_map_click,
)
from cyberbrein.presentation.models import (
    DashboardData,
    DashboardFilters,
    FilterOptions,
    FindingView,
)
from cyberbrein.presentation.pdf_export import generate_pdf
from cyberbrein.presentation.repository import PresentationRepository

COLOR_LABELS = {
    "GREEN": "Groen – beperkte aandacht",
    "YELLOW": "Geel – verhoogde aandacht",
    "RED": "Rood – hoge aandacht",
}
SIGNAL_LABELS = {
    "weak": "Zwak (< -80 dBm)",
    "medium": "Middel (-80 t/m -67 dBm)",
    "strong": "Sterk (> -67 dBm)",
}
FACTOR_LABELS = {
    "signal_strength": "Signaalsterkte",
    "encryption": "Encryptietype",
    "observation_frequency": "Waarnemingsfrequentie",
}
CATEGORY_LABELS = {
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


def main() -> None:
    st.set_page_config(page_title="Cyberbrein Wi-Fi Exposure", layout="wide")
    st.title("Wi-Fi-exposure per meetronde")
    database_url = os.environ.get("CYBERBREIN_DATABASE_URL", "")
    if not database_url:
        st.error("De lokale databaseconfiguratie ontbreekt.")
        return

    repository: PresentationRepository | None = None
    try:
        repository = PresentationRepository(database_url)
        rounds = repository.list_measurement_rounds()
        if not rounds:
            st.info("Er is nog geen verwerkte meetronde beschikbaar.")
            return
        round_ids = [item.measurement_round_id for item in rounds]
        selected_round = st.sidebar.selectbox("Meetronde", round_ids)
        unfiltered = repository.load_dashboard(selected_round)
        filters = _render_filters(unfiltered.filter_options)
        dashboard = repository.load_dashboard(selected_round, filters)
    except (SQLAlchemyError, RuntimeError, ValueError):
        st.error("De dashboarddata kon niet veilig worden geladen.")
        return
    finally:
        if repository is not None:
            repository.close()

    total, elevated, high = st.columns(3)
    total.metric("Netwerkvondsten", dashboard.total_count)
    elevated.metric("Verhoogde aandacht", dashboard.elevated_count)
    high.metric("Hoge aandacht", dashboard.high_count)

    if not dashboard.findings:
        st.info("Voor deze selectie zijn geen netwerkvondsten beschikbaar.")
    map_result = st_folium(
        build_map(dashboard),
        height=570,
        use_container_width=True,
        returned_objects=["last_object_clicked", "last_object_clicked_tooltip"],
        key=f"map-{selected_round}-{hash(filters)}",
    )
    st.caption(
        "De bolletjes zijn indicatieve netwerkvondsten binnen de meetcontext. "
        "Ze bewijzen niet waar een access point fysiek aanwezig is."
    )

    selected = finding_from_selection_label(
        dashboard.findings,
        map_result.get("last_object_clicked_tooltip") if map_result else None,
    )
    clicked = map_result.get("last_object_clicked") if map_result else None
    if selected is None and clicked:
        matching = findings_at_map_click(
            dashboard.findings,
            latitude=float(clicked["lat"]),
            longitude=float(clicked["lng"]),
            tolerance=1e-6,
        )
        if len(matching) == 1:
            selected = matching[0]
    if selected is not None:
        st.session_state["selected_network_id"] = selected.network_id

    selected_network_id = st.session_state.get("selected_network_id")
    selected = next(
        (finding for finding in dashboard.findings if finding.network_id == selected_network_id),
        None,
    )
    if selected is not None:
        st.success("Netwerkvondst geselecteerd. De details staan direct hieronder.")
        _render_detail(selected)
    _render_pdf_export(dashboard, filters)


def _render_filters(options: FilterOptions) -> DashboardFilters:
    zone_ids = st.sidebar.multiselect("Zone", options.zone_ids)
    bands = st.sidebar.multiselect("Band", options.bands)
    channels = st.sidebar.multiselect("Kanaal", options.channels)
    encryptions = st.sidebar.multiselect("Encryptietype", options.encryptions)
    score_colors = st.sidebar.multiselect(
        "Scorekleur",
        options.score_colors,
        format_func=lambda value: COLOR_LABELS[value],
    )
    signal_categories = st.sidebar.multiselect(
        "Signaalklasse (score)",
        options.signal_categories,
        format_func=lambda value: SIGNAL_LABELS[value],
    )
    return DashboardFilters(
        zone_ids=frozenset(zone_ids),
        bands=frozenset(bands),
        channels=frozenset(channels),
        encryptions=frozenset(encryptions),
        score_colors=frozenset(score_colors),
        signal_categories=frozenset(signal_categories),
    )


def _render_detail(finding: FindingView) -> None:
    st.subheader("Detail netwerkvondst")
    st.code(finding.network_id, language=None)
    score, color = st.columns(2)
    score.metric("Exposure-score", f"{finding.score} / 8")
    color.metric("Scorekleur", COLOR_LABELS[finding.score_color])

    st.write(
        {
            "Zone": finding.zone_id,
            "Band": finding.band,
            "Kanaal": finding.channel,
            "Encryptietype": finding.encryption,
            "Gemiddelde signaalsterkte": f"{finding.average_rssi_dbm:.1f} dBm",
            "Sterkste signaalsterkte": f"{finding.strongest_rssi_dbm} dBm",
            "Aantal waarnemingen": finding.observation_count,
        }
    )
    factor_rows = [
        {
            "Scorefactor": FACTOR_LABELS[factor.factor_type],
            "Waargenomen waarde": factor.observed_value,
            "Categorie": CATEGORY_LABELS[factor.category],
            "Punten": factor.points,
            "Weging": factor.weight,
            "Gewogen punten": factor.weighted_points,
        }
        for factor in finding.factors
    ]
    st.dataframe(factor_rows, hide_index=True, use_container_width=True)
    st.caption(
        "Deze beoordeling gebruikt uitsluitend passief waargenomen metadata en is geen volledig "
        "beveiligingsoordeel."
    )


def _render_pdf_export(dashboard: DashboardData, filters: DashboardFilters) -> None:
    st.divider()
    st.subheader("PDF-preview")
    preview_key = (
        dashboard.measurement_round.measurement_round_id,
        dashboard.findings,
        filters,
    )
    if st.button("Maak PDF-preview", type="primary"):
        try:
            st.session_state["pdf_preview"] = generate_pdf(dashboard, filters)
            st.session_state["pdf_preview_key"] = preview_key
        except Exception:
            st.error(
                "De PDF-preview kon niet veilig worden gemaakt; het dashboard blijft beschikbaar."
            )
    pdf_bytes = st.session_state.get("pdf_preview")
    if pdf_bytes and st.session_state.get("pdf_preview_key") == preview_key:
        st.pdf(pdf_bytes, height=650)
        safe_round_id = re.sub(
            r"[^A-Za-z0-9._-]+",
            "-",
            dashboard.measurement_round.measurement_round_id,
        )
        st.download_button(
            "Download PDF",
            data=pdf_bytes,
            file_name=f"cyberbrein-{safe_round_id}.pdf",
            mime="application/pdf",
        )


if __name__ == "__main__":
    main()
