from cyberbrein.presentation.app import _clear_deleted_round_state


def test_deleted_round_state_discards_selection_pdf_and_confirmation() -> None:
    state = {
        "selected_network_id": "private-network-id",
        "pdf_preview": b"private-pdf",
        "pdf_preview_key": ("round-a",),
        "show_delete_dialog": True,
        "confirm_delete_round-a": True,
        "unrelated": "preserved",
    }

    _clear_deleted_round_state(state, "round-a")

    assert state == {"unrelated": "preserved"}
