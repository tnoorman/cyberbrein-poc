import json
import logging
import math
import socket
import time
from collections.abc import Callable
from datetime import datetime, timezone
from threading import Condition, Event, Lock, Thread
from typing import Protocol

from cyberbrein.collection.models import GpsFix

GPSD_WATCH_COMMAND = b'?WATCH={"enable":true,"json":true}\n'
logger = logging.getLogger(__name__)


class _GpsdTransport(Protocol):
    def settimeout(self, value: float) -> None: ...

    def sendall(self, data: bytes) -> None: ...

    def recv(self, size: int) -> bytes: ...

    def shutdown(self, how: int) -> None: ...

    def close(self) -> None: ...


TransportFactory = Callable[[tuple[str, int], float], _GpsdTransport]
MonotonicClock = Callable[[], float]


class GpsFixSource(Protocol):
    def get_latest_fix(self) -> GpsFix | None: ...


FixCallback = Callable[[GpsFix], None]


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

    accuracy_m = _horizontal_accuracy(message)

    return GpsFix(
        latitude=latitude,
        longitude=longitude,
        mode=mode,
        accuracy_m=accuracy_m,
        observed_at_utc=observed_at_utc,
    )


def _horizontal_accuracy(message: dict[str, object]) -> float | None:
    """Prefer GPSD's 2D error, otherwise combine longitude and latitude errors."""
    eph = _finite_non_negative_float(message.get("eph"))
    if eph is not None:
        return eph

    longitude_error = _finite_non_negative_float(message.get("epx"))
    latitude_error = _finite_non_negative_float(message.get("epy"))
    if longitude_error is None or latitude_error is None:
        return None
    return math.hypot(longitude_error, latitude_error)


def _finite_non_negative_float(value: object) -> float | None:
    try:
        candidate = float(value)  # type: ignore[arg-type]
    except (TypeError, ValueError):
        return None
    return candidate if math.isfinite(candidate) and candidate >= 0 else None


class GpsdClient:
    def __init__(
        self,
        host: str = "127.0.0.1",
        port: int = 2947,
        timeout_seconds: float = 5.0,
        transport_factory: TransportFactory = _create_transport,
        monotonic_clock: MonotonicClock = time.monotonic,
    ) -> None:
        self._address = (host, port)
        self._timeout_seconds = timeout_seconds
        self._transport_factory = transport_factory
        self._monotonic_clock = monotonic_clock
        self._transport_lock = Lock()
        self._active_transport: _GpsdTransport | None = None

    def get_latest_fix(self) -> GpsFix | None:
        """Return the latest valid 3D fix received from GPSD, if available."""
        try:
            transport = self._transport_factory(self._address, self._timeout_seconds)
        except OSError:
            return None

        latest_fix = None
        try:
            transport.settimeout(self._timeout_seconds)
            transport.sendall(GPSD_WATCH_COMMAND)
            buffer = ""
            deadline = self._monotonic_clock() + self._timeout_seconds
            while True:
                remaining = deadline - self._monotonic_clock()
                if remaining <= 0:
                    return latest_fix
                transport.settimeout(remaining)
                chunk = transport.recv(4096)
                if not chunk:
                    return latest_fix
                buffer += chunk.decode("utf-8", errors="replace")

                while "\n" in buffer:
                    line, buffer = buffer.split("\n", 1)
                    fix = _parse_fix(line.strip())
                    if fix is not None:
                        latest_fix = fix
                if latest_fix is not None and latest_fix.accuracy_m is not None:
                    return latest_fix
        except (OSError, TimeoutError):
            return latest_fix
        finally:
            transport.close()

    def stream_fixes(
        self,
        callback: FixCallback,
        stop_event: Event,
        *,
        max_accuracy_age_seconds: float = 10.0,
        reconnect_delay_seconds: float = 1.0,
    ) -> None:
        """Continuously stream merged GPSD fixes until cancellation is requested."""
        if max_accuracy_age_seconds <= 0:
            raise ValueError("max_accuracy_age_seconds must be positive")
        if reconnect_delay_seconds < 0:
            raise ValueError("reconnect_delay_seconds must not be negative")

        state = _TpvState(self._monotonic_clock, max_accuracy_age_seconds)
        while not stop_event.is_set():
            transport: _GpsdTransport | None = None
            try:
                transport = self._transport_factory(self._address, min(self._timeout_seconds, 1.0))
                self._set_active_transport(transport)
                transport.settimeout(min(self._timeout_seconds, 1.0))
                transport.sendall(GPSD_WATCH_COMMAND)
                logger.info("gpsd_connected")
                buffer = ""
                while not stop_event.is_set():
                    try:
                        chunk = transport.recv(4096)
                    except (TimeoutError, socket.timeout):
                        continue
                    if not chunk:
                        break
                    buffer += chunk.decode("utf-8", errors="replace")
                    while "\n" in buffer:
                        line, buffer = buffer.split("\n", 1)
                        fix = state.update(line.strip())
                        if fix is not None:
                            callback(fix)
            except OSError:
                if not stop_event.is_set():
                    logger.warning("gpsd_reconnecting")
            finally:
                self._clear_active_transport(transport)
                if transport is not None:
                    _close_transport(transport)
            if not stop_event.is_set():
                stop_event.wait(reconnect_delay_seconds)

    def close(self) -> None:
        """Actively release a collection-time GPSD read from another thread."""
        with self._transport_lock:
            transport = self._active_transport
        if transport is not None:
            _close_transport(transport)

    def _set_active_transport(self, transport: _GpsdTransport) -> None:
        with self._transport_lock:
            self._active_transport = transport

    def _clear_active_transport(self, transport: _GpsdTransport | None) -> None:
        with self._transport_lock:
            if self._active_transport is transport:
                self._active_transport = None


