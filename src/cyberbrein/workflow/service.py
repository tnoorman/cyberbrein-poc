import os
import secrets
import stat
import sys
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from pathlib import Path

from cyberbrein.collection.buffer import is_empty_source_buffer
from cyberbrein.pipeline.exit_codes import CLEANUP_EXIT, UNUSABLE_SOURCE_EXIT
from cyberbrein.pipeline.models import PipelineRuntimeError
from cyberbrein.pipeline.runtime_inputs import cleanup_runtime_inputs

CommandRunner = Callable[[Sequence[str], dict[str, str]], int]
GpsCheck = Callable[[float], bool]
MonitorCheck = Callable[[str], bool]


@dataclass(frozen=True, slots=True)
class WorkflowEvent:
    name: str
    round_id: str


EventHandler = Callable[[WorkflowEvent], None]


@dataclass(frozen=True, slots=True)
class RunRequest:
    round_id: str
    interface: str
    interface_lifecycle: str
    channels: str
    duration: float
    zones_path: Path
    max_gps_accuracy: float
    database_url: str
    no_dashboard: bool
    address: str
    port: int


@dataclass(frozen=True, slots=True)
class ResumeRequest:
    round_id: str
    zones_path: Path
    max_gps_accuracy: float
    database_url: str
    no_dashboard: bool
    address: str
    port: int


@dataclass(frozen=True, slots=True)
class RoundOutcome:
    exit_code: int
    round_id: str | None = None
    guidance: str = ""
    source_path: Path | None = None
    secret_path: Path | None = None
    detail: str | None = None


class WorkflowService:
    def __init__(
        self,
        command_runner: CommandRunner,
        gps_check: GpsCheck,
        monitor_check: MonitorCheck,
        event_handler: EventHandler | None = None,
    ) -> None:
        self._command_runner = command_runner
        self._gps_check = gps_check
        self._monitor_check = monitor_check
        self._event_handler = event_handler or (lambda _event: None)

    def run(self, request: RunRequest) -> RoundOutcome:
        source_path, secret_path = round_paths(request.round_id)
        if request.interface_lifecycle == "persistent-monitor" and not self._monitor_check(
            request.interface
        ):
            return RoundOutcome(2, request.round_id)
        if not self._gps_check(request.max_gps_accuracy):
            return RoundOutcome(2, request.round_id)

        try:
            create_runtime_inputs(source_path, secret_path)
        except OSError as error:
            return RoundOutcome(
                2,
                request.round_id,
                "runtime_creation_failed",
                source_path,
                secret_path,
                str(error),
            )

        environment = _environment(request.database_url)
        collection_command = [
            "sudo",
            _python_executable(),
            "-m",
            "cyberbrein.collection",
            "--interface",
            request.interface,
            "--database-path",
            str(source_path),
            "--measurement-round-id",
            request.round_id,
            "--channels",
            request.channels,
            "--duration",
            str(request.duration),
            "--gpsd",
            "--require-gps-fix",
            "--max-gps-accuracy",
            str(request.max_gps_accuracy),
        ]
        if request.interface_lifecycle == "persistent-monitor":
            collection_command.append("--no-auto-monitor")
        self._event_handler(WorkflowEvent("round_started", request.round_id))
        collection_exit = self._command_runner(collection_command, environment)
        if collection_exit != 0:
            guidance = (
                "empty_attempt" if cleanup_empty_attempt(source_path, secret_path) else "recovery"
            )
            return RoundOutcome(
                collection_exit,
                request.round_id,
                guidance,
                source_path,
                secret_path,
            )

        return self._process_round(
            ResumeRequest(
                round_id=request.round_id,
                zones_path=request.zones_path,
                max_gps_accuracy=request.max_gps_accuracy,
                database_url=request.database_url,
                no_dashboard=request.no_dashboard,
                address=request.address,
                port=request.port,
            )
        )

    def resume(self, request: ResumeRequest) -> RoundOutcome:
        return self._process_round(request)

    def dashboard(self, address: str, port: int, database_url: str) -> RoundOutcome:
        environment = _environment(database_url)
        app_path = Path(__file__).resolve().parents[1] / "presentation/app.py"
        command = [
            _python_executable(),
            "-m",
            "streamlit",
            "run",
            str(app_path),
            "--server.address",
            address,
            "--server.port",
            str(port),
            "--server.headless",
            "true",
        ]
        return RoundOutcome(self._command_runner(command, environment))

    def discard(self, round_id: str) -> RoundOutcome:
        source_path, secret_path = round_paths(round_id)
        try:
            cleanup_runtime_inputs(source_path, secret_path, missing_ok=True)
        except PipelineRuntimeError:
            return RoundOutcome(
                2,
                round_id,
                "discard_failed",
                source_path,
                secret_path,
            )
        return RoundOutcome(0, round_id, "discarded", source_path, secret_path)

    def _process_round(self, request: ResumeRequest) -> RoundOutcome:
        source_path, secret_path = round_paths(request.round_id)
        environment = _environment(request.database_url)
        pipeline_command = [
            _python_executable(),
            "-m",
            "cyberbrein.pipeline",
            "--source-db",
            str(source_path),
            "--measurement-round-id",
            request.round_id,
            "--zones",
            str(request.zones_path),
            "--secret-file",
            str(secret_path),
            "--max-gps-accuracy",
            str(request.max_gps_accuracy),
            "--delete-source-on-success",
        ]
        pipeline_exit = self._command_runner(pipeline_command, environment)
        if pipeline_exit != 0:
            guidance = "recovery"
            if pipeline_exit == CLEANUP_EXIT:
                guidance = "incomplete_cleanup"
            elif pipeline_exit == UNUSABLE_SOURCE_EXIT:
                guidance = "unusable"
            return RoundOutcome(
                pipeline_exit,
                request.round_id,
                guidance,
                source_path,
                secret_path,
            )

        outcome = RoundOutcome(
            0,
            request.round_id,
            "processed",
            source_path,
            secret_path,
        )
        if request.no_dashboard:
            return outcome
        dashboard_outcome = self.dashboard(request.address, request.port, request.database_url)
        return RoundOutcome(
            dashboard_outcome.exit_code,
            request.round_id,
            "processed",
            source_path,
            secret_path,
        )


