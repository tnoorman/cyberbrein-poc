import argparse
import math
import stat
import sys
from collections.abc import Sequence
from pathlib import Path

from .models import PipelineResult, PipelineRuntimeError
from .runtime_config import RuntimeConfigurationError, load_approved_zones, load_secret
from .service import PipelineService

CONFIGURATION_EXIT = 2
PIPELINE_EXIT = 3
CLEANUP_EXIT = 4


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Safely process one Collection buffer into verified SQLite storage."
    )
    parser.add_argument("--source-db", required=True, help="Temporary Collection SQLite buffer.")
    parser.add_argument("--measurement-round-id", required=True, help="Expected measurement round.")
    parser.add_argument("--zones", required=True, help="Approved WGS84 GeoJSON zones.")
    parser.add_argument("--secret-file", required=True, help="Mode-600 measurement-round secret.")
    parser.add_argument("--storage-db", required=True, help="Processed SQLite storage path.")
    parser.add_argument(
        "--max-gps-accuracy",
        type=float,
        default=15.0,
        help="Maximum accepted GPS accuracy in metres (default: 15).",
    )
    parser.add_argument(
        "--delete-source-on-success",
        action="store_true",
        help="Delete the raw SQLite buffer, its sidecars, and the secret after verified storage.",
    )
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    if (
        not math.isfinite(args.max_gps_accuracy)
        or args.max_gps_accuracy < 0
        or not args.measurement_round_id.strip()
    ):
        parser.error("--max-gps-accuracy must be finite and non-negative; round ID is required")

    source_path = Path(args.source_db)
    secret_path = Path(args.secret_file)
    storage_path = Path(args.storage_db)
    try:
        _validate_runtime_paths(source_path, storage_path)
        zones = load_approved_zones(args.zones)
        secret = load_secret(secret_path)
    except RuntimeConfigurationError as error:
        _print_failure(error.category)
        return CONFIGURATION_EXIT

    try:
        result = PipelineService().run(
            source_database_path=source_path,
            measurement_round_id=args.measurement_round_id,
            zones=zones,
            secret=secret,
            storage_database_path=storage_path,
            max_gps_accuracy_m=args.max_gps_accuracy,
        )
    except PipelineRuntimeError as error:
        _print_failure(error.category)
        return PIPELINE_EXIT

    _print_result(result)
    if args.delete_source_on_success:
        try:
            cleanup_runtime_inputs(source_path, secret_path)
        except PipelineRuntimeError as error:
            _print_failure(error.category)
            return CLEANUP_EXIT
        print("Ruwe invoer verwijderd: ja")
    else:
        print("Ruwe invoer verwijderd: nee")
    return 0


def cleanup_runtime_inputs(source_path: Path, secret_path: Path) -> None:
    """Delete raw SQLite files and the secret only after verified processing."""
    sidecars = tuple(
        source_path.with_name(f"{source_path.name}{suffix}")
        for suffix in ("-journal", "-wal", "-shm")
    )
    required = (source_path, secret_path)
    optional = tuple(path for path in sidecars if path.exists() or path.is_symlink())
    try:
        for path in (*required, *optional):
            file_status = path.lstat()
            if stat.S_ISLNK(file_status.st_mode) or not stat.S_ISREG(file_status.st_mode):
                raise PipelineRuntimeError("cleanup_failed")
        for path in (*optional, source_path, secret_path):
            path.unlink()
        if any(path.exists() for path in (*optional, source_path, secret_path)):
            raise PipelineRuntimeError("cleanup_failed")
    except PipelineRuntimeError:
        raise
    except OSError as error:
        raise PipelineRuntimeError("cleanup_failed") from error


def _validate_runtime_paths(source_path: Path, storage_path: Path) -> None:
    try:
        source_status = source_path.lstat()
        if (
            stat.S_ISLNK(source_status.st_mode)
            or not stat.S_ISREG(source_status.st_mode)
            or stat.S_IMODE(source_status.st_mode) != 0o600
        ):
            raise RuntimeConfigurationError("invalid_source_buffer")
        if storage_path.exists() or storage_path.is_symlink():
            storage_status = storage_path.lstat()
            if stat.S_ISLNK(storage_status.st_mode) or not stat.S_ISREG(storage_status.st_mode):
                raise RuntimeConfigurationError("invalid_storage_configuration")
    except RuntimeConfigurationError:
        raise
    except OSError as error:
        raise RuntimeConfigurationError("invalid_source_buffer") from error


def _print_result(result: PipelineResult) -> None:
    print(f"Ingestion geaccepteerd: {result.ingestion_accepted_count}")
    print(f"Ingestion afgewezen: {result.ingestion_rejected_count}")
    print(f"Ingestion redenen: {result.ingestion_rejection_reasons}")
    print(f"Processing geaccepteerd: {result.processing_accepted_count}")
    print(f"Processing afgewezen: {result.processing_rejected_count}")
    print(f"Processing redenen: {result.processing_rejection_reasons}")
    print(f"Netwerkvondsten opgeslagen: {result.finding_count}")
    print("Opslag geverifieerd: ja")


def _print_failure(category: str) -> None:
    print(f"Pipeline mislukt: {category}", file=sys.stderr)
