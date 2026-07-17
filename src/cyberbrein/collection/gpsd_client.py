import json
import math
import socket
from collections.abc import Callable
from datetime import datetime, timezone
from typing import Protocol

from cyberbrein.collection.models import GpsFix

GPSD_WATCH_COMMAND = b'?WATCH={"enable":true,"json":true}\n'


class _GpsdTransport(Protocol):
    def settimeout(self, value: float) -> None: ...

    def sendall(self, data: bytes) -> None: ...

    def recv(self, size: int) -> bytes: ...

    def close(self) -> None: ...


TransportFactory = Callable[[tuple[str, int], float], _GpsdTransport]


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