class _TpvState:
    """Merge GPSD TPV fields, whose position and error values may arrive separately."""

    def __init__(self, monotonic_clock: MonotonicClock, max_accuracy_age_seconds: float) -> None:
        self._monotonic_clock = monotonic_clock
        self._max_accuracy_age_seconds = max_accuracy_age_seconds
        self._accuracy_m: float | None = None
        self._accuracy_received_at: float | None = None

    def update(self, line: str) -> GpsFix | None:
        try:
            message = json.loads(line)
        except json.JSONDecodeError:
            return None
        if not isinstance(message, dict) or message.get("class") != "TPV":
            return None

        now = self._monotonic_clock()
        accuracy_m = _horizontal_accuracy(message)
        if accuracy_m is not None:
            self._accuracy_m = accuracy_m
            self._accuracy_received_at = now

        position = _parse_fix(line)
        if position is None:
            return None
        if self._accuracy_m is None or self._accuracy_received_at is None:
            return None
        if now - self._accuracy_received_at > self._max_accuracy_age_seconds:
            self._accuracy_m = None
            self._accuracy_received_at = None
            return None
        return GpsFix(
            latitude=position.latitude,
            longitude=position.longitude,
            mode=position.mode,
            accuracy_m=self._accuracy_m,
            observed_at_utc=position.observed_at_utc,
        )


def _close_transport(transport: _GpsdTransport) -> None:
    try:
        shutdown = getattr(transport, "shutdown", None)
        if shutdown is not None:
            shutdown(socket.SHUT_RDWR)
    except OSError:
        pass
    try:
        transport.close()
    except OSError:
        pass


class CachedGpsFixProvider:
    """Refresh GPS data in the background and expose only a recent in-memory fix."""

    def __init__(
        self,
        source: GpsFixSource,
        *,
        max_age_seconds: float = 5.0,
        refresh_interval_seconds: float = 0.1,
        stop_timeout_seconds: float = 1.5,
        max_accuracy_age_seconds: float = 10.0,
        monotonic_clock: MonotonicClock = time.monotonic,
    ) -> None:
        if max_age_seconds <= 0:
            raise ValueError("max_age_seconds must be positive")
        if refresh_interval_seconds < 0:
            raise ValueError("refresh_interval_seconds must not be negative")
        if stop_timeout_seconds <= 0:
            raise ValueError("stop_timeout_seconds must be positive")

        self._source = source
        self._max_age_seconds = max_age_seconds
        self._refresh_interval_seconds = refresh_interval_seconds
        self._stop_timeout_seconds = stop_timeout_seconds
        self._max_accuracy_age_seconds = max_accuracy_age_seconds
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
        """Cancel the background reader and actively release a blocked GPSD socket."""
        self._stop_event.set()
        close = getattr(self._source, "close", None)
        if close is not None:
            close()
        with self._condition:
            self._condition.notify_all()
        if self._thread is not None:
            self._thread.join(timeout=self._stop_timeout_seconds)
            if self._thread.is_alive():
                logger.warning("gps_cache_stop_timeout")
            else:
                self._thread = None

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
        stream_fixes = getattr(self._source, "stream_fixes", None)
        if stream_fixes is not None:
            try:
                stream_fixes(
                    self._store_fix,
                    self._stop_event,
                    max_accuracy_age_seconds=self._max_accuracy_age_seconds,
                )
            except Exception:
                if not self._stop_event.is_set():
                    logger.error("gps_cache_refresh_failed")
            return

        while not self._stop_event.is_set():
            try:
                fix = self._source.get_latest_fix()
            except Exception:
                logger.error("gps_cache_refresh_failed")
                fix = None
            if fix is not None:
                self._store_fix(fix)
            self._stop_event.wait(self._refresh_interval_seconds)

    def _store_fix(self, fix: GpsFix) -> None:
        with self._condition:
            self._latest_fix = fix
            self._received_at_monotonic = self._monotonic_clock()
            self._condition.notify_all()
