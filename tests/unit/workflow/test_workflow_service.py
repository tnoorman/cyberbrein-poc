from pathlib import Path

import pytest

from cyberbrein.workflow.service import ResumeRequest, RunRequest, WorkflowEvent, WorkflowService


def _run_request(tmp_path: Path) -> RunRequest:
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
    )

    outcome = service.run(_run_request(tmp_path))

    assert outcome.exit_code == 2
    assert not (tmp_path / "data").exists()


def test_resume_invokes_pipeline_without_collection(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.chdir(tmp_path)
    commands: list[list[str]] = []

    def run_command(command: list[str], _environment: dict[str, str]) -> int:
        commands.append(command)
        return 0

    service = WorkflowService(
        command_runner=run_command,
        gps_check=lambda _accuracy: True,
        monitor_check=lambda _interface: True,
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
