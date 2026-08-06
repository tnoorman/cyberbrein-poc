import stat
from pathlib import Path

from .models import PipelineRuntimeError


def cleanup_runtime_inputs(
    source_path: Path,
    secret_path: Path,
    *,
    missing_ok: bool = False,
) -> None:
    """Delete raw SQLite files and the secret only after verified processing."""
    sidecars = tuple(
        source_path.with_name(f"{source_path.name}{suffix}")
        for suffix in ("-journal", "-wal", "-shm")
    )
    required = (source_path, secret_path)
    optional = tuple(path for path in sidecars if path.exists() or path.is_symlink())
    existing_required: list[Path] = []
    try:
        for path in required:
            try:
                file_status = path.lstat()
            except FileNotFoundError:
                if missing_ok:
                    continue
                raise
            if stat.S_ISLNK(file_status.st_mode) or not stat.S_ISREG(file_status.st_mode):
                raise PipelineRuntimeError("cleanup_failed")
            existing_required.append(path)
        for path in optional:
            file_status = path.lstat()
            if stat.S_ISLNK(file_status.st_mode) or not stat.S_ISREG(file_status.st_mode):
                raise PipelineRuntimeError("cleanup_failed")
        for path in (*optional, *existing_required):
            path.unlink()
        if any(path.exists() for path in (*optional, *existing_required)):
            raise PipelineRuntimeError("cleanup_failed")
    except PipelineRuntimeError:
        raise
    except OSError as error:
        raise PipelineRuntimeError("cleanup_failed") from error
