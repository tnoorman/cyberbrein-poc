import argparse
import math
import os
import re
import secrets
import sqlite3
import subprocess
import sys
from collections.abc import Sequence
from datetime import datetime, timezone
from pathlib import Path

from dotenv import load_dotenv

from cyberbrein.collection.gpsd_client import GpsdClient
from cyberbrein.pipeline.cli import UNUSABLE_SOURCE_EXIT, cleanup_runtime_inputs
from cyberbrein.pipeline.models import PipelineRuntimeError
from cyberbrein.pipeline.runtime_config import RuntimeConfigurationError, load_approved_zones

DEFAULT_DATABASE_URL = "postgresql+psycopg2:///cyberbrein_poc"
ROUND_ID_PATTERN = re.compile(r"[A-Za-z0-9][A-Za-z0-9._-]{0,127}")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="cyberbrein", description="Run the Cyberbrein measurement workflow with one command."
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    run = subparsers.add_parser(
        "run",
        help="Collect, process, clean temporary inputs, and start the dashboard.",
    )
    run.add_argument(
        "--interface",
        default=os.environ.get("CYBERBREIN_INTERFACE"),
        help="Dedicated Wi-Fi interface (or set CYBERBREIN_INTERFACE).",
    )
    run.add_argument(
        "--channels",
        default=os.environ.get("CYBERBREIN_CHANNELS", "36,40,44,48"),
        help="Comma-separated collection channels.",
    )
    run.add_argument(
        "--duration",
        type=float,
        default=os.environ.get("CYBERBREIN_DURATION", "60"),
        help="Collection duration in seconds (default: 60).",
    )
    run.add_argument(
        "--zones",
        default=os.environ.get("CYBERBREIN_ZONES", "data/local/zones.geojson"),
        help="Approved GeoJSON zone file.",
    )
    run.add_argument(
        "--max-gps-accuracy",
        type=float,
        default=os.environ.get("CYBERBREIN_MAX_GPS_ACCURACY", "15"),
        help="Maximum accepted GPS accuracy in metres (default: 15).",
    )
    run.add_argument(
        "--round-id",
        help="Optional round ID; a UTC-based ID is generated when omitted.",
    )
    run.add_argument(
        "--no-dashboard",
        action="store_true",
        help="Stop after verified processing instead of starting Streamlit.",
    )
    _add_dashboard_arguments(run)

    resume = subparsers.add_parser(
        "resume",
        help="Process a preserved buffer from an interrupted workflow.",
    )
    resume.add_argument("round_id", help="Measurement round ID shown by the failed workflow.")
    resume.add_argument(
        "--zones",
        default=os.environ.get("CYBERBREIN_ZONES", "data/local/zones.geojson"),
        help="Approved GeoJSON zone file.",
    )
    resume.add_argument(
        "--max-gps-accuracy",
        type=float,
        default=os.environ.get("CYBERBREIN_MAX_GPS_ACCURACY", "15"),
        help="Maximum accepted GPS accuracy in metres (default: 15).",
    )
    resume.add_argument(
        "--no-dashboard",
        action="store_true",
        help="Stop after verified processing instead of starting Streamlit.",
    )
    _add_dashboard_arguments(resume)

    dashboard = subparsers.add_parser("dashboard", help="Start only the local dashboard.")
    _add_dashboard_arguments(dashboard)

    discard = subparsers.add_parser(
        "discard",
        help="Delete one explicitly named preserved raw buffer and its secret.",
    )
    discard.add_argument("round_id", help="Measurement round ID to discard.")
    discard.add_argument(
        "--yes",
        action="store_true",
        help="Confirm permanent deletion of the preserved inputs.",
    )
    return parser


def _add_dashboard_arguments(parser: argparse.ArgumentParser) -> None:
    parser.add_argument(
        "--address",
        default=os.environ.get("CYBERBREIN_DASHBOARD_ADDRESS", "127.0.0.1"),
        help="Dashboard bind address (default: 127.0.0.1).",
    )
    parser.add_argument(
        "--port",
        type=int,
        default=os.environ.get("CYBERBREIN_DASHBOARD_PORT", "8501"),
        help="Dashboard port (default: 8501).",
    )


