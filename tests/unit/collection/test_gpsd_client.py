from datetime import datetime, timezone

import pytest

from cyberbrein.collection.gpsd_client import GPSD_WATCH_COMMAND, GpsdClient
from cyberbrein.collection.models import GpsFix


class FakeTransport:
    def __init__(self, chunks: list[bytes]) -> None:
        self._chunks = iter(chunks)
        self.timeout: float | None = None
        self.sent_data: list[bytes] = []
        self.closed = False

    def settimeout(self, value: float) -> None:
        self.timeout = value

    def sendall(self, data: bytes) -> None:
        self.sent_data.append(data)

    def recv(self, size: int) -> bytes:
        del size
        return next(self._chunks, b"")

    def close(self) -> None:
        self.closed = True


def _client_for(chunks: list[bytes]) -> tuple[GpsdClient, FakeTransport]:
    transport = FakeTransport(chunks)

    def factory(address: tuple[str, int], timeout_seconds: float) -> FakeTransport:
        assert address == ("127.0.0.1", 2947)
        assert timeout_seconds == 2.0
        return transport

    return GpsdClient(timeout_seconds=2.0, transport_factory=factory), transport


def test_get_latest_fix_returns_valid_gpsd_fix() -> None:
    client, transport = _client_for(
        [b'{"class":"TPV","mode":3,"lat":0.0,"lon":0.0,"eph":4.5,"time":"2026-01-01T12:00:00Z"}\n']
    )

    fix = client.get_latest_fix()

    assert fix == GpsFix(
        latitude=0.0,
        longitude=0.0,
        mode=3,
        accuracy_m=4.5,
        observed_at_utc=datetime(2026, 1, 1, 12, 0, tzinfo=timezone.utc),
    )
    assert transport.sent_data == [GPSD_WATCH_COMMAND]
    assert transport.timeout == 2.0
    assert transport.closed


def test_get_latest_fix_returns_last_valid_fix_from_received_messages() -> None:
    client, _ = _client_for(
        [
            b'{"class":"TPV","mode":3,"lat":0.0,"lon":0.0,'
            b'"time":"2026-01-01T12:00:00Z"}\n'
            b'{"class":"TPV","mode":3,"lat":1.0,"lon":1.0,'
            b'"time":"2026-01-01T12:00:01Z"}\n'
        ]
    )

    fix = client.get_latest_fix()

    assert fix is not None
    assert fix.latitude == 1.0
    assert fix.longitude == 1.0
    assert fix.observed_at_utc == datetime(2026, 1, 1, 12, 0, 1, tzinfo=timezone.utc)


def test_get_latest_fix_rejects_mode_two() -> None:
    client, _ = _client_for(
        [b'{"class":"TPV","mode":2,"lat":0.0,"lon":0.0,"time":"2026-01-01T12:00:00Z"}\n']
    )

    assert client.get_latest_fix() is None


def test_get_latest_fix_accepts_missing_accuracy() -> None:
    client, _ = _client_for(
        [b'{"class":"TPV","mode":3,"lat":0.0,"lon":0.0,"time":"2026-01-01T12:00:00Z"}\n']
    )

    fix = client.get_latest_fix()

    assert fix is not None
    assert fix.accuracy_m is None


@pytest.mark.parametrize(
    "message",
    [
        b"not-json\n",
        b'{"class":"SKY"}\n',
        b'{"class":"TPV","mode":3,"lat":0.0,"time":"2026-01-01T12:00:00Z"}\n',
    ],
    ids=["malformed-json", "non-tpv", "incomplete-tpv"],
)
def test_get_latest_fix_ignores_invalid_messages(message: bytes) -> None:
    client, _ = _client_for([message])

    assert client.get_latest_fix() is None
