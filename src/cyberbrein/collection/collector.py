import logging
from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime, timezone
from threading import Event, Thread
from typing import Protocol

from cyberbrein.collection.models import GpsFix, RawObservation, WifiFrameMetadata

logger = logging.getLogger(__name__)


class GpsFixProvider(Protocol):
    def get_latest_fix(self) -> GpsFix | None: ...


class ObservationWriter(Protocol):
    def write(self, observation: RawObservation) -> None: ...


class Hopper(Protocol):
    def run(self, stop_event: Event) -> None: ...


class Sniffer(Protocol):
    def __call__(
        self,
        *,
        iface: str,
        prn: Callable[[object], object],
        store: bool,
        timeout: float,
    ) -> object: ...


FrameParser = Callable[[object, datetime], WifiFrameMetadata | None]
Clock = Callable[[], datetime]


class CollectionError(RuntimeError):
    """A controlled collection failure identified by a privacy-safe category."""

    def __init__(self, category: str) -> None:
        super().__init__(category)
        self.category = category


@dataclass(frozen=True, slots=True)
class CollectionSummary:
    received_packets: int
    stored_observations: int
    unsupported_packets: int
    missing_gps_fixes: int


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


class CollectorService:
    def __init__(
        self,
        measurement_round_id: str,
        writer: ObservationWriter,
        gpsd_client: GpsFixProvider | None = None,
        channel_hopper: Hopper | None = None,
        *,
        require_gps_fix: bool = False,
        frame_parser: FrameParser | None = None,
        clock: Clock = _utc_now,
    ) -> None:
        if not measurement_round_id.strip():
            raise ValueError("measurement_round_id is required")
        if require_gps_fix and gpsd_client is None:
            raise ValueError("gpsd_client is required when GPS fix is mandatory")

        self._measurement_round_id = measurement_round_id
        self._writer = writer
        self._gpsd_client = gpsd_client
        self._channel_hopper = channel_hopper
        self._require_gps_fix = require_gps_fix
        if frame_parser is None:
            from cyberbrein.collection.frame_parser import parse_wifi_frame

            frame_parser = parse_wifi_frame
        self._frame_parser = frame_parser
        self._clock = clock
        self._received_packets = 0
        self._stored_observations = 0
        self._unsupported_packets = 0
        self._missing_gps_fixes = 0

    def process_packet(self, packet: object) -> None:
        """Parse and persist one packet when it satisfies the collection policy."""
        self._received_packets += 1
        try:
            metadata = self._frame_parser(packet, self._clock())
        except Exception as error:
            logger.error("collection_frame_parse_failed")
            raise CollectionError("frame_parse_failed") from error

        if metadata is None:
            self._unsupported_packets += 1
            return

        gps_fix = self._get_gps_fix()
        if gps_fix is None:
            self._missing_gps_fixes += 1
            if self._require_gps_fix:
                return

        observation = RawObservation(
            measurement_round_id=self._measurement_round_id,
            observed_at_utc=metadata.observed_at_utc,
            bssid=metadata.bssid,
            ssid=metadata.ssid,
            rssi_dbm=metadata.rssi_dbm,
            channel=metadata.channel,
            frequency_mhz=metadata.frequency_mhz,
            band=metadata.band,
            encryption=metadata.encryption,
            frame_type=metadata.frame_type,
            latitude=gps_fix.latitude if gps_fix is not None else None,
            longitude=gps_fix.longitude if gps_fix is not None else None,
            gps_mode=gps_fix.mode if gps_fix is not None else None,
            gps_accuracy_m=gps_fix.accuracy_m if gps_fix is not None else None,
        )

        try:
            self._writer.write(observation)
        except Exception as error:
            logger.error("collection_observation_write_failed")
            raise CollectionError("observation_write_failed") from error
        self._stored_observations += 1

    def run(self, interface: str, duration_seconds: float, sniffer: Sniffer) -> CollectionSummary:
        """Run packet collection and always stop the optional channel hopper."""
        if not interface.strip():
            raise ValueError("interface is required")
        if duration_seconds <= 0:
            raise ValueError("duration_seconds must be positive")

        stop_event = Event()
        hopper_errors: list[Exception] = []
        hopper_thread = self._start_hopper(stop_event, hopper_errors)
        logger.info("collection_started")
        try:
            sniffer(
                iface=interface,
                prn=self.process_packet,
                store=False,
                timeout=duration_seconds,
            )
        except CollectionError:
            raise
        except Exception as error:
            logger.error("collection_sniffer_failed")
            raise CollectionError("sniffer_failed") from error
        finally:
            stop_event.set()
            if hopper_thread is not None:
                hopper_thread.join(timeout=2.0)

        if hopper_errors:
            logger.error("collection_channel_hopper_failed")
            raise CollectionError("channel_hopper_failed") from hopper_errors[0]

        summary = self.summary()
        logger.info(
            "collection_finished stored=%d unsupported=%d missing_gps=%d",
            summary.stored_observations,
            summary.unsupported_packets,
            summary.missing_gps_fixes,
        )
        return summary

    def summary(self) -> CollectionSummary:
        return CollectionSummary(
            received_packets=self._received_packets,
            stored_observations=self._stored_observations,
            unsupported_packets=self._unsupported_packets,
            missing_gps_fixes=self._missing_gps_fixes,
        )

    def _get_gps_fix(self) -> GpsFix | None:
        if self._gpsd_client is None:
            return None
        try:
            return self._gpsd_client.get_latest_fix()
        except Exception as error:
            logger.error("collection_gps_read_failed")
            raise CollectionError("gps_read_failed") from error

    def _start_hopper(
        self,
        stop_event: Event,
        hopper_errors: list[Exception],
    ) -> Thread | None:
        if self._channel_hopper is None:
            return None

        def run_hopper() -> None:
            try:
                self._channel_hopper.run(stop_event)
            except Exception as error:
                hopper_errors.append(error)
                stop_event.set()

        thread = Thread(target=run_hopper, daemon=True, name="channel-hopper")
        thread.start()
        return thread
