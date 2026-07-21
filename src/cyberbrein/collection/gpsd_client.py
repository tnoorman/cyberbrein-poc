import json
import logging
import math
import socket
import time
from collections.abc import Callable
from datetime import datetime, timezone
from threading import Condition, Event, Thread
from typing import Protocol

from cyberbrein.collection.models import GpsFix

GPSD_WATCH_COMMAND = b'?WATCH={"enable":true,"json":true}\n'
logger = logging.getLogger(__name__)


class _GpsdTransport(Protocol):
    def settimeout(self, value: float) -> None: ...

    def sendall(self, data: bytes) -> None: ...

    def recv(self, size: int) -> bytes: ...

    def close(self) -> None: ...


TransportFactory = Callable[[tuple[str, int], float], _GpsdTransport]
MonotonicClock = Callable[[], float]


class GpsFixSource(Protocol):
    def get_latest_fix(self) -> GpsFix | None: ...


def _create_transport(address: tuple[str, int], timeout_seconds: float) -> _GpsdTransport:
    return socket.create_connection(address, timeout=timeout_seconds)


def _parse_timestamp(value: object) -> datetime | None:
    if not isinstance(value, str):
        return None
    try:
        timestamp = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None
    if timestamp.tzinfo is None:
        return None
    return timestamp.astimezone(timezone.utc)


def _parse_fix(line: str) -> GpsFix | None:
    try:
        message = json.loads(line)
    except json.JSONDecodeError:
        return None
    if not isinstance(message, dict) or message.get("class") != "TPV":
        return None

    try:
        mode = int(message.get("mode", 0))
        latitude = float(message["lat"])
        longitude = float(message["lon"])
    except (KeyError, TypeError, ValueError):
        return None
    if mode < 3:
        return None
    if not math.isfinite(latitude) or not -90 <= latitude <= 90:
        return None
    if not math.isfinite(longitude) or not -180 <= longitude <= 180:
        return None

    observed_at_utc = _parse_timestamp(message.get("time"))
    if observed_at_utc is None:
        return None

    accuracy_m = None
    if message.get("eph") is not None:
        try:
            candidate_accuracy = float(message["eph"])
        except (TypeError, ValueError):
            candidate_accuracy = None
        if candidate_accuracy is not None and math.isfinite(candidate_accuracy):
            accuracy_m = candidate_accuracy

    return GpsFix(
        latitude=latitude,
        longitude=longitude,
        mode=mode,
        accuracy_m=accuracy_m,
        observed_at_utc=observed_at_utc,
    )


class GpsdClient:
    def __init__(
        self,
        host: str = "127.0.0.1",
        port: int = 2947,
        timeout_seconds: float = 5.0,
        transport_factory: TransportFactory = _create_transport,
    ) -> None:
        self._address = (host, port)
        self._timeout_seconds = timeout_seconds
        self._transport_factory = transport_factory

    def get_latest_fix(self) -> GpsFix | None:
        """Return the latest valid 3D fix received from GPSD, if available."""
        try:
            transport = self._transport_factory(self._address, self._timeout_seconds)
        except OSError:
            return None

        try:
            transport.settimeout(self._timeout_seconds)
            transport.sendall(GPSD_WATCH_COMMAND)
            buffer = ""
            while True:
                chunk = transport.recv(4096)
                if not chunk:
                    return None
                buffer += chunk.decode("utf-8", errors="replace")

                latest_fix = None
                while "\n" in buffer:
                    line, buffer = buffer.split("\n", 1)
                    fix = _parse_fix(line.strip())
                    if fix is not None:
                        latest_fix = fix
                if latest_fix is not None:
                    return latest_fix
        except (OSError, TimeoutError):
            return None
        finally:
            transport.close()


class CachedGpsFixProvider:
    """Refresh GPS data in the background and expose only a recent in-memory fix."""

    def __init__(
        self,
        source: GpsFixSource,
        *,
        max_age_seconds: float = 5.0,
        refresh_interval_seconds: float = 0.1,
        monotonic_clock: MonotonicClock = time.monotonic,
    ) -> None:
        if max_age_seconds <= 0:
            raise ValueError("max_age_seconds must be positive")
        if refresh_interval_seconds < 0:
            raise ValueError("refresh_interval_seconds must not be negative")

        self._source = source
        self._max_age_seconds = max_age_seconds
        self._refresh_interval_seconds = refresh_interval_seconds
        self._monotonic_clock = monotonic_clock
        self._condition = Condition()
        self._stop_event = Event()
        self._thread: Thread | None = None
        self._latest_fix: GpsFix | None = None
        self._received_at_monotonic: float | None = None

    def start(self) -> None:
        """Start one background GPS reader."""
        if self._thread is not None:
            raise RuntimeError("GPS cache has already been started")
        self._stop_event.clear()
        self._thread = Thread(target=self._refresh, daemon=True, name="gpsd-cache")
        self._thread.start()

    def stop(self) -> None:
        """Stop the background reader after its current bounded GPSD read."""
        self._stop_event.set()
        with self._condition:
            self._condition.notify_all()
        if self._thread is not None:
            self._thread.join()

    def get_latest_fix(self) -> GpsFix | None:
        """Return immediately with the latest fresh fix, or None."""
        with self._condition:
            return self._fresh_fix_locked()

    def wait_for_fix(self, timeout_seconds: float) -> GpsFix | None:
        """Wait up to the configured startup timeout for a fresh fix."""
        if timeout_seconds < 0:
            raise ValueError("timeout_seconds must not be negative")
        deadline = self._monotonic_clock() + timeout_seconds
        with self._condition:
            while True:
                fix = self._fresh_fix_locked()
                if fix is not None:
                    return fix
                remaining = deadline - self._monotonic_clock()
                if remaining <= 0 or self._stop_event.is_set():
                    return None
                self._condition.wait(remaining)

    def _fresh_fix_locked(self) -> GpsFix | None:
        if self._latest_fix is None or self._received_at_monotonic is None:
            return None
        age_seconds = self._monotonic_clock() - self._received_at_monotonic
        if age_seconds > self._max_age_seconds:
            return None
        return self._latest_fix

    def _refresh(self) -> None:
        while not self._stop_event.is_set():
            try:
                fix = self._source.get_latest_fix()
            except Exception:
                logger.error("gps_cache_refresh_failed")
                fix = None
            if fix is not None:
                with self._condition:
                    self._latest_fix = fix
                    self._received_at_monotonic = self._monotonic_clock()
                    self._condition.notify_all()
            self._stop_event.wait(self._refresh_interval_seconds)
