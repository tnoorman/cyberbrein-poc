import logging
from datetime import datetime, timezone
from threading import Event

import pytest

from cyberbrein.collection.collector import CollectionError, CollectorService
from cyberbrein.collection.models import GpsFix, RawObservation, WifiFrameMetadata

OBSERVED_AT_UTC = datetime(2026, 1, 1, 12, 0, tzinfo=timezone.utc)
SYNTHETIC_BSSID = "02:00:00:00:00:50"
SYNTHETIC_SSID = "SYNTHETIC-COLLECTOR-NETWORK"


class FakeWriter:
    def __init__(self, error: Exception | None = None) -> None:
        self.observations: list[RawObservation] = []
        self._error = error

    def write(self, observation: RawObservation) -> None:
        if self._error is not None:
            raise self._error
        self.observations.append(observation)


class FakeGpsdClient:
    def __init__(self, fix: GpsFix | None) -> None:
        self._fix = fix

    def get_latest_fix(self) -> GpsFix | None:
        return self._fix


class FakeHopper:
    def __init__(self) -> None:
        self.started = Event()
        self.stopped = Event()

    def run(self, stop_event: Event) -> None:
        self.started.set()
        stop_event.wait(1.0)
        if stop_event.is_set():
            self.stopped.set()


def _metadata() -> WifiFrameMetadata:
    return WifiFrameMetadata(
        observed_at_utc=OBSERVED_AT_UTC,
        bssid=SYNTHETIC_BSSID,
        ssid=SYNTHETIC_SSID,
        rssi_dbm=-42,
        channel=1,
        frequency_mhz=2412,
        band="2.4GHz",
        encryption="OPEN",
        frame_type="BEACON",
    )


def _fix() -> GpsFix:
    return GpsFix(
        latitude=0.0,
        longitude=0.0,
        mode=3,
        accuracy_m=4.0,
        observed_at_utc=OBSERVED_AT_UTC,
    )


def _single_packet_sniffer(packet: object):
    def sniff(*, iface: str, prn: object, store: bool, timeout: float) -> None:
        assert iface == "synthetic-monitor0"
        assert store is False
        assert timeout == 1.0
        assert callable(prn)
        prn(packet)

    return sniff


def test_packet_and_gps_fix_produce_one_raw_observation() -> None:
    packet = object()
    writer = FakeWriter()
    service = CollectorService(
        measurement_round_id="synthetic-round-collector",
        writer=writer,
        gpsd_client=FakeGpsdClient(_fix()),
        frame_parser=lambda received, observed_at: (
            _metadata() if received is packet and observed_at == OBSERVED_AT_UTC else None
        ),
        clock=lambda: OBSERVED_AT_UTC,
    )

    summary = service.run("synthetic-monitor0", 1.0, _single_packet_sniffer(packet))

    assert summary.stored_observations == 1
    assert writer.observations == [
        RawObservation(
            measurement_round_id="synthetic-round-collector",
            observed_at_utc=OBSERVED_AT_UTC,
            bssid=SYNTHETIC_BSSID,
            ssid=SYNTHETIC_SSID,
            rssi_dbm=-42,
            channel=1,
            frequency_mhz=2412,
            band="2.4GHz",
            encryption="OPEN",
            frame_type="BEACON",
            latitude=0.0,
            longitude=0.0,
            gps_mode=3,
            gps_accuracy_m=4.0,
        )
    ]


def test_missing_required_gps_fix_is_not_stored() -> None:
    writer = FakeWriter()
    service = CollectorService(
        measurement_round_id="synthetic-round-collector",
        writer=writer,
        gpsd_client=FakeGpsdClient(None),
        require_gps_fix=True,
        frame_parser=lambda packet, observed_at: _metadata(),
    )

    service.process_packet(object())

    assert writer.observations == []
    assert service.summary().missing_gps_fixes == 1


def test_unsupported_packet_is_not_stored() -> None:
    writer = FakeWriter()
    service = CollectorService(
        measurement_round_id="synthetic-round-collector",
        writer=writer,
        frame_parser=lambda packet, observed_at: None,
    )

    service.process_packet(object())

    assert writer.observations == []
    assert service.summary().unsupported_packets == 1


def test_missing_optional_gps_fix_is_stored_with_empty_gps_fields() -> None:
    writer = FakeWriter()
    service = CollectorService(
        measurement_round_id="synthetic-round-collector",
        writer=writer,
        frame_parser=lambda packet, observed_at: _metadata(),
    )

    service.process_packet(object())

    assert len(writer.observations) == 1
    observation = writer.observations[0]
    assert observation.latitude is None
    assert observation.longitude is None
    assert observation.gps_mode is None
    assert observation.gps_accuracy_m is None


def test_writer_error_is_controlled_and_stops_hopper() -> None:
    packet = object()
    hopper = FakeHopper()
    service = CollectorService(
        measurement_round_id="synthetic-round-collector",
        writer=FakeWriter(RuntimeError("synthetic writer failure")),
        channel_hopper=hopper,
        frame_parser=lambda received, observed_at: _metadata(),
    )

    def sniff(*, iface: str, prn: object, store: bool, timeout: float) -> None:
        del iface, store, timeout
        assert hopper.started.wait(1.0)
        assert callable(prn)
        prn(packet)

    with pytest.raises(CollectionError, match="observation_write_failed"):
        service.run("synthetic-monitor0", 1.0, sniff)

    assert hopper.stopped.wait(1.0)


def test_hopper_is_stopped_after_success() -> None:
    hopper = FakeHopper()
    service = CollectorService(
        measurement_round_id="synthetic-round-collector",
        writer=FakeWriter(),
        channel_hopper=hopper,
        frame_parser=lambda packet, observed_at: None,
    )

    service.run("synthetic-monitor0", 1.0, _single_packet_sniffer(object()))

    assert hopper.started.is_set()
    assert hopper.stopped.wait(1.0)


def test_logs_do_not_contain_raw_measurement_values(
    caplog: pytest.LogCaptureFixture,
) -> None:
    writer = FakeWriter()
    service = CollectorService(
        measurement_round_id="synthetic-round-collector",
        writer=writer,
        gpsd_client=FakeGpsdClient(_fix()),
        frame_parser=lambda packet, observed_at: _metadata(),
    )

    with caplog.at_level(logging.INFO):
        service.process_packet(object())

    assert SYNTHETIC_BSSID not in caplog.text
    assert SYNTHETIC_SSID not in caplog.text
    assert "0.0" not in caplog.text


def test_measurement_round_id_is_required() -> None:
    with pytest.raises(ValueError, match="measurement_round_id is required"):
        CollectorService(measurement_round_id=" ", writer=FakeWriter())


def test_cli_returns_controlled_nonzero_exit_without_leaking_setup_error(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    from cyberbrein.collection import cli

    sensitive_error = "AA:BB:CC:DD:EE:FF CYBERBREIN_TEST_SECRET_SSID 52.123,4.567"

    def failing_writer(database_path: str) -> None:
        del database_path
        raise RuntimeError(sensitive_error)

    monkeypatch.setattr(cli, "SQLiteObservationWriter", failing_writer)

    exit_code = cli.main(
        [
            "--interface",
            "synthetic-monitor0",
            "--database-path",
            "synthetic.sqlite",
            "--measurement-round-id",
            "synthetic-round-collector",
        ]
    )

    captured = capsys.readouterr()
    assert exit_code == 2
    assert "configuration_failed" in captured.err
    assert sensitive_error not in captured.out
    assert sensitive_error not in captured.err