def round_paths(round_id: str) -> tuple[Path, Path]:
    return (
        Path("data/smoke") / f"{round_id}.sqlite",
        Path("data/local") / f"{round_id}.secret",
    )


def create_runtime_inputs(source_path: Path, secret_path: Path) -> None:
    ensure_private_directory(source_path.parent)
    ensure_private_directory(secret_path.parent)
    if source_path.exists() or secret_path.exists():
        raise FileExistsError("runtimebestanden voor deze meetronde bestaan al")

    source_descriptor = os.open(source_path, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
    os.close(source_descriptor)
    try:
        secret_descriptor = os.open(secret_path, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
        with os.fdopen(secret_descriptor, "w", encoding="utf-8") as stream:
            stream.write(secrets.token_hex(32))
            stream.write("\n")
    except BaseException:
        source_path.unlink(missing_ok=True)
        secret_path.unlink(missing_ok=True)
        raise


def ensure_private_directory(path: Path) -> None:
    path.mkdir(mode=0o700, parents=True, exist_ok=True)
    directory_status = path.lstat()
    if stat.S_ISLNK(directory_status.st_mode) or not stat.S_ISDIR(directory_status.st_mode):
        raise OSError(f"unsafe runtime directory: {path}")
    path.chmod(0o700)


def cleanup_empty_attempt(source_path: Path, secret_path: Path) -> bool:
    """Remove launcher-owned inputs only when the buffer contains no observations."""
    try:
        if source_path.is_symlink() or secret_path.is_symlink():
            return False
        if not source_path.is_file() or not secret_path.is_file():
            return False
        if is_empty_source_buffer(source_path) is not True:
            return False
        source_path.unlink()
        secret_path.unlink()
        return True
    except OSError:
        return False


def _environment(database_url: str) -> dict[str, str]:
    environment = dict(os.environ)
    environment["CYBERBREIN_DATABASE_URL"] = database_url
    return environment


def _python_executable() -> str:
    """Keep the virtualenv path; resolving its symlink would bypass the environment."""
    return str(Path(sys.executable).absolute())
