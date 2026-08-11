import hashlib
import os
import secrets
import stat
import sys
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

from cyberbrein.collection.buffer import is_empty_source_buffer
from cyberbrein.pipeline.exit_codes import CLEANUP_EXIT, UNUSABLE_SOURCE_EXIT
from cyberbrein.pipeline.models import PipelineRuntimeError
from cyberbrein.pipeline.runtime_config import RuntimeConfigurationError, load_approved_zones
from cyberbrein.pipeline.runtime_inputs import cleanup_runtime_inputs

from .round_state import RoundPaths, RoundRecord, RoundState, RoundStateError, RoundStateStore

CommandRunner = Callable[[Sequence[str], dict[str, str]], int]
GpsCheck = Callable[[float], bool]
MonitorCheck = Callable[[str], bool]
RetainedRoundCheck = Callable[[str], bool]


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
    policy_override_requested: bool = False


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
        retained_round_check: RetainedRoundCheck,
        event_handler: EventHandler | None = None,
        state_store: RoundStateStore | None = None,
        clock: Callable[[], datetime] | None = None,
    ) -> None:
        self._command_runner = command_runner
        self._gps_check = gps_check
        self._monitor_check = monitor_check
        self._retained_round_check = retained_round_check
        self._event_handler = event_handler or (lambda _event: None)
        self._clock = clock or (lambda: datetime.now(timezone.utc))
        self._state_store = state_store or RoundStateStore(self._clock)

    def run(self, request: RunRequest) -> RoundOutcome:
        paths = RoundPaths.for_round(request.round_id)
        try:
            if self._retained_round_check(request.database_url):
                return RoundOutcome(2, request.round_id, "retained_round_exists")
        except Exception:
            return RoundOutcome(2, request.round_id, "storage_preflight_failed")
        if request.interface_lifecycle == "persistent-monitor" and not self._monitor_check(
            request.interface
        ):
            return RoundOutcome(2, request.round_id)
        if not self._gps_check(request.max_gps_accuracy):
            return RoundOutcome(2, request.round_id)

        try:
            create_runtime_bundle(
                paths,
                request.zones_path,
                request.max_gps_accuracy,
                self._state_store,
                self._clock(),
            )
        except (OSError, RoundStateError, RuntimeConfigurationError) as error:
            detail = error.category if hasattr(error, "category") else str(error)
            return RoundOutcome(
                2,
                request.round_id,
                "runtime_creation_failed",
                paths.source,
                paths.secret,
                detail,
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
            str(paths.source),
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
            guidance = "recovery"
            if cleanup_empty_attempt(paths.source, paths.secret):
                try:
                    cleanup_policy_inputs(paths, self._state_store)
                    guidance = "empty_attempt"
                except (OSError, RoundStateError):
                    guidance = "empty_cleanup_failed"
            return RoundOutcome(
                collection_exit,
                request.round_id,
                guidance,
                paths.source,
                paths.secret,
            )

        try:
            self._state_store.transition(request.round_id, RoundState.COLLECTED)
        except RoundStateError as error:
            return RoundOutcome(
                2,
                request.round_id,
                "round_state_failed",
                paths.source,
                paths.secret,
                error.category,
            )

        return self._process_round(
            ResumeRequest(
                round_id=request.round_id,
                zones_path=paths.zones_snapshot,
                max_gps_accuracy=request.max_gps_accuracy,
                database_url=request.database_url,
                no_dashboard=request.no_dashboard,
                address=request.address,
                port=request.port,
            ),
            managed_state=True,
        )

    def resume(self, request: ResumeRequest) -> RoundOutcome:
        paths = RoundPaths.for_round(request.round_id)
        try:
            record = self._state_store.load(request.round_id)
        except RoundStateError as error:
            return _state_failure(request.round_id, paths, error.category)

        if record is None:
            if paths.zones_snapshot.exists() or paths.zones_snapshot.is_symlink():
                return _state_failure(request.round_id, paths, "orphaned_zone_snapshot")
            if not preserved_inputs_ready(paths):
                return RoundOutcome(
                    2,
                    request.round_id,
                    "preserved_inputs_missing",
                    paths.source,
                    paths.secret,
                )
            try:
                load_approved_zones(request.zones_path)
            except RuntimeConfigurationError:
                return RoundOutcome(
                    2,
                    request.round_id,
                    "legacy_policy_invalid",
                    paths.source,
                    paths.secret,
                )
            return self._process_round(request, managed_state=False)
        if record.state is RoundState.UNUSABLE:
            return RoundOutcome(
                2,
                request.round_id,
                "unusable",
                paths.source,
                paths.secret,
            )
        if record.state is RoundState.STORED_UNCLEANED:
            return RoundOutcome(
                2,
                request.round_id,
                "incomplete_cleanup",
                paths.source,
                paths.secret,
            )
        if request.policy_override_requested:
            return RoundOutcome(
                2,
                request.round_id,
                "policy_override_rejected",
                paths.source,
                paths.secret,
            )
        if not preserved_inputs_ready(paths):
            return RoundOutcome(
                2,
                request.round_id,
                "preserved_inputs_missing",
                paths.source,
                paths.secret,
            )
        try:
            verify_pinned_policy(paths, record)
            if record.state is RoundState.PREPARED:
                record = self._state_store.transition(request.round_id, RoundState.COLLECTED)
        except RoundStateError as error:
            return _state_failure(request.round_id, paths, error.category)
        except (OSError, RuntimeConfigurationError):
            return _state_failure(request.round_id, paths, "invalid_zone_snapshot")

        return self._process_round(
            ResumeRequest(
                round_id=request.round_id,
                zones_path=paths.zones_snapshot,
                max_gps_accuracy=record.max_gps_accuracy_m,
                database_url=request.database_url,
                no_dashboard=request.no_dashboard,
                address=request.address,
                port=request.port,
            ),
            managed_state=True,
        )

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
        paths = RoundPaths.for_round(round_id)
        try:
            cleanup_runtime_inputs(paths.source, paths.secret, missing_ok=True)
            cleanup_policy_inputs(paths, self._state_store)
        except (OSError, PipelineRuntimeError, RoundStateError):
            return RoundOutcome(
                2,
                round_id,
                "discard_failed",
                paths.source,
                paths.secret,
            )
        return RoundOutcome(0, round_id, "discarded", paths.source, paths.secret)

    def _process_round(self, request: ResumeRequest, *, managed_state: bool) -> RoundOutcome:
        paths = RoundPaths.for_round(request.round_id)
        environment = _environment(request.database_url)
        pipeline_command = [
            _python_executable(),
            "-m",
            "cyberbrein.pipeline",
            "--source-db",
            str(paths.source),
            "--measurement-round-id",
            request.round_id,
            "--zones",
            str(request.zones_path),
            "--secret-file",
            str(paths.secret),
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
            if managed_state and pipeline_exit in {CLEANUP_EXIT, UNUSABLE_SOURCE_EXIT}:
                target_state = (
                    RoundState.STORED_UNCLEANED
                    if pipeline_exit == CLEANUP_EXIT
                    else RoundState.UNUSABLE
                )
                try:
                    self._state_store.transition(
                        request.round_id,
                        target_state,
                        last_exit_code=pipeline_exit,
                    )
                except RoundStateError as error:
                    return RoundOutcome(
                        2,
                        request.round_id,
                        "round_state_failed",
                        paths.source,
                        paths.secret,
                        error.category,
                    )
            return RoundOutcome(
                pipeline_exit,
                request.round_id,
                guidance,
                paths.source,
                paths.secret,
            )

        if managed_state:
            try:
                self._state_store.transition(
                    request.round_id,
                    RoundState.STORED_UNCLEANED,
                    last_exit_code=0,
                )
                cleanup_policy_inputs(paths, self._state_store)
            except (OSError, RoundStateError):
                return RoundOutcome(
                    CLEANUP_EXIT,
                    request.round_id,
                    "incomplete_cleanup",
                    paths.source,
                    paths.secret,
                )

        outcome = RoundOutcome(
            0,
            request.round_id,
            "processed",
            paths.source,
            paths.secret,
        )
        if request.no_dashboard:
            return outcome
        dashboard_outcome = self.dashboard(request.address, request.port, request.database_url)
        return RoundOutcome(
            dashboard_outcome.exit_code,
            request.round_id,
            "processed",
            paths.source,
            paths.secret,
        )


def round_paths(round_id: str) -> tuple[Path, Path]:
    paths = RoundPaths.for_round(round_id)
    return paths.source, paths.secret


def create_runtime_bundle(
    paths: RoundPaths,
    zones_path: Path,
    max_gps_accuracy: float,
    state_store: RoundStateStore,
    created_at: datetime,
) -> None:
    ensure_private_directory(paths.source.parent)
    ensure_private_directory(paths.secret.parent)
    for path in (paths.source, paths.secret, paths.zones_snapshot, paths.state_record):
        if path.exists() or path.is_symlink():
            raise FileExistsError("runtimebestanden voor deze meetronde bestaan al")

    try:
        _create_empty_file(paths.source)
        _create_secret(paths.secret)
        zones_sha256 = snapshot_approved_zones(zones_path, paths.zones_snapshot)
        timestamp = created_at.astimezone(timezone.utc)
        state_store.create(
            RoundRecord(
                round_id=paths.source.stem,
                state=RoundState.PREPARED,
                created_at_utc=timestamp,
                updated_at_utc=timestamp,
                max_gps_accuracy_m=max_gps_accuracy,
                zones_sha256=zones_sha256,
            )
        )
    except BaseException:
        for path in (paths.source, paths.secret, paths.zones_snapshot):
            path.unlink(missing_ok=True)
        state_store.delete(paths.source.stem, missing_ok=True)
        raise


def snapshot_approved_zones(source: Path, destination: Path) -> str:
    source_descriptor: int | None = None
    destination_descriptor: int | None = None
    try:
        source_descriptor = os.open(
            source,
            os.O_RDONLY | getattr(os, "O_CLOEXEC", 0) | getattr(os, "O_NOFOLLOW", 0),
        )
        source_status = os.fstat(source_descriptor)
        if not stat.S_ISREG(source_status.st_mode):
            raise RuntimeConfigurationError("invalid_zone_file")
        with os.fdopen(source_descriptor, "rb") as stream:
            source_descriptor = None
            payload = stream.read()
        destination_descriptor = os.open(
            destination,
            os.O_CREAT | os.O_EXCL | os.O_WRONLY | getattr(os, "O_NOFOLLOW", 0),
            0o600,
        )
        with os.fdopen(destination_descriptor, "wb") as stream:
            destination_descriptor = None
            stream.write(payload)
            stream.flush()
            os.fsync(stream.fileno())
        load_approved_zones(destination)
        return hashlib.sha256(payload).hexdigest()
    except RuntimeConfigurationError:
        destination.unlink(missing_ok=True)
        raise
    except OSError as error:
        destination.unlink(missing_ok=True)
        raise RuntimeConfigurationError("invalid_zone_file") from error
    finally:
        if source_descriptor is not None:
            os.close(source_descriptor)
        if destination_descriptor is not None:
            os.close(destination_descriptor)


def verify_pinned_policy(paths: RoundPaths, record: RoundRecord) -> None:
    try:
        snapshot_status = paths.zones_snapshot.lstat()
        if (
            stat.S_ISLNK(snapshot_status.st_mode)
            or not stat.S_ISREG(snapshot_status.st_mode)
            or stat.S_IMODE(snapshot_status.st_mode) != 0o600
        ):
            raise RoundStateError("invalid_zone_snapshot")
        payload = paths.zones_snapshot.read_bytes()
    except RoundStateError:
        raise
    except OSError as error:
        raise RoundStateError("invalid_zone_snapshot") from error
    if hashlib.sha256(payload).hexdigest() != record.zones_sha256:
        raise RoundStateError("zone_snapshot_mismatch")
    load_approved_zones(paths.zones_snapshot)


def cleanup_policy_inputs(paths: RoundPaths, state_store: RoundStateStore) -> None:
    if paths.zones_snapshot.exists() or paths.zones_snapshot.is_symlink():
        snapshot_status = paths.zones_snapshot.lstat()
        if stat.S_ISLNK(snapshot_status.st_mode) or not stat.S_ISREG(snapshot_status.st_mode):
            raise RoundStateError("invalid_zone_snapshot")
        paths.zones_snapshot.unlink()
    state_store.delete(paths.source.stem, missing_ok=True)


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


def preserved_inputs_ready(paths: RoundPaths) -> bool:
    return (
        paths.source.is_file()
        and not paths.source.is_symlink()
        and paths.secret.is_file()
        and not paths.secret.is_symlink()
    )


def ensure_private_directory(path: Path) -> None:
    path.mkdir(mode=0o700, parents=True, exist_ok=True)
    directory_status = path.lstat()
    if stat.S_ISLNK(directory_status.st_mode) or not stat.S_ISDIR(directory_status.st_mode):
        raise OSError(f"unsafe runtime directory: {path}")
    path.chmod(0o700)


def _create_empty_file(path: Path) -> None:
    descriptor = os.open(path, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
    os.close(descriptor)


def _create_secret(path: Path) -> None:
    descriptor = os.open(path, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
    with os.fdopen(descriptor, "w", encoding="utf-8") as stream:
        stream.write(secrets.token_hex(32))
        stream.write("\n")


def _state_failure(round_id: str, paths: RoundPaths, detail: str) -> RoundOutcome:
    return RoundOutcome(
        2,
        round_id,
        "invalid_round_state",
        paths.source,
        paths.secret,
        detail,
    )


def _environment(database_url: str) -> dict[str, str]:
    environment = dict(os.environ)
    environment["CYBERBREIN_DATABASE_URL"] = database_url
    return environment


def _python_executable() -> str:
    """Keep the virtualenv path; resolving its symlink would bypass the environment."""
    return str(Path(sys.executable).absolute())