def main(argv: Sequence[str] | None = None) -> int:
    load_dotenv()
    parser = build_parser()
    args = parser.parse_args(argv)
    if hasattr(os, "geteuid") and os.geteuid() == 0:
        print(
            "Start de launcher zonder sudo: ./cyberbrein "
            f"{args.command}. Alleen Collection vraagt daarna om sudo.",
            file=sys.stderr,
        )
        return 2
    if args.command == "discard":
        return _discard_round(parser, args.round_id, args.yes)

    database_url = os.environ.get("CYBERBREIN_DATABASE_URL", DEFAULT_DATABASE_URL)
    if not database_url.startswith(("postgresql://", "postgresql+psycopg2://")):
        parser.error("CYBERBREIN_DATABASE_URL must point to PostgreSQL/PostGIS")
    if not 1 <= args.port <= 65535:
        parser.error("--port must be between 1 and 65535")

    if args.command == "dashboard":
        return _start_dashboard(args.address, args.port, database_url)

    if args.command == "resume":
        _validate_processing_arguments(parser, args)
        source_path, secret_path, zones_path = _runtime_paths(parser, args.round_id, args.zones)
        if not source_path.is_file() or source_path.is_symlink():
            parser.error(f"preserved source buffer not found: {source_path}")
        if not secret_path.is_file() or secret_path.is_symlink():
            parser.error(f"preserved secret not found: {secret_path}")
        return _process_round(
            round_id=args.round_id,
            source_path=source_path,
            secret_path=secret_path,
            zones_path=zones_path,
            max_gps_accuracy=args.max_gps_accuracy,
            database_url=database_url,
            no_dashboard=args.no_dashboard,
            address=args.address,
            port=args.port,
        )

    _validate_run_arguments(parser, args)
    round_id = args.round_id or _new_round_id()
    source_path, secret_path, zones_path = _runtime_paths(parser, round_id, args.zones)
    if not _gps_quality_ready(args.max_gps_accuracy):
        return 2

    try:
        _create_runtime_inputs(source_path, secret_path)
    except OSError as error:
        print(f"Workflow kon veilige runtimebestanden niet maken: {error}", file=sys.stderr)
        return 2

    environment = os.environ.copy()
    environment["CYBERBREIN_DATABASE_URL"] = database_url
    python = _python_executable()
    collection_command = [
        "sudo",
        python,
        "-m",
        "cyberbrein.collection",
        "--interface",
        args.interface,
        "--database-path",
        str(source_path),
        "--measurement-round-id",
        round_id,
        "--channels",
        args.channels,
        "--duration",
        str(args.duration),
        "--gpsd",
        "--require-gps-fix",
        "--max-gps-accuracy",
        str(args.max_gps_accuracy),
    ]
    print(f"Meetronde gestart: {round_id}")
    collection_exit = _run(collection_command, environment)
    if collection_exit != 0:
        if _cleanup_empty_attempt(source_path, secret_path):
            print("Geen waarnemingen vastgelegd; lege runtimebestanden zijn verwijderd.")
        else:
            _print_recovery(source_path, secret_path)
        return collection_exit

    return _process_round(
        round_id=round_id,
        source_path=source_path,
        secret_path=secret_path,
        zones_path=zones_path,
        max_gps_accuracy=args.max_gps_accuracy,
        database_url=database_url,
        no_dashboard=args.no_dashboard,
        address=args.address,
        port=args.port,
    )


def _process_round(
    *,
    round_id: str,
    source_path: Path,
    secret_path: Path,
    zones_path: Path,
    max_gps_accuracy: float,
    database_url: str,
    no_dashboard: bool,
    address: str,
    port: int,
) -> int:
    environment = os.environ.copy()
    environment["CYBERBREIN_DATABASE_URL"] = database_url
    pipeline_command = [
        _python_executable(),
        "-m",
        "cyberbrein.pipeline",
        "--source-db",
        str(source_path),
        "--measurement-round-id",
        round_id,
        "--zones",
        str(zones_path),
        "--secret-file",
        str(secret_path),
        "--max-gps-accuracy",
        str(max_gps_accuracy),
        "--delete-source-on-success",
    ]
    pipeline_exit = _run(pipeline_command, environment)
    if pipeline_exit != 0:
        if pipeline_exit == UNUSABLE_SOURCE_EXIT:
            _print_unusable(source_path, secret_path)
        else:
            _print_recovery(source_path, secret_path)
        return pipeline_exit

    print("Meetronde verwerkt en tijdelijke invoer veilig verwijderd.")
    if no_dashboard:
        return 0
    return _start_dashboard(address, port, database_url)


def _validate_run_arguments(parser: argparse.ArgumentParser, args: argparse.Namespace) -> None:
    if not args.interface or not args.interface.strip():
        parser.error("--interface is required (or set CYBERBREIN_INTERFACE)")
    if not math.isfinite(args.duration) or args.duration <= 0:
        parser.error("--duration must be positive")
    _validate_processing_arguments(parser, args)
    if args.round_id and ROUND_ID_PATTERN.fullmatch(args.round_id) is None:
        parser.error("--round-id may contain only letters, digits, dots, underscores, and hyphens")


def _validate_processing_arguments(
    parser: argparse.ArgumentParser, args: argparse.Namespace
) -> None:
    if not math.isfinite(args.max_gps_accuracy) or args.max_gps_accuracy < 0:
        parser.error("--max-gps-accuracy must not be negative")
    if args.round_id is not None and ROUND_ID_PATTERN.fullmatch(args.round_id) is None:
        parser.error("round ID may contain only letters, digits, dots, underscores, and hyphens")


