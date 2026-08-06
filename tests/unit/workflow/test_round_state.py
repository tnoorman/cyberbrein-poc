import json
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

from cyberbrein.workflow.round_state import (
    ALLOWED_TRANSITIONS,
    RoundPaths,
    RoundRecord,
    RoundState,
    RoundStateError,
    RoundStateStore,
)

DIGEST = "a" * 64
NOW = datetime(2026, 8, 6, 10, 0, tzinfo=timezone.utc)


def _record(state: RoundState = RoundState.PREPARED) -> RoundRecord:
    return RoundRecord(
        round_id="state-round",
        state=state,
        created_at_utc=NOW,
        updated_at_utc=NOW,
        max_gps_accuracy_m=15.0,
        zones_sha256=DIGEST,
    )


def test_round_paths_reject_unsafe_identifier() -> None:
    with pytest.raises(RoundStateError, match="invalid_measurement_round_id"):
        RoundPaths.for_round("../escape")


def test_record_rejects_invalid_intrinsic_values() -> None:
    with pytest.raises(RoundStateError, match="invalid_round_state"):
        RoundRecord(
            round_id="state-round",
            state=RoundState.PREPARED,
            created_at_utc=NOW.replace(tzinfo=None),
            updated_at_utc=NOW,
            max_gps_accuracy_m=15.0,
            zones_sha256=DIGEST,
        )
    with pytest.raises(RoundStateError, match="invalid_round_state"):
        RoundRecord(
            round_id="state-round",
            state=RoundState.PREPARED,
            created_at_utc=NOW,
            updated_at_utc=NOW,
            max_gps_accuracy_m=15.0,
            zones_sha256="not-a-digest",
        )


def test_store_round_trips_mode_600_record(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.chdir(tmp_path)
    (tmp_path / "data/local").mkdir(parents=True)
    store = RoundStateStore()

    store.create(_record())

    path = RoundPaths.for_round("state-round").state_record
    assert path.stat().st_mode & 0o777 == 0o600
    assert store.load("state-round") == _record()
    assert not path.with_name(f".{path.name}.tmp").exists()


@pytest.mark.parametrize("from_state,to_state", sorted(ALLOWED_TRANSITIONS))
def test_store_allows_declared_transitions(
    from_state: RoundState,
    to_state: RoundState,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.chdir(tmp_path)
    (tmp_path / "data/local").mkdir(parents=True)
    later = NOW + timedelta(seconds=1)
    store = RoundStateStore(clock=lambda: later)
    store.create(_record(from_state))

    updated = store.transition("state-round", to_state, last_exit_code=4)

    assert updated.state is to_state
    assert updated.updated_at_utc == later
    assert updated.last_exit_code == 4


def test_store_rejects_undeclared_transition(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.chdir(tmp_path)
    (tmp_path / "data/local").mkdir(parents=True)
    store = RoundStateStore()
    store.create(_record())

    with pytest.raises(RoundStateError, match="invalid_round_transition"):
        store.transition("state-round", RoundState.STORED_UNCLEANED)


def test_corrupt_or_permissive_record_fails_closed(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.chdir(tmp_path)
    path = tmp_path / "data/local/state-round.round.json"
    path.parent.mkdir(parents=True)
    path.write_text("{broken", encoding="utf-8")
    path.chmod(0o600)
    store = RoundStateStore()

    with pytest.raises(RoundStateError, match="invalid_round_state"):
        store.load("state-round")

    path.write_text(json.dumps({}), encoding="utf-8")
    path.chmod(0o644)
    with pytest.raises(RoundStateError, match="invalid_round_state"):
        store.load("state-round")


def test_missing_record_is_legacy_and_delete_can_be_idempotent(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.chdir(tmp_path)
    store = RoundStateStore()

    assert store.load("legacy-round") is None
    store.delete("legacy-round", missing_ok=True)
