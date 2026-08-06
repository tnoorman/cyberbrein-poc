import argparse
import math
import os
import re
import subprocess
import sys
from collections.abc import Sequence
from datetime import datetime, timezone
from pathlib import Path

from dotenv import load_dotenv

from cyberbrein.collection.gpsd_client import GpsdClient
from cyberbrein.collection.monitor_setup import MonitorProvisioner, MonitorSetupError
from cyberbrein.pipeline.exit_codes import (
    CLEANUP_EXIT as CLEANUP_EXIT,
)
from cyberbrein.pipeline.exit_codes import (
    UNUSABLE_SOURCE_EXIT as UNUSABLE_SOURCE_EXIT,
)
from cyberbrein.pipeline.runtime_config import RuntimeConfigurationError, load_approved_zones

from .service import ResumeRequest, RoundOutcome, RunRequest, WorkflowEvent, WorkflowService

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
        "--management-interface",
        default=os.environ.get("CYBERBREIN_MANAGEMENT_INTERFACE", "wlan0"),
        help="Wi-Fi interface reserved for connectivity/AP use (default: wlan0).",
    )
    run.add_argument(
        "--interface-lifecycle",
        choices=("persistent-monitor", "temporary"),
        default=os.environ.get(
            "CYBERBREIN_INTERFACE_LIFECYCLE",
            "persistent-monitor",
        ),
        help="Capture-interface lifecycle (default: persistent-monitor).",
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

    for command, help_text in (
        ("setup-monitor", "Persistently dedicate a Wi-Fi interface to monitor mode."),
        ("teardown-monitor", "Return a persistently configured interface to managed mode."),
    ):
        monitor_command = subparsers.add_parser(command, help=help_text)
        monitor_command.add_argument(
            "--interface",
            default=os.environ.get("CYBERBREIN_INTERFACE"),
            required=os.environ.get("CYBERBREIN_INTERFACE") is None,
            help="Dedicated capture interface (or set CYBERBREIN_INTERFACE).",
        )
        monitor_command.add_argument(
            "--management-interface",
            default=os.environ.get("CYBERBREIN_MANAGEMENT_INTERFACE", "wlan0"),
            help="Protected connectivity/AP interface (default: wlan0).",
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
    is_root = hasattr(os, "geteuid") and os.geteuid() == 0
    if args.command in {"setup-monitor", "teardown-monitor"}:
        if not is_root:
            print(
                f"Voer deze eenmalige systeemconfiguratie uit met sudo: sudo ./cyberbrein "
                f"{args.command} --interface {args.interface}",
                file=sys.stderr,
            )
            return 2
        return _configure_monitor_interface(args, setup=args.command == "setup-monitor")

    if is_root:
        print(
            "Start de launcher zonder sudo: ./cyberbrein "
            f"{args.command}. Alleen Collection vraagt daarna om sudo.",
            file=sys.stderr,
        )
        return 2
    service = WorkflowService(
        command_runner=_run,
        gps_check=_gps_quality_ready,
        monitor_check=_monitor_interface_ready,
        event_handler=_render_workflow_event,
    )
    if args.command == "discard":
        if ROUND_ID_PATTERN.fullmatch(args.round_id) is None:
            parser.error(
                "round ID may contain only letters, digits, dots, underscores, and hyphens"
            )
        if not args.yes:
            parser.error("discard requires --yes because it permanently deletes raw inputs")
        return _render_outcome(service.discard(args.round_id))

    database_url = os.environ.get("CYBERBREIN_DATABASE_URL", DEFAULT_DATABASE_URL)
    if not database_url.startswith(("postgresql://", "postgresql+psycopg2://")):
        parser.error("CYBERBREIN_DATABASE_URL must point to PostgreSQL/PostGIS")
    if not 1 <= args.port <= 65535:
        parser.error("--port must be between 1 and 65535")

    if args.command == "dashboard":
        return _render_outcome(service.dashboard(args.address, args.port, database_url))

    if args.command == "resume":
        _validate_processing_arguments(parser, args)
        source_path, secret_path, zones_path = _runtime_paths(parser, args.round_id, args.zones)
        if not source_path.is_file() or source_path.is_symlink():
            parser.error(f"preserved source buffer not found: {source_path}")
        if not secret_path.is_file() or secret_path.is_symlink():
            parser.error(f"preserved secret not found: {secret_path}")
        return _render_outcome(
            service.resume(
                ResumeRequest(
                    round_id=args.round_id,
                    zones_path=zones_path,
                    max_gps_accuracy=args.max_gps_accuracy,
                    database_url=database_url,
                    no_dashboard=args.no_dashboard,
                    address=args.address,
                    port=args.port,
                )
            )
        )

    _validate_run_arguments(parser, args)
    round_id = args.round_id or _new_round_id()
    _, _, zones_path = _runtime_paths(parser, round_id, args.zones)
    return _render_outcome(
        service.run(
            RunRequest(
                round_id=round_id,
                interface=args.interface,
                interface_lifecycle=args.interface_lifecycle,
                channels=args.channels,
                duration=args.duration,
                zones_path=zones_path,
                max_gps_accuracy=args.max_gps_accuracy,
                database_url=database_url,
                no_dashboard=args.no_dashboard,
                address=args.address,
                port=args.port,
            )
        )
    )


def _validate_run_arguments(parser: argparse.ArgumentParser, args: argparse.Namespace) -> None:
    if not args.interface or not args.interface.strip():
        parser.error("--interface is required (or set CYBERBREIN_INTERFACE)")
    if not math.isfinite(args.duration) or args.duration <= 0:
        parser.error("--duration must be positive")
    if args.interface == args.management_interface:
        parser.error("capture interface must differ from --management-interface")
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


def _monitor_interface_ready(interface: str) -> bool:
    try:
        result = subprocess.run(
            ["iw", "dev", interface, "info"],
            stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL,
            text=True,
            check=False,
        )
    except OSError:
        result = None
    if result is not None and result.returncode == 0:
        for line in result.stdout.splitlines():
            if line.strip() == "type monitor":
                return True
    print(
        f"Workflow gestopt: {interface} is niet persistent in monitor mode.\n"
        f"Eenmalige setup: sudo ./cyberbrein setup-monitor --interface {interface}",
        file=sys.stderr,
    )
    return False


def _render_workflow_event(event: WorkflowEvent) -> None:
    if event.name == "round_started":
        print(f"Meetronde gestart: {event.round_id}")


def _render_outcome(outcome: RoundOutcome) -> int:
    if outcome.guidance == "runtime_creation_failed":
        print(
            f"Workflow kon veilige runtimebestanden niet maken: {outcome.detail}",
            file=sys.stderr,
        )
    elif outcome.guidance == "empty_attempt":
        print("Geen waarnemingen vastgelegd; lege runtimebestanden zijn verwijderd.")
    elif outcome.guidance == "recovery":
        assert outcome.source_path is not None and outcome.secret_path is not None
        _print_recovery(outcome.source_path, outcome.secret_path)
    elif outcome.guidance == "unusable":
        assert outcome.source_path is not None and outcome.secret_path is not None
        _print_unusable(outcome.source_path, outcome.secret_path)
    elif outcome.guidance == "incomplete_cleanup":
        assert outcome.source_path is not None and outcome.secret_path is not None
        _print_incomplete_cleanup(outcome.source_path, outcome.secret_path)
    elif outcome.guidance == "processed":
        print("Meetronde verwerkt en tijdelijke invoer veilig verwijderd.")
    elif outcome.guidance == "discard_failed":
        print(
            "Verwijderen mislukt: ongeldige of ontbrekende runtimebestanden.",
            file=sys.stderr,
        )
    elif outcome.guidance == "discarded":
        print(f"Ruwe invoer verwijderd voor meetronde: {outcome.round_id}")
    return outcome.exit_code


def _configure_monitor_interface(args: argparse.Namespace, *, setup: bool) -> int:
    try:
        provisioner = MonitorProvisioner(
            args.interface,
            args.management_interface,
        )
        if setup:
            provisioner.setup()
            print(f"Persistente monitor mode actief voor: {args.interface}")
        else:
            provisioner.teardown()
            print(f"Managed mode hersteld voor: {args.interface}")
    except MonitorSetupError as error:
        print(f"Monitorconfiguratie mislukt: {error.category}", file=sys.stderr)
        return 2
    return 0


def _run(command: Sequence[str], environment: dict[str, str]) -> int:
    try:
        return subprocess.run(command, check=False, env=environment).returncode
    except KeyboardInterrupt:
        print("Workflow onderbroken; gecontroleerde afsluiting gestart.", file=sys.stderr)
        return 130
    except FileNotFoundError:
        print(f"Benodigd programma niet gevonden: {command[0]}", file=sys.stderr)
        return 127


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


def _print_incomplete_cleanup(source_path: Path, secret_path: Path) -> None:
    print(
        "Meetronde opgeslagen en geverifieerd, maar tijdelijke invoer is niet volledig verwijderd."
    )
    for label, path in (("Bronbuffer", source_path), ("Secret", secret_path)):
        if path.exists() or path.is_symlink():
            print(f"{label}: {path}")
    print("Verwerking mag niet opnieuw worden uitgevoerd.")
    print("Resultaten bekijken: ./cyberbrein dashboard")
    print(f"Resterende invoer verwijderen: ./cyberbrein discard {source_path.stem} --yes")
