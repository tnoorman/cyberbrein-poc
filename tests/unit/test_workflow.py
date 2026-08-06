from pathlib import Path

import pytest

from cyberbrein import workflow


def _write_zone_file(path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        """{
            "type": "FeatureCollection",
            "features": [{
                "type": "Feature",
                "properties": {"zone_id": "test-zone"},
                "geometry": {
                    "type": "Polygon",
                    "coordinates": [[[0, 0], [1, 0], [1, 1], [0, 1], [0, 0]]]
                }
            }]
        }""",
        encoding="utf-8",
    )


def test_run_sequences_collection_pipeline_and_dashboard(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.chdir(tmp_path)
    zones = tmp_path / "data/local/zones.geojson"
    _write_zone_file(zones)
    monkeypatch.setenv("CYBERBREIN_INTERFACE", "wlan-test")
    monkeypatch.setenv("CYBERBREIN_DATABASE_URL", "postgresql+psycopg2:///test")
    monkeypatch.setattr(workflow, "_gps_quality_ready", lambda max_accuracy: True)
    monkeypatch.setattr(workflow, "_monitor_interface_ready", lambda interface: True)
    commands: list[list[str]] = []
    modes: list[tuple[int, int]] = []
    directory_modes: list[tuple[int, int]] = []

    def fake_run(command: list[str], **_: object) -> subprocess_result:
        commands.append(command)
        if "cyberbrein.collection" in command:
            source = tmp_path / "data/smoke/test-round.sqlite"
            secret = tmp_path / "data/local/test-round.secret"
            modes.append((source.stat().st_mode & 0o777, secret.stat().st_mode & 0o777))
            directory_modes.append(
                (source.parent.stat().st_mode & 0o777, secret.parent.stat().st_mode & 0o777)
            )
        return subprocess_result(0)

    monkeypatch.setattr(workflow.subprocess, "run", fake_run)

    assert workflow.main(["run", "--round-id", "test-round"]) == 0

    assert "cyberbrein.collection" in commands[0]
    assert "--no-auto-monitor" in commands[0]
    assert commands[0][:2] == ["sudo", str(Path(workflow.sys.executable).absolute())]
    assert commands[0][1] != str(Path(workflow.sys.executable).resolve())
    assert "cyberbrein.pipeline" in commands[1]
    assert "--delete-source-on-success" in commands[1]
    assert commands[2][2:4] == ["streamlit", "run"]
    assert modes == [(0o600, 0o600)]
    assert directory_modes == [(0o700, 0o700)]


def test_runtime_directory_symlink_is_rejected(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.chdir(tmp_path)
    real_local = tmp_path / "real-local"
    real_local.mkdir()
    data = tmp_path / "data"
    data.mkdir()
    (data / "local").symlink_to(real_local, target_is_directory=True)
    _write_zone_file(real_local / "zones.geojson")
    monkeypatch.setenv("CYBERBREIN_INTERFACE", "wlan-test")
    monkeypatch.setattr(workflow, "_gps_quality_ready", lambda max_accuracy: True)
    monkeypatch.setattr(workflow, "_monitor_interface_ready", lambda interface: True)

    assert workflow.main(["run", "--round-id", "unsafe-directory"]) == 2
    assert not (tmp_path / "data/smoke/unsafe-directory.sqlite").exists()
    assert not (real_local / "unsafe-directory.secret").exists()


def test_collection_failure_removes_empty_runtime_inputs(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.chdir(tmp_path)
    _write_zone_file(tmp_path / "data/local/zones.geojson")
    monkeypatch.setenv("CYBERBREIN_INTERFACE", "wlan-test")
    monkeypatch.setattr(workflow, "_gps_quality_ready", lambda max_accuracy: True)
    monkeypatch.setattr(workflow, "_monitor_interface_ready", lambda interface: True)
    monkeypatch.setattr(
        workflow.subprocess,
        "run",
        lambda *_args, **_kwargs: subprocess_result(2),
    )

    assert workflow.main(["run", "--round-id", "failed-round"]) == 2
    assert not (tmp_path / "data/smoke/failed-round.sqlite").exists()
    assert not (tmp_path / "data/local/failed-round.secret").exists()


def test_collection_failure_keeps_nonempty_buffer_for_recovery(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.chdir(tmp_path)
    _write_zone_file(tmp_path / "data/local/zones.geojson")
    monkeypatch.setenv("CYBERBREIN_INTERFACE", "wlan-test")
    monkeypatch.setattr(workflow, "_gps_quality_ready", lambda max_accuracy: True)
    monkeypatch.setattr(workflow, "_monitor_interface_ready", lambda interface: True)

    def failed_collection(command: list[str], **_: object) -> subprocess_result:
        source_index = command.index("--database-path") + 1
        source = Path(command[source_index])
        source.write_bytes(b"captured-data")
        return subprocess_result(2)

    monkeypatch.setattr(workflow.subprocess, "run", failed_collection)

    assert workflow.main(["run", "--round-id", "recoverable-round"]) == 2
    assert (tmp_path / "data/smoke/recoverable-round.sqlite").exists()
    assert (tmp_path / "data/local/recoverable-round.secret").exists()


def test_invalid_zone_file_stops_before_runtime_inputs_are_created(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.chdir(tmp_path)
    zone_path = tmp_path / "data/local/zones.geojson"
    zone_path.parent.mkdir(parents=True)
    zone_path.write_text('{"type":"FeatureCollection","features":[]}', encoding="utf-8")
    monkeypatch.setenv("CYBERBREIN_INTERFACE", "wlan-test")

    with pytest.raises(SystemExit, match="2"):
        workflow.main(["run", "--round-id", "invalid-zone-round"])

    assert not (tmp_path / "data/smoke/invalid-zone-round.sqlite").exists()
    assert not (tmp_path / "data/local/invalid-zone-round.secret").exists()


def test_unusable_live_gps_stops_before_runtime_inputs_are_created(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.chdir(tmp_path)
    _write_zone_file(tmp_path / "data/local/zones.geojson")
    monkeypatch.setenv("CYBERBREIN_INTERFACE", "wlan-test")
    monkeypatch.setattr(workflow, "_gps_quality_ready", lambda max_accuracy: False)
    monkeypatch.setattr(workflow, "_monitor_interface_ready", lambda interface: True)

    assert workflow.main(["run", "--round-id", "bad-gps-round"]) == 2
    assert not (tmp_path / "data/smoke/bad-gps-round.sqlite").exists()
    assert not (tmp_path / "data/local/bad-gps-round.secret").exists()


def test_dashboard_command_does_not_create_runtime_inputs(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("CYBERBREIN_DATABASE_URL", "postgresql+psycopg2:///test")
    commands: list[list[str]] = []

    def fake_run(command: list[str], **_: object) -> subprocess_result:
        commands.append(command)
        return subprocess_result(0)

    monkeypatch.setattr(workflow.subprocess, "run", fake_run)

    assert workflow.main(["dashboard", "--port", "9000"]) == 0
    assert commands[0][2:4] == ["streamlit", "run"]
    assert commands[0][-4:] == ["--server.port", "9000", "--server.headless", "true"]
    assert not (tmp_path / "data").exists()


def test_resume_processes_existing_inputs_without_collection(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.chdir(tmp_path)
    _write_zone_file(tmp_path / "data/local/zones.geojson")
    source = tmp_path / "data/smoke/resume-round.sqlite"
    source.parent.mkdir(parents=True)
    source.write_bytes(b"preserved")
    source.chmod(0o600)
    secret = tmp_path / "data/local/resume-round.secret"
    secret.write_text("s" * 64, encoding="utf-8")
    secret.chmod(0o600)
    commands: list[list[str]] = []

    def fake_run(command: list[str], **_: object) -> subprocess_result:
        commands.append(command)
        return subprocess_result(0)

    monkeypatch.setattr(workflow.subprocess, "run", fake_run)

    assert workflow.main(["resume", "resume-round", "--no-dashboard"]) == 0
    assert len(commands) == 1
    assert "cyberbrein.pipeline" in commands[0]
    assert "cyberbrein.collection" not in commands[0]


def test_unusable_buffer_is_not_presented_as_recoverable(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    monkeypatch.chdir(tmp_path)
    _write_zone_file(tmp_path / "data/local/zones.geojson")
    source = tmp_path / "data/smoke/unusable-round.sqlite"
    source.parent.mkdir(parents=True)
    source.write_bytes(b"preserved")
    source.chmod(0o600)
    secret = tmp_path / "data/local/unusable-round.secret"
    secret.write_text("s" * 64, encoding="utf-8")
    secret.chmod(0o600)
    monkeypatch.setattr(
        workflow.subprocess,
        "run",
        lambda *_args, **_kwargs: subprocess_result(workflow.UNUSABLE_SOURCE_EXIT),
    )

    assert workflow.main(["resume", "unusable-round", "--no-dashboard"]) == 5

    output = capsys.readouterr().out
    assert "discard unusable-round --yes" in output
    assert "resume unusable-round" not in output


def test_verified_storage_with_incomplete_cleanup_is_not_reprocessed(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    monkeypatch.chdir(tmp_path)
    _write_zone_file(tmp_path / "data/local/zones.geojson")
    source = tmp_path / "data/smoke/stored-round.sqlite"
    source.parent.mkdir(parents=True)
    source.write_bytes(b"preserved")
    source.chmod(0o600)
    secret = tmp_path / "data/local/stored-round.secret"
    secret.write_text("s" * 64, encoding="utf-8")
    secret.chmod(0o600)
    monkeypatch.setattr(
        workflow.subprocess,
        "run",
        lambda *_args, **_kwargs: subprocess_result(workflow.CLEANUP_EXIT),
    )

    assert workflow.main(["resume", "stored-round", "--no-dashboard"]) == 4

    output = capsys.readouterr().out
    assert "opgeslagen en geverifieerd" in output
    assert "dashboard" in output
    assert "discard stored-round --yes" in output
    assert "resume stored-round" not in output


@pytest.mark.parametrize("missing", ("source", "secret"))
def test_discard_finishes_partial_cleanup(
    missing: str,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.chdir(tmp_path)
    source = tmp_path / "data/smoke/partial-round.sqlite"
    source.parent.mkdir(parents=True)
    source.write_bytes(b"raw")
    source.chmod(0o600)
    secret = tmp_path / "data/local/partial-round.secret"
    secret.parent.mkdir(parents=True)
    secret.write_text("s" * 64, encoding="utf-8")
    secret.chmod(0o600)
    (source if missing == "source" else secret).unlink()

    assert workflow.main(["discard", "partial-round", "--yes"]) == 0
    assert not source.exists()
    assert not secret.exists()


def test_discard_deletes_explicitly_confirmed_runtime_inputs(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.chdir(tmp_path)
    source = tmp_path / "data/smoke/discard-round.sqlite"
    source.parent.mkdir(parents=True)
    source.write_bytes(b"raw")
    source.chmod(0o600)
    secret = tmp_path / "data/local/discard-round.secret"
    secret.parent.mkdir(parents=True)
    secret.write_text("s" * 64, encoding="utf-8")
    secret.chmod(0o600)

    assert workflow.main(["discard", "discard-round", "--yes"]) == 0

    assert not source.exists()
    assert not secret.exists()


def test_subprocess_keyboard_interrupt_returns_130(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    def interrupt(*_args: object, **_kwargs: object) -> subprocess_result:
        raise KeyboardInterrupt

    monkeypatch.setattr(workflow.subprocess, "run", interrupt)

    assert workflow._run(["synthetic"], {}) == 130
    assert "gecontroleerde afsluiting" in capsys.readouterr().err


def test_root_invocation_is_rejected_before_starting_subprocess(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(workflow.os, "geteuid", lambda: 0)
    monkeypatch.setattr(
        workflow.subprocess,
        "run",
        lambda *_args, **_kwargs: pytest.fail("subprocess must not start as root"),
    )

    assert workflow.main(["dashboard"]) == 2


@pytest.mark.parametrize(
    "round_id",
    (
        "../escape",
        "nested/round",
        "round with spaces",
        "a" * 129,
    ),
)
def test_unsafe_round_id_is_rejected_before_runtime_inputs(
    round_id: str,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.chdir(tmp_path)
    _write_zone_file(tmp_path / "data/local/zones.geojson")
    monkeypatch.setenv("CYBERBREIN_INTERFACE", "wlan-test")

    with pytest.raises(SystemExit, match="2"):
        workflow.main(["run", "--round-id", round_id])

    assert not (tmp_path / "data/smoke").exists()


def test_missing_program_returns_127(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    monkeypatch.setattr(
        workflow.subprocess,
        "run",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(FileNotFoundError),
    )

    assert workflow._run(["missing-program"], {}) == 127
    assert "Benodigd programma niet gevonden" in capsys.readouterr().err


@pytest.mark.parametrize("port", ("0", "65536"))
def test_dashboard_rejects_invalid_port_before_starting_subprocess(
    port: str,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        workflow.subprocess,
        "run",
        lambda *_args, **_kwargs: pytest.fail("subprocess must not start"),
    )

    with pytest.raises(SystemExit, match="2"):
        workflow.main(["dashboard", "--port", port])


def test_dashboard_rejects_non_postgresql_storage(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("CYBERBREIN_DATABASE_URL", "sqlite:///unsafe.db")
    monkeypatch.setattr(
        workflow.subprocess,
        "run",
        lambda *_args, **_kwargs: pytest.fail("subprocess must not start"),
    )

    with pytest.raises(SystemExit, match="2"):
        workflow.main(["dashboard"])


def test_persistent_monitor_preflight_stops_before_runtime_inputs(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.chdir(tmp_path)
    _write_zone_file(tmp_path / "data/local/zones.geojson")
    monkeypatch.setenv("CYBERBREIN_INTERFACE", "wlan-test")
    monkeypatch.setattr(workflow, "_monitor_interface_ready", lambda interface: False)
    monkeypatch.setattr(
        workflow,
        "_gps_quality_ready",
        lambda accuracy: pytest.fail("GPS must not be checked before interface readiness"),
    )

    assert workflow.main(["run", "--round-id", "monitor-not-ready"]) == 2
    assert not (tmp_path / "data/smoke/monitor-not-ready.sqlite").exists()
    assert not (tmp_path / "data/local/monitor-not-ready.secret").exists()


def test_temporary_lifecycle_keeps_automatic_monitor_switching(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.chdir(tmp_path)
    _write_zone_file(tmp_path / "data/local/zones.geojson")
    monkeypatch.setenv("CYBERBREIN_INTERFACE", "wlan-test")
    monkeypatch.setattr(workflow, "_gps_quality_ready", lambda max_accuracy: True)
    commands: list[list[str]] = []

    def fake_run(command: list[str], **_: object) -> subprocess_result:
        commands.append(command)
        return subprocess_result(0)

    monkeypatch.setattr(workflow.subprocess, "run", fake_run)

    assert (
        workflow.main(
            [
                "run",
                "--round-id",
                "temporary-round",
                "--interface-lifecycle",
                "temporary",
                "--no-dashboard",
            ]
        )
        == 0
    )
    assert "--no-auto-monitor" not in commands[0]


def test_setup_monitor_requires_root(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("CYBERBREIN_INTERFACE", "wlan-test")
    monkeypatch.setattr(workflow.os, "geteuid", lambda: 1000)

    assert workflow.main(["setup-monitor"]) == 2


def test_setup_monitor_runs_privileged_provisioner(monkeypatch: pytest.MonkeyPatch) -> None:
    lifecycle: list[str] = []

    class FakeProvisioner:
        def __init__(self, interface: str, management_interface: str) -> None:
            assert interface == "wlan-test"
            assert management_interface == "wlan0"

        def setup(self) -> None:
            lifecycle.append("setup")

        def teardown(self) -> None:
            lifecycle.append("teardown")

    monkeypatch.setattr(workflow.os, "geteuid", lambda: 0)
    monkeypatch.setattr(workflow, "MonitorProvisioner", FakeProvisioner)

    assert workflow.main(["setup-monitor", "--interface", "wlan-test"]) == 0
    assert workflow.main(["teardown-monitor", "--interface", "wlan-test"]) == 0
    assert lifecycle == ["setup", "teardown"]


def test_monitor_interface_ready_accepts_only_monitor_mode(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    monkeypatch.setattr(
        workflow.subprocess,
        "run",
        lambda *args, **kwargs: subprocess_result(0, "Interface wlan1\n\ttype monitor\n"),
    )
    assert workflow._monitor_interface_ready("wlan1") is True

    monkeypatch.setattr(
        workflow.subprocess,
        "run",
        lambda *args, **kwargs: subprocess_result(0, "Interface wlan1\n\ttype managed\n"),
    )
    assert workflow._monitor_interface_ready("wlan1") is False
    assert "setup-monitor --interface wlan1" in capsys.readouterr().err


class subprocess_result:
    def __init__(self, returncode: int, stdout: str = "") -> None:
        self.returncode = returncode
        self.stdout = stdout
