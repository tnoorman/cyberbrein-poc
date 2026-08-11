from pathlib import Path

import pytest

from cyberbrein.pipeline.exit_codes import CLEANUP_EXIT
from cyberbrein.workflow.round_state import RoundPaths, RoundState, RoundStateStore
from cyberbrein.workflow.service import ResumeRequest, RunRequest, WorkflowEvent, WorkflowService


def _write_zones(path: Path) -> None:
    path.write_text(
        '{"type":"FeatureCollection","features":[{"type":"Feature",'
        '"properties":{"zone_id":"zone-a"},"geometry":{"type":"Polygon",'
        '"coordinates":[[[0,0],[1,0],[1,1],[0,1],[0,0]]]}}]}',
        encoding="utf-8",
    )


def _run_request(tmp_path: Path) -> RunRequest:
    _write_zones(tmp_path / "zones.geojson")
    return RunRequest(
        round_id="service-round",
        interface="wlan-test",
        interface_lifecycle="persistent-monitor",
        channels="36,40",
        duration=30.0,
        zones_path=tmp_path / "zones.geojson",
        max_gps_accuracy=15.0,
        database_url="postgresql+psycopg2:///test",
        no_dashboard=True,
        address="127.0.0.1",
        port=8501,
    )


def test_run_uses_injected_boundaries_and_emits_start_event(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.chdir(tmp_path)
    commands: list[list[str]] = []
    events: list[WorkflowEvent] = []

    def run_command(command: list[str], _environment: dict[str, str]) -> int:
        commands.append(command)
        return 0

    service = WorkflowService(
        command_runner=run_command,
        gps_check=lambda accuracy: accuracy == 15.0,
        monitor_check=lambda interface: interface == "wlan-test",
        retained_round_check=lambda _url: False,
        event_handler=events.append,
    )

    outcome = service.run(_run_request(tmp_path))

    assert outcome.exit_code == 0
    assert outcome.guidance == "processed"
    assert events == [WorkflowEvent("round_started", "service-round")]
    assert "cyberbrein.collection" in commands[0]
    assert "--no-auto-monitor" in commands[0]
    assert "cyberbrein.pipeline" in commands[1]


def test_failed_preflight_does_not_create_runtime_inputs(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.chdir(tmp_path)
    service = WorkflowService(
        command_runner=lambda *_args: pytest.fail("command must not run"),
        gps_check=lambda _accuracy: pytest.fail("GPS must follow monitor preflight"),
        monitor_check=lambda _interface: False,
        retained_round_check=lambda _url: False,
    )

    outcome = service.run(_run_request(tmp_path))

    assert outcome.exit_code == 2
    assert not (tmp_path / "data").exists()


def test_retained_storage_round_stops_before_device_preflights_and_runtime_creation(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.chdir(tmp_path)
    service = WorkflowService(
        command_runner=lambda *_args: pytest.fail("command must not run"),
        gps_check=lambda _accuracy: pytest.fail("GPS must not run"),
        monitor_check=lambda _interface: pytest.fail("monitor check must not run"),
        retained_round_check=lambda url: url.endswith("/test"),
    )

    outcome = service.run(_run_request(tmp_path))

    assert outcome.exit_code == 2
    assert outcome.guidance == "retained_round_exists"
    assert not (tmp_path / "data").exists()


def test_unavailable_storage_preflight_fails_closed_before_runtime_creation(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.chdir(tmp_path)

    def unavailable(_url: str) -> bool:
        raise RuntimeError("private database detail")

    service = WorkflowService(
        command_runner=lambda *_args: pytest.fail("command must not run"),
        gps_check=lambda _accuracy: pytest.fail("GPS must not run"),
        monitor_check=lambda _interface: pytest.fail("monitor check must not run"),
        retained_round_check=unavailable,
    )

    outcome = service.run(_run_request(tmp_path))

    assert outcome.exit_code == 2
    assert outcome.guidance == "storage_preflight_failed"
    assert outcome.detail is None
    assert not (tmp_path / "data").exists()


def test_resume_invokes_pipeline_without_collection(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.chdir(tmp_path)
    _write_zones(tmp_path / "zones.geojson")
    source = tmp_path / "data/smoke/resume-round.sqlite"
    source.parent.mkdir(parents=True)
    source.write_bytes(b"preserved")
    secret = tmp_path / "data/local/resume-round.secret"
    secret.parent.mkdir(parents=True)
    secret.write_text("s" * 64, encoding="utf-8")
    commands: list[list[str]] = []

    def run_command(command: list[str], _environment: dict[str, str]) -> int:
        commands.append(command)
        return 0

    service = WorkflowService(
        command_runner=run_command,
        gps_check=lambda _accuracy: True,
        monitor_check=lambda _interface: True,
        retained_round_check=lambda _url: False,
    )
    outcome = service.resume(
        ResumeRequest(
            round_id="resume-round",
            zones_path=tmp_path / "zones.geojson",
            max_gps_accuracy=15.0,
            database_url="postgresql+psycopg2:///test",
            no_dashboard=True,
            address="127.0.0.1",
            port=8501,
        )
    )

    assert outcome.exit_code == 0
    assert len(commands) == 1
    assert "cyberbrein.pipeline" in commands[0]
    assert "cyberbrein.collection" not in commands[0]


def test_resume_uses_pinned_policy_after_original_zone_file_changes(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.chdir(tmp_path)
    commands: list[list[str]] = []

    def interrupt_collection(command: list[str], _environment: dict[str, str]) -> int:
        source = Path(command[command.index("--database-path") + 1])
        source.write_bytes(b"captured")
        return 2

    service = WorkflowService(
        command_runner=interrupt_collection,
        gps_check=lambda _accuracy: True,
        monitor_check=lambda _interface: True,
        retained_round_check=lambda _url: False,
    )
    assert service.run(_run_request(tmp_path)).exit_code == 2
    paths = RoundPaths.for_round("service-round")
    original_snapshot = paths.zones_snapshot.read_bytes()
    (tmp_path / "zones.geojson").write_text(
        (tmp_path / "zones.geojson").read_text(encoding="utf-8").replace("zone-a", "zone-b"),
        encoding="utf-8",
    )

    def fail_pipeline(command: list[str], _environment: dict[str, str]) -> int:
        commands.append(command)
        return 3

    resumed = WorkflowService(
        command_runner=fail_pipeline,
        gps_check=lambda _accuracy: True,
        monitor_check=lambda _interface: True,
        retained_round_check=lambda _url: False,
    ).resume(
        ResumeRequest(
            round_id="service-round",
            zones_path=tmp_path / "zones.geojson",
            max_gps_accuracy=25.0,
            database_url="postgresql+psycopg2:///test",
            no_dashboard=True,
            address="127.0.0.1",
            port=8501,
        )
    )

    assert resumed.exit_code == 3
    assert paths.zones_snapshot.read_bytes() == original_snapshot
    pipeline = commands[0]
    assert pipeline[pipeline.index("--zones") + 1] == str(paths.zones_snapshot)
    assert pipeline[pipeline.index("--max-gps-accuracy") + 1] == "15.0"


def test_pinned_round_rejects_explicit_policy_override(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.chdir(tmp_path)

    def interrupt_collection(command: list[str], _environment: dict[str, str]) -> int:
        Path(command[command.index("--database-path") + 1]).write_bytes(b"captured")
        return 2

    service = WorkflowService(
        command_runner=interrupt_collection,
        gps_check=lambda _accuracy: True,
        monitor_check=lambda _interface: True,
        retained_round_check=lambda _url: False,
    )
    assert service.run(_run_request(tmp_path)).exit_code == 2

    outcome = service.resume(
        ResumeRequest(
            round_id="service-round",
            zones_path=tmp_path / "zones.geojson",
            max_gps_accuracy=25.0,
            database_url="postgresql+psycopg2:///test",
            no_dashboard=True,
            address="127.0.0.1",
            port=8501,
            policy_override_requested=True,
        )
    )

    assert outcome.exit_code == 2
    assert outcome.guidance == "policy_override_rejected"


def test_corrupt_zone_snapshot_fails_closed(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.chdir(tmp_path)

    def interrupt_collection(command: list[str], _environment: dict[str, str]) -> int:
        Path(command[command.index("--database-path") + 1]).write_bytes(b"captured")
        return 2

    service = WorkflowService(
        command_runner=interrupt_collection,
        gps_check=lambda _accuracy: True,
        monitor_check=lambda _interface: True,
        retained_round_check=lambda _url: False,
    )
    assert service.run(_run_request(tmp_path)).exit_code == 2
    RoundPaths.for_round("service-round").zones_snapshot.write_bytes(b"swapped")

    outcome = service.resume(
        ResumeRequest(
            round_id="service-round",
            zones_path=tmp_path / "zones.geojson",
            max_gps_accuracy=15.0,
            database_url="postgresql+psycopg2:///test",
            no_dashboard=True,
            address="127.0.0.1",
            port=8501,
        )
    )

    assert outcome.exit_code == 2
    assert outcome.guidance == "invalid_round_state"
    assert outcome.detail == "zone_snapshot_mismatch"


def test_stored_uncleaned_round_cannot_resume_and_can_be_discarded(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.chdir(tmp_path)
    command_count = 0

    def incomplete_cleanup(_command: list[str], _environment: dict[str, str]) -> int:
        nonlocal command_count
        command_count += 1
        return 0 if command_count == 1 else CLEANUP_EXIT

    service = WorkflowService(
        command_runner=incomplete_cleanup,
        gps_check=lambda _accuracy: True,
        monitor_check=lambda _interface: True,
        retained_round_check=lambda _url: False,
    )
    assert service.run(_run_request(tmp_path)).exit_code == CLEANUP_EXIT
    assert RoundStateStore().load("service-round").state is RoundState.STORED_UNCLEANED
    RoundPaths.for_round("service-round").source.unlink()

    outcome = service.resume(
        ResumeRequest(
            round_id="service-round",
            zones_path=tmp_path / "zones.geojson",
            max_gps_accuracy=15.0,
            database_url="postgresql+psycopg2:///test",
            no_dashboard=True,
            address="127.0.0.1",
            port=8501,
        )
    )
    assert outcome.exit_code == 2
    assert outcome.guidance == "incomplete_cleanup"
    assert command_count == 2

    assert service.discard("service-round").exit_code == 0
    paths = RoundPaths.for_round("service-round")
    assert not paths.zones_snapshot.exists()
    assert not paths.state_record.exists()


def test_active_round_with_missing_preserved_input_fails_before_pipeline(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.chdir(tmp_path)

    def interrupt_collection(command: list[str], _environment: dict[str, str]) -> int:
        Path(command[command.index("--database-path") + 1]).write_bytes(b"captured")
        return 2

    service = WorkflowService(
        command_runner=interrupt_collection,
        gps_check=lambda _accuracy: True,
        monitor_check=lambda _interface: True,
        retained_round_check=lambda _url: False,
    )
    assert service.run(_run_request(tmp_path)).exit_code == 2
    RoundPaths.for_round("service-round").secret.unlink()

    outcome = service.resume(
        ResumeRequest(
            round_id="service-round",
            zones_path=tmp_path / "zones.geojson",
            max_gps_accuracy=15.0,
            database_url="postgresql+psycopg2:///test",
            no_dashboard=True,
            address="127.0.0.1",
            port=8501,
        )
    )

    assert outcome.exit_code == 2
    assert outcome.guidance == "preserved_inputs_missing"
