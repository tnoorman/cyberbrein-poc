from cyberbrein.presentation.app import (
    _active_filter_count,
    _clear_deleted_round_state,
    _clear_result_state,
    _frequency_label,
    _short_network_id,
)
from cyberbrein.presentation.models import DashboardFilters


def test_deleted_round_state_discards_selection_pdf_and_confirmation() -> None:
    state = {
        "selected_network_id": "private-network-id",
        "pdf_preview": b"private-pdf",
        "pdf_preview_key": ("round-a",),
        "show_pdf_dialog": True,
        "show_delete_dialog": True,
        "confirm_delete_round-a": True,
        "unrelated": "preserved",
    }

    _clear_deleted_round_state(state, "round-a")

    assert state == {"unrelated": "preserved"}


def test_filter_count_counts_active_filter_groups() -> None:
    filters = DashboardFilters(
        bands=frozenset({"2.4GHz", "5GHz"}),
        channels=frozenset({1, 6}),
        score_colors=frozenset({"YELLOW"}),
    )

    assert _active_filter_count(filters) == 3


def test_filter_change_discards_stale_result_state() -> None:
    state = {
        "selected_network_id": "private-network-id",
        "pdf_preview": b"private-pdf",
        "pdf_preview_key": ("round-a",),
        "show_pdf_dialog": True,
        "applied_filters": DashboardFilters(),
    }

    _clear_result_state(state)

    assert state == {"applied_filters": DashboardFilters()}


def test_detail_labels_shorten_identifier_and_handle_unknown_frequency() -> None:
    assert _short_network_id("abcdefghijklmnop") == "abcdefghijkl…"
    assert _short_network_id("short") == "short"
    assert _frequency_label(5180) == "5180 MHz"
    assert _frequency_label(None) == "Onbekend"
