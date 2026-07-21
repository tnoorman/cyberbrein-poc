import argparse
import logging
import sys
from collections.abc import Sequence

from cyberbrein.collection.channel_hopper import ChannelHopper
from cyberbrein.collection.collector import CollectionError, CollectorService
from cyberbrein.collection.gpsd_client import CachedGpsFixProvider, GpsdClient
from cyberbrein.collection.sqlite_writer import SQLiteObservationWriter


def _parse_channels(value: str) -> tuple[int, ...]:
    try:
        channels = tuple(int(part.strip()) for part in value.split(",") if part.strip())
    except ValueError as error:
        raise argparse.ArgumentTypeError("channels must be comma-separated integers") from error
    if not channels or any(channel <= 0 for channel in channels):
        raise argparse.ArgumentTypeError("channels must contain positive integers")
    return channels


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Passive Wi-Fi collection to a temporary restricted SQLite buffer."
    )
    parser.add_argument(
        "--interface",
        "--iface",
        dest="interface",
        required=True,
        help="Wi-Fi interface already configured in monitor mode.",
    )
    parser.add_argument(
        "--database-path",
        "--db",
        dest="database_path",
        required=True,
        help="Path to the temporary SQLite buffer.",
    )
    parser.add_argument(
        "--measurement-round-id",
        "--round-id",
        dest="measurement_round_id",
        required=True,
        help="Identifier for this measurement round.",
    )
    parser.add_argument(
        "--channels",
        type=_parse_channels,
        default=_parse_channels("1,6,11"),
        help="Comma-separated channels used for hopping (default: 1,6,11).",
    )
    parser.add_argument(
        "--duration",
        "--seconds",
        dest="duration_seconds",
        type=float,
        default=60.0,
        help="Measurement duration in seconds (default: 60).",
    )
    parser.add_argument(
        "--dwell",
        dest="dwell_seconds",
        type=float,
        default=1.0,
        help="Seconds per channel while hopping (default: 1).",
    )
    parser.add_argument("--no-hop", action="store_true", help="Disable channel hopping.")
    parser.add_argument("--gpsd", action="store_true", help="Attach live 3D fixes from GPSD.")
    parser.add_argument("--gpsd-host", default="127.0.0.1", help="GPSD host.")
    parser.add_argument("--gpsd-port", type=int, default=2947, help="GPSD port.")
    parser.add_argument(
        "--gpsd-timeout",
        type=float,
        default=5.0,
        help="GPSD connection/read timeout in seconds.",
    )
    parser.add_argument(
        "--gps-max-age",
        type=float,
        default=5.0,
        help="Maximum cached GPS-fix age in seconds (default: 5).",
    )
    parser.add_argument(
        "--gps-wait",
        type=float,
        default=30.0,
        help="Maximum startup wait for a required GPS fix (default: 30).",
    )
    parser.add_argument(
        "--require-gps-fix",
        action="store_true",
        help="Store only observations with a valid live 3D GPS fix.",
    )
    return parser


def _validate_arguments(parser: argparse.ArgumentParser, args: argparse.Namespace) -> None:
    if args.duration_seconds <= 0:
        parser.error("--duration must be positive")
    if args.dwell_seconds <= 0:
        parser.error("--dwell must be positive")
    if not 1 <= args.gpsd_port <= 65535:
        parser.error("--gpsd-port must be between 1 and 65535")
    if args.gpsd_timeout <= 0:
        parser.error("--gpsd-timeout must be positive")
    if args.gps_max_age <= 0:
        parser.error("--gps-max-age must be positive")
    if args.gps_wait < 0:
        parser.error("--gps-wait must not be negative")


def _sniff(**kwargs: object) -> object:
    from scapy.sendrecv import sniff

    return sniff(**kwargs)


def main(argv: Sequence[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    _validate_arguments(parser, args)
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")

    use_gpsd = args.gpsd or args.require_gps_fix
    gpsd_provider = (
        CachedGpsFixProvider(
            GpsdClient(
                host=args.gpsd_host,
                port=args.gpsd_port,
                timeout_seconds=args.gpsd_timeout,
            ),
            max_age_seconds=args.gps_max_age,
        )
        if use_gpsd
        else None
    )
    hopper = None
    if not args.no_hop:
        hopper = ChannelHopper(
            interface=args.interface,
            channels=args.channels,
            dwell_seconds=args.dwell_seconds,
        )

    try:
        if gpsd_provider is not None:
            gpsd_provider.start()
            if args.require_gps_fix and gpsd_provider.wait_for_fix(args.gps_wait) is None:
                raise CollectionError("gps_fix_unavailable")
        writer = SQLiteObservationWriter(args.database_path)
        service = CollectorService(
            measurement_round_id=args.measurement_round_id,
            writer=writer,
            gpsd_client=gpsd_provider,
            channel_hopper=hopper,
            require_gps_fix=args.require_gps_fix,
        )
        print("Collection gestart")
        summary = service.run(args.interface, args.duration_seconds, _sniff)
    except KeyboardInterrupt:
        print("Collection onderbroken", file=sys.stderr)
        return 130
    except Exception as error:
        category = error.category if isinstance(error, CollectionError) else "configuration_failed"
        print(f"Collection mislukt: {category}", file=sys.stderr)
        return 2
    finally:
        if gpsd_provider is not None:
            gpsd_provider.stop()

    print(f"Waarnemingen opgeslagen: {summary.stored_observations}")
    print(f"Frames overgeslagen: {summary.unsupported_packets}")
    print(f"Ontbrekende GPS-fixes: {summary.missing_gps_fixes}")
    print("Collection gestopt")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
