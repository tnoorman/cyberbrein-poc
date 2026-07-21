from dataclasses import fields, replace
from datetime import datetime, timezone
from pathlib import Path

import pytest
from scapy.layers.dot11 import Dot11, Dot11Beacon, Dot11Elt, RadioTap

from cyberbrein.collection.frame_parser import parse_wifi_frame
from cyberbrein.collection.models import RawObservation
from cyberbrein.collection.sqlite_writer import SQLiteObservationWriter
from cyberbrein.ingestion.models import AcceptedObservation
from cyberbrein.ingestion.pseudonymizer import pseudonymize_bssid
from cyberbrein.ingestion.service import IngestionService
from cyberbrein.ingestion.validator import (
    INVALID_GPS_MODE,
    INVALID_LATITUDE,
    INVALID_RSSI,
    MISSING_BSSID,
)

SYNTHETIC_BSSID = "02:00:00:00:00:40"
SYNTHETIC_SSID = "SYNTHETIC-INGESTION-NETWORK"
TEST_SECRET = "synthetic-ingestion-secret"
OBSERVED_AT_UTC = datetime(2026, 1, 1, 12, 0, tzinfo=timezone.utc)


def _synthetic_frame() -> RadioTap:
    return (
        RadioTap(
            present="Channel+dBm_AntSignal",
            ChannelFrequency=2412,
            ChannelFlags=0,
            dBm_AntSignal=-42,
        )
        / Dot11(
            type=0,
            subtype=8,
            addr1="ff:ff:ff:ff:ff:ff",
            addr2=SYNTHETIC_BSSID,
            addr3=SYNTHETIC_BSSID,
        )
        / Dot11Beacon(cap="ESS")
        / Dot11Elt(ID=0, info=SYNTHETIC_SSID.encode("utf-8"))
        / Dot11Elt(ID=3, info=b"\x01")
    )


def _raw_observation() -> RawObservation:
    metadata = parse_wifi_frame(_synthetic_frame(), OBSERVED_AT_UTC)
    assert metadata is not None
    return RawObservation(
        measurement_round_id="synthetic-round-ingestion",
        observed_at_utc=metadata.observed_at_utc,
        bssid=metadata.bssid,
        ssid=metadata.ssid,
        rssi_dbm=metadata.rssi_dbm,
        channel=metadata.channel,
        frequency_mhz=metadata.frequency_mhz,
        band=metadata.band,
        encryption=metadata.encryption,
        frame_type=metadata.frame_type,
        latitude=0.0,
        longitude=0.0,
        gps_mode=3,
        gps_accuracy_m=None,
    )


def test_synthetic_frame_flows_to_private_accepted_observation(
    tmp_path: Path,
    caplog: pytest.LogCaptureFixture,
    capsys: pytest.CaptureFixture[str],
) -> None:
    database_path = tmp_path / "collection.sqlite"
    writer = SQLiteObservationWriter(database_path)
    writer.write(_raw_observation())

    result = IngestionService(database_path).ingest(TEST_SECRET)

    assert result.accepted_count == 1
    assert result.rejected_count == 0
    assert result.rejection_reasons == {}
    accepted = result.accepted[0]
    assert accepted == AcceptedObservation(
        measurement_round_id="synthetic-round-ingestion",
        observed_at_utc=OBSERVED_AT_UTC,
        network_id=pseudonymize_bssid(SYNTHETIC_BSSID, TEST_SECRET),
        ssid_present=True,
        rssi_dbm=-42,
        channel=1,
        frequency_mhz=2412,
        band="2.4GHz",
        encryption="OPN",
        latitude=0.0,
        longitude=0.0,
        gps_mode=3,
        gps_accuracy_m=None,
    )

    accepted_field_names = {field.name for field in fields(AcceptedObservation)}
    assert {"bssid", "ssid", "secret"}.isdisjoint(accepted_field_names)
    assert SYNTHETIC_BSSID not in repr(accepted)
    assert SYNTHETIC_BSSID not in repr(result)
    assert SYNTHETIC_BSSID not in repr(result.rejection_reasons)
    assert SYNTHETIC_SSID not in repr(accepted)
    assert SYNTHETIC_SSID not in repr(result)
    assert TEST_SECRET not in repr(result)
    assert SYNTHETIC_BSSID not in caplog.text
    assert SYNTHETIC_SSID not in caplog.text
    assert TEST_SECRET not in caplog.text
    captured = capsys.readouterr()
    assert SYNTHETIC_BSSID not in captured.out
    assert SYNTHETIC_BSSID not in captured.err
    assert SYNTHETIC_SSID not in captured.out
    assert SYNTHETIC_SSID not in captured.err
    assert TEST_SECRET not in captured.out
    assert TEST_SECRET not in captured.err
    assert database_path.exists()
    assert TEST_SECRET.encode("utf-8") not in database_path.read_bytes()


def test_rejected_rows_are_counted_by_safe_reason(tmp_path: Path) -> None:
    database_path = tmp_path / "collection.sqlite"
    writer = SQLiteObservationWriter(database_path)
    valid = _raw_observation()
    with writer.transaction() as transaction:
        transaction.add(valid)
        transaction.add(replace(valid, bssid=""))
        transaction.add(replace(valid, rssi_dbm=-121))
        transaction.add(replace(valid, gps_mode=2))
        transaction.add(replace(valid, latitude=91.0))

    result = IngestionService(database_path).ingest(TEST_SECRET)

    assert result.accepted_count == 1
    assert result.rejected_count == 4
    assert result.rejection_reasons == {
        INVALID_GPS_MODE: 1,
        INVALID_LATITUDE: 1,
        INVALID_RSSI: 1,
        MISSING_BSSID: 1,
    }
    assert SYNTHETIC_BSSID not in repr(result.rejection_reasons)


def test_different_secrets_produce_different_network_ids(tmp_path: Path) -> None:
    database_path = tmp_path / "collection.sqlite"
    SQLiteObservationWriter(database_path).write(_raw_observation())
    service = IngestionService(database_path)

    first_result = service.ingest("synthetic-secret-one")
    second_result = service.ingest("synthetic-secret-two")

    assert first_result.accepted[0].network_id != second_result.accepted[0].network_id
    assert database_path.exists()


def test_missing_ssid_becomes_only_false_presence_flag(tmp_path: Path) -> None:
    database_path = tmp_path / "collection.sqlite"
    SQLiteObservationWriter(database_path).write(replace(_raw_observation(), ssid=None))

    result = IngestionService(database_path).ingest(TEST_SECRET)

    accepted = result.accepted[0]
    assert accepted.ssid_present is False
    assert not hasattr(accepted, "ssid")


def test_service_requires_runtime_secret(tmp_path: Path) -> None:
    database_path = tmp_path / "collection.sqlite"
    SQLiteObservationWriter(database_path).write(_raw_observation())

    with pytest.raises(ValueError, match="secret is required"):
        IngestionService(database_path).ingest("")
