from datetime import datetime, timezone
from threading import Event

import pytest

from cyberbrein.collection.gpsd_client import (
    GPSD_WATCH_COMMAND,
    CachedGpsFixProvider,
    GpsdClient,
)
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


class FakeFixSource:
    def __init__(self, fixes: list[GpsFix | None]) -> None:
        self._fixes = iter(fixes)
        self.called = Event()

    def get_latest_fix(self) -> GpsFix | None:
        self.called.set()
        return next(self._fixes, None)


def _valid_fix() -> GpsFix:
    return GpsFix(
        latitude=0.0,
        longitude=0.0,
        mode=3,
        accuracy_m=4.5,
        observed_at_utc=datetime(2026, 1, 1, 12, 0, tzinfo=timezone.utc),
    )


def test_cache_reads_source_in_background_and_returns_fix() -> None:
    source = FakeFixSource([_valid_fix()])
    cache = CachedGpsFixProvider(source, refresh_interval_seconds=0.01)

    cache.start()
    try:
        assert cache.wait_for_fix(1.0) == _valid_fix()
        assert cache.get_latest_fix() == _valid_fix()
    finally:
        cache.stop()


def test_cache_returns_immediately_while_source_is_blocked() -> None:
    release_source = Event()

    class BlockingSource:
        def get_latest_fix(self) -> GpsFix | None:
            release_source.wait(1.0)
            return _valid_fix()

    cache = CachedGpsFixProvider(BlockingSource())
    cache.start()
    try:
        assert cache.get_latest_fix() is None
    finally:
        release_source.set()
        cache.stop()


def test_cache_rejects_stale_fix_using_monotonic_age() -> None:
    monotonic_time = [100.0]
    cache = CachedGpsFixProvider(
        FakeFixSource([_valid_fix()]),
        max_age_seconds=5.0,
        refresh_interval_seconds=10.0,
        monotonic_clock=lambda: monotonic_time[0],
    )
    cache.start()
    try:
        assert cache.wait_for_fix(1.0) == _valid_fix()
        monotonic_time[0] = 105.1
        assert cache.get_latest_fix() is None
    finally:
        cache.stop()


def test_wait_for_fix_returns_none_after_timeout() -> None:
    monotonic_time = [100.0]
    source = FakeFixSource([None])
    cache = CachedGpsFixProvider(
        source,
        refresh_interval_seconds=10.0,
        monotonic_clock=lambda: monotonic_time.pop(0) if len(monotonic_time) > 1 else 101.0,
    )
    cache.start()
    try:
        assert cache.wait_for_fix(0.0) is None
    finally:
        cache.stop()
