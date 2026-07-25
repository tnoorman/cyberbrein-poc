import os
import re
from collections.abc import MutableMapping
from pathlib import Path
from typing import Any

import streamlit as st
from sqlalchemy.exc import SQLAlchemyError
from streamlit_folium import st_folium

from cyberbrein.operations.service import ActivityLog, DeletionResult, OperationsService
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
from cyberbrein.presentation.styles import apply_dashboard_styles
from cyberbrein.storage.repository import StorageRepository

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
    st.set_page_config(
        page_title="Cyberbrein Wi-Fi Exposure",
        page_icon="🛡️",
        layout="wide",
    )
    apply_dashboard_styles()
    st.markdown('<div class="cb-eyebrow">Cyberbrein · Wi-Fi exposure</div>', unsafe_allow_html=True)
    st.title("Kaartoverzicht")
    st.caption("Passieve Wi-Fi-waarnemingen binnen de goedgekeurde meetzone")
    database_url = os.environ.get("CYBERBREIN_DATABASE_URL", "")
    if not database_url:
        st.error("De lokale databaseconfiguratie ontbreekt.")
        return

    repository: PresentationRepository | None = None
    try:
        repository = PresentationRepository(database_url)
        rounds = repository.list_measurement_rounds()
        if not rounds:
            deleted_count = st.session_state.pop("deletion_success_count", None)
            if deleted_count is not None:
                st.success(
                    f"De meetronde en {deleted_count} netwerkvondsten zijn definitief verwijderd."
                )
            st.info("Er is nog geen verwerkte meetronde beschikbaar.")
            return
        round_ids = [item.measurement_round_id for item in rounds]
        selected_round = st.session_state.get("active_round_id")
        if selected_round not in round_ids:
            selected_round = round_ids[0]
            st.session_state["active_round_id"] = selected_round
        unfiltered = repository.load_dashboard(selected_round)
        filters = st.session_state.get("applied_filters", DashboardFilters())
        dashboard = repository.load_dashboard(selected_round, filters)
    except (SQLAlchemyError, RuntimeError, ValueError):
        st.error("De dashboarddata kon niet veilig worden geladen.")
        return
    finally:
        if repository is not None:
            repository.close()

    _render_metrics(dashboard)

    context, filter_action, delete_action = st.columns([4, 1, 1], vertical_alignment="center")
    zone_label = ", ".join(zone.zone_id for zone in unfiltered.zones)
    context.markdown(
        f'<div class="cb-context"><strong>{zone_label}</strong> · gemeten gebied</div>',
        unsafe_allow_html=True,
    )
    with filter_action:
        _render_filter_popover(
            round_ids=round_ids,
            selected_round=selected_round,
            options=unfiltered.filter_options,
            filters=filters,
        )
    if delete_action.button("Meetdata verwijderen", type="secondary", width="stretch"):
        st.session_state["show_delete_dialog"] = True
    if st.session_state.get("show_delete_dialog"):
        _render_delete_dialog(
            database_url=database_url,
            measurement_round_id=selected_round,
            finding_count=unfiltered.total_count,
        )

    if not dashboard.findings:
        st.info("Voor deze selectie zijn geen netwerkvondsten beschikbaar.")
    map_result = st_folium(
        build_map(dashboard),
        height=570,
        use_container_width=True,
        returned_objects=["last_object_clicked", "last_object_clicked_tooltip"],
        key=f"map-{selected_round}-{hash(filters)}",
    )
    st.markdown(
        '<div class="cb-privacy-note">ⓘ De kaart toont passieve Wi-Fi-waarnemingen. '
        "De posities zijn indicatief en vormen geen bewezen locatie van een access point. "
        "De ondergrond is bewust labelloos.</div>",
        unsafe_allow_html=True,
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


@st.dialog("Meetdata verwijderen na inzichtverstrekking")
def _render_delete_dialog(
    *,
    database_url: str,
    measurement_round_id: str,
    finding_count: int,
) -> None:
    st.caption("Beheeractie · alleen beschikbaar voor Cyberbrein")
    st.write(
        {
            "Geselecteerde meetronde": measurement_round_id,
            "Netwerkvondsten": finding_count,
        }
    )
    st.error(
        "Verwijdering is definitief. Deze meetdata kan na verwijdering niet worden hersteld. "
        "Voer dit pas uit nadat de inzichten zijn gedeeld."
    )
    confirmation_key = f"confirm_delete_{measurement_round_id}"
    confirmed = st.checkbox(
        "Ik bevestig dat de inzichten zijn verstrekt en dat deze meetdata permanent verwijderd "
        "mag worden.",
        key=confirmation_key,
    )
    cancel, delete_column = st.columns(2)
    if cancel.button("Annuleren", width="stretch"):
        st.session_state.pop("show_delete_dialog", None)
        st.rerun()
    if delete_column.button(
        "Bevestig verwijdering",
        type="primary",
        disabled=not confirmed,
        width="stretch",
    ):
        try:
            result = _delete_measurement_round(
                database_url=database_url,
                activity_log_path=Path(
                    os.environ.get(
                        "CYBERBREIN_ACTIVITY_LOG_PATH",
                        "data/logs/operations.jsonl",
                    )
                ),
                measurement_round_id=measurement_round_id,
            )
        except Exception:
            st.error(
                "De meetdata kon niet aantoonbaar worden verwijderd. "
                "Controleer het activiteitenlog en Storage."
            )
            return
        _clear_deleted_round_state(st.session_state, measurement_round_id)
        st.session_state["deletion_success_count"] = result.deleted_findings
        st.rerun()


def _delete_measurement_round(
    *,
    database_url: str,
    activity_log_path: Path,
    measurement_round_id: str,
) -> DeletionResult:
    repository = StorageRepository(database_url)
    try:
        return OperationsService(
            repository,
            ActivityLog(activity_log_path),
        ).delete_measurement_round(measurement_round_id)
    finally:
        repository.close()


def _clear_deleted_round_state(
    state: MutableMapping[str, Any],
    measurement_round_id: str,
) -> None:
    for key in (
        "selected_network_id",
        "pdf_preview",
        "pdf_preview_key",
        "show_delete_dialog",
        f"confirm_delete_{measurement_round_id}",
    ):
        state.pop(key, None)


def _render_filter_popover(
    *,
    round_ids: list[str],
    selected_round: str,
    options: FilterOptions,
    filters: DashboardFilters,
) -> None:
    active_count = _active_filter_count(filters)
    label = f"Filters ({active_count})" if active_count else "Filters"
    with st.popover(label, width="stretch"):
        st.subheader("Filters")
        st.caption("Verfijn de kaart op veilige categorieën en klassen.")
        with st.form("dashboard_filters"):
            staged_round = st.selectbox(
                "Meetronde",
                round_ids,
                index=round_ids.index(selected_round),
            )
            bands = st.multiselect("Band", options.bands, default=sorted(filters.bands))
            encryptions = st.multiselect(
                "Encryptietype",
                options.encryptions,
                default=sorted(filters.encryptions),
            )
            score_colors = st.pills(
                "Scorekleur",
                options.score_colors,
                default=sorted(filters.score_colors),
                selection_mode="multi",
                format_func=lambda value: COLOR_LABELS[value],
            )
            signal_categories = st.segmented_control(
                "Signaalsterkte",
                options.signal_categories,
                default=sorted(filters.signal_categories),
                selection_mode="multi",
                format_func=lambda value: SIGNAL_LABELS[value],
                width="stretch",
            )
            with st.expander("Meer filters"):
                zone_ids = st.multiselect(
                    "Zone",
                    options.zone_ids,
                    default=sorted(filters.zone_ids),
                )
                channels = st.multiselect(
                    "Kanaal",
                    options.channels,
                    default=sorted(filters.channels),
                )
            reset, apply = st.columns(2)
            reset_clicked = reset.form_submit_button("Filters wissen", width="stretch")
            apply_clicked = apply.form_submit_button(
                "Filters toepassen",
                type="primary",
                width="stretch",
            )
        if reset_clicked:
            st.session_state["active_round_id"] = staged_round
            st.session_state["applied_filters"] = DashboardFilters()
            _clear_result_state(st.session_state)
            st.rerun()
        if apply_clicked:
            st.session_state["active_round_id"] = staged_round
            st.session_state["applied_filters"] = DashboardFilters(
                zone_ids=frozenset(zone_ids),
                bands=frozenset(bands),
                channels=frozenset(channels),
                encryptions=frozenset(encryptions),
                score_colors=frozenset(score_colors or ()),
                signal_categories=frozenset(signal_categories or ()),
            )
            _clear_result_state(st.session_state)
            st.rerun()


def _active_filter_count(filters: DashboardFilters) -> int:
    return sum(
        bool(values)
        for values in (
            filters.zone_ids,
            filters.bands,
            filters.channels,
            filters.encryptions,
            filters.score_colors,
            filters.signal_categories,
        )
    )


def _clear_result_state(state: MutableMapping[str, Any]) -> None:
    for key in ("selected_network_id", "pdf_preview", "pdf_preview_key"):
        state.pop(key, None)


def _render_metrics(dashboard: DashboardData) -> None:
    columns = st.columns(3)
    metrics = (
        ("Netwerkvondsten", dashboard.total_count),
        ("Verhoogde aandacht", dashboard.elevated_count),
        ("Hoge aandacht", dashboard.high_count),
    )
    for column, (label, value) in zip(columns, metrics, strict=True):
        with column:
            with st.container(border=True):
                st.metric(label, value)


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
    st.dataframe(factor_rows, hide_index=True, width="stretch")
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