def _runtime_paths(
    parser: argparse.ArgumentParser, round_id: str, zones: str
) -> tuple[Path, Path, Path]:
    source_path = Path("data/smoke") / f"{round_id}.sqlite"
    secret_path = Path("data/local") / f"{round_id}.secret"
    zones_path = Path(zones)
    if not zones_path.is_file() or zones_path.is_symlink():
        parser.error(f"approved zone file not found: {zones_path}")
    try:
        load_approved_zones(zones_path)
    except RuntimeConfigurationError:
        parser.error(f"approved zone file is invalid: {zones_path}")
    return source_path, secret_path, zones_path


def _new_round_id() -> str:
    timestamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    return f"measurement-{timestamp}"


def _gps_quality_ready(max_gps_accuracy: float) -> bool:
    fix = GpsdClient(timeout_seconds=10.0).get_latest_fix()
    if fix is None:
        print("Workflow gestopt: geen actuele 3D GPS-fix beschikbaar.", file=sys.stderr)
        return False
    if fix.accuracy_m is None:
        print(
            "Workflow gestopt: GPSD rapporteert geen horizontale nauwkeurigheid.", file=sys.stderr
        )
        return False
    if fix.accuracy_m > max_gps_accuracy:
        print(
            "Workflow gestopt: GPS-nauwkeurigheid overschrijdt de ingestelde grens "
            f"van {max_gps_accuracy:g} meter.",
            file=sys.stderr,
        )
        return False
    return True


def _create_runtime_inputs(source_path: Path, secret_path: Path) -> None:
    source_path.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
    secret_path.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
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


def _cleanup_empty_attempt(source_path: Path, secret_path: Path) -> bool:
    """Remove launcher-owned inputs only when the buffer contains no observations."""
    try:
        if source_path.is_symlink() or secret_path.is_symlink():
            return False
        if not source_path.is_file() or not secret_path.is_file():
            return False
        if source_path.stat().st_size > 0:
            with sqlite3.connect(f"file:{source_path.absolute()}?mode=ro", uri=True) as connection:
                count = connection.execute("SELECT count(*) FROM raw_observation").fetchone()
            if count is None or count[0] != 0:
                return False
        source_path.unlink()
        secret_path.unlink()
        return True
    except (OSError, sqlite3.Error):
        return False


def _run(command: Sequence[str], environment: dict[str, str]) -> int:
    try:
        return subprocess.run(command, check=False, env=environment).returncode
    except KeyboardInterrupt:
        print("Workflow onderbroken; gecontroleerde afsluiting gestart.", file=sys.stderr)
        return 130
    except FileNotFoundError:
        print(f"Benodigd programma niet gevonden: {command[0]}", file=sys.stderr)
        return 127


def _python_executable() -> str:
    """Keep the virtualenv path; resolving its symlink would bypass the environment."""
    return str(Path(sys.executable).absolute())


def _start_dashboard(address: str, port: int, database_url: str) -> int:
    environment = os.environ.copy()
    environment["CYBERBREIN_DATABASE_URL"] = database_url
    command = [
        _python_executable(),
        "-m",
        "streamlit",
        "run",
        "src/cyberbrein/presentation/app.py",
        "--server.address",
        address,
        "--server.port",
        str(port),
        "--server.headless",
        "true",
    ]
    return _run(command, environment)


def _print_recovery(source_path: Path, secret_path: Path) -> None:
    print("Workflow gestopt; bronbuffer en secret zijn bewaard voor gecontroleerd herstel.")
    print(f"Bronbuffer: {source_path}")
    print(f"Secret: {secret_path}")
    print(f"Verwerking hervatten: ./cyberbrein resume {source_path.stem}")


def _print_unusable(source_path: Path, secret_path: Path) -> None:
    print("De bronbuffer is geldig maar bevat geen waarnemingen die aan het beleid voldoen.")
    print(f"Bronbuffer: {source_path}")
    print(f"Secret: {secret_path}")
    print(f"Verwijderen: ./cyberbrein discard {source_path.stem} --yes")


def _discard_round(parser: argparse.ArgumentParser, round_id: str, confirmed: bool) -> int:
    if ROUND_ID_PATTERN.fullmatch(round_id) is None:
        parser.error("round ID may contain only letters, digits, dots, underscores, and hyphens")
    if not confirmed:
        parser.error("discard requires --yes because it permanently deletes raw inputs")
    source_path = Path("data/smoke") / f"{round_id}.sqlite"
    secret_path = Path("data/local") / f"{round_id}.secret"
    try:
        cleanup_runtime_inputs(source_path, secret_path)
    except PipelineRuntimeError:
        print("Verwijderen mislukt: ongeldige of ontbrekende runtimebestanden.", file=sys.stderr)
        return 2
    print(f"Ruwe invoer verwijderd voor meetronde: {round_id}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
