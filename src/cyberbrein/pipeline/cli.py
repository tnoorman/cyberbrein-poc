import argparse
import math
import os
import stat
import sys
from collections.abc import Sequence
from pathlib import Path

from .exit_codes import CLEANUP_EXIT, CONFIGURATION_EXIT, PIPELINE_EXIT, UNUSABLE_SOURCE_EXIT
from .models import PipelineResult, PipelineRuntimeError
from .runtime_config import RuntimeConfigurationError, load_approved_zones, load_secret
from .runtime_inputs import cleanup_runtime_inputs
from .service import PipelineService


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Safely process one Collection buffer into verified PostGIS storage."
    )
    parser.add_argument("--source-db", required=True, help="Temporary Collection SQLite buffer.")
    parser.add_argument("--measurement-round-id", required=True, help="Expected measurement round.")
    parser.add_argument("--zones", required=True, help="Approved WGS84 GeoJSON zones.")
    parser.add_argument("--secret-file", required=True, help="Mode-600 measurement-round secret.")
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
    storage_database_url = os.environ.get("CYBERBREIN_DATABASE_URL", "")
    try:
        _validate_source_path(source_path)
        zones = load_approved_zones(args.zones)
        secret = load_secret(secret_path)
        _validate_database_url(storage_database_url)
    except RuntimeConfigurationError as error:
        _print_failure(error.category)
        return CONFIGURATION_EXIT

    try:
        result = PipelineService().run(
            source_database_path=source_path,
            measurement_round_id=args.measurement_round_id,
            zones=zones,
            secret=secret,
            storage_database_url=storage_database_url,
            max_gps_accuracy_m=args.max_gps_accuracy,
        )
    except PipelineRuntimeError as error:
        _print_failure(error.category)
        return UNUSABLE_SOURCE_EXIT if error.category == "no_usable_observations" else PIPELINE_EXIT

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


def _validate_source_path(source_path: Path) -> None:
    try:
        source_status = source_path.lstat()
        if (
            stat.S_ISLNK(source_status.st_mode)
            or not stat.S_ISREG(source_status.st_mode)
            or stat.S_IMODE(source_status.st_mode) != 0o600
        ):
            raise RuntimeConfigurationError("invalid_source_buffer")
    except RuntimeConfigurationError:
        raise
    except OSError as error:
        raise RuntimeConfigurationError("invalid_source_buffer") from error


def _validate_database_url(database_url: str) -> None:
    if not database_url.startswith(("postgresql://", "postgresql+psycopg2://")):
        raise RuntimeConfigurationError("invalid_storage_configuration")


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
