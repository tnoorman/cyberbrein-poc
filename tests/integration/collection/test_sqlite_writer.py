import os
import sqlite3
import stat
from dataclasses import replace
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

from cyberbrein.collection.models import RawObservation
from cyberbrein.collection.sqlite_writer import SQLiteObservationWriter

SYNTHETIC_BSSID = "02:00:00:00:00:20"
SYNTHETIC_SSID = "SYNTHETIC-SQLITE-NETWORK"


def _observation(**changes: object) -> RawObservation:
    observation = RawObservation(
        measurement_round_id="synthetic-round-001",
        observed_at_utc=datetime(2026, 1, 1, 12, 0, tzinfo=timezone.utc),
        bssid=SYNTHETIC_BSSID,
        ssid=SYNTHETIC_SSID,
        rssi_dbm=-42,
        channel=1,
        frequency_mhz=2412,
        band="2.4GHz",
        encryption="OPN",
        frame_type="BEACON",
        latitude=0.0,
        longitude=0.0,
        gps_mode=3,
        gps_accuracy_m=5.0,
    )
    return replace(observation, **changes)


def _table_names(database_path: Path) -> set[str]:
    with sqlite3.connect(database_path) as connection:
        rows = connection.execute("SELECT name FROM sqlite_master WHERE type = 'table'").fetchall()
    return {row[0] for row in rows}


def _row_count(database_path: Path, table_name: str) -> int:
    queries = {
        "measurement_round": "SELECT COUNT(*) FROM measurement_round",
        "raw_observation": "SELECT COUNT(*) FROM raw_observation",
    }
    try:
        query = queries[table_name]
    except KeyError as error:
        raise ValueError("unsupported test table") from error
    with sqlite3.connect(database_path) as connection:
        row = connection.execute(query).fetchone()
    assert row is not None
    return int(row[0])


def test_schema_is_created(tmp_path: Path) -> None:
    database_path = tmp_path / "collection.sqlite"

    SQLiteObservationWriter(database_path)

    assert {"measurement_round", "raw_observation"} <= _table_names(database_path)


def test_one_raw_observation_is_stored(tmp_path: Path) -> None:
    database_path = tmp_path / "collection.sqlite"
    writer = SQLiteObservationWriter(database_path)

    writer.write(_observation())

    connection = sqlite3.connect(database_path)
    connection.row_factory = sqlite3.Row
    try:
        row = connection.execute(
            """
            SELECT
                measurement_round_id,
                observed_at_utc,
                bssid,
                ssid,
                rssi_dbm,
                channel,
                frequency_mhz,
                band,
                encryption,
                frame_type,
                latitude,
                longitude,
                gps_mode,
                gps_accuracy_m
            FROM raw_observation
            """
        ).fetchone()
    finally:
        connection.close()

    assert row is not None
    assert dict(row) == {
        "measurement_round_id": "synthetic-round-001",
        "observed_at_utc": "2026-01-01T12:00:00+00:00",
        "bssid": SYNTHETIC_BSSID,
        "ssid": SYNTHETIC_SSID,
        "rssi_dbm": -42,
        "channel": 1,
        "frequency_mhz": 2412,
        "band": "2.4GHz",
        "encryption": "OPN",
        "frame_type": "BEACON",
        "latitude": 0.0,
        "longitude": 0.0,
        "gps_mode": 3,
        "gps_accuracy_m": 5.0,
    }


def test_multiple_inserts_commit_in_one_transaction(tmp_path: Path) -> None:
    database_path = tmp_path / "collection.sqlite"
    writer = SQLiteObservationWriter(database_path)
    first = _observation()
    second = _observation(
        observed_at_utc=first.observed_at_utc + timedelta(seconds=1),
        bssid="02:00:00:00:00:21",
        ssid="SYNTHETIC-SQLITE-NETWORK-2",
    )

    with writer.transaction() as transaction:
        transaction.add(first)
        transaction.add(second)

    assert _row_count(database_path, "measurement_round") == 1
    assert _row_count(database_path, "raw_observation") == 2


def test_transaction_rolls_back_on_forced_error(tmp_path: Path) -> None:
    database_path = tmp_path / "collection.sqlite"
    writer = SQLiteObservationWriter(database_path)

    with pytest.raises(RuntimeError, match="synthetic forced failure"):
        with writer.transaction() as transaction:
            transaction.add(_observation())
            raise RuntimeError("synthetic forced failure")

    assert _row_count(database_path, "measurement_round") == 0
    assert _row_count(database_path, "raw_observation") == 0


@pytest.mark.skipif(os.name != "posix", reason="POSIX file modes are only available on Linux")
def test_database_permissions_are_not_broader_than_0600(tmp_path: Path) -> None:
    database_path = tmp_path / "collection.sqlite"

    SQLiteObservationWriter(database_path)

    permissions = stat.S_IMODE(database_path.stat().st_mode)
    assert permissions & ~0o600 == 0


def test_sql_injection_like_ssid_is_stored_as_a_value(tmp_path: Path) -> None:
    database_path = tmp_path / "collection.sqlite"
    writer = SQLiteObservationWriter(database_path)
    synthetic_ssid = "SYNTHETIC'); DROP TABLE raw_observation; --"

    writer.write(_observation(ssid=synthetic_ssid))

    with sqlite3.connect(database_path) as connection:
        row = connection.execute("SELECT ssid FROM raw_observation").fetchone()
    assert row is not None
    assert row[0] == synthetic_ssid
    assert "raw_observation" in _table_names(database_path)


def test_schema_has_no_pseudonym_or_secret_columns(tmp_path: Path) -> None:
    database_path = tmp_path / "collection.sqlite"

    SQLiteObservationWriter(database_path)

    with sqlite3.connect(database_path) as connection:
        raw_rows = connection.execute("PRAGMA table_info(raw_observation)").fetchall()
        round_rows = connection.execute("PRAGMA table_info(measurement_round)").fetchall()
    raw_column_names = {row[1] for row in raw_rows}
    round_column_names = {row[1] for row in round_rows}
    assert raw_column_names == {
        "raw_observation_id",
        "measurement_round_id",
        "observed_at_utc",
        "bssid",
        "ssid",
        "rssi_dbm",
        "channel",
        "frequency_mhz",
        "band",
        "encryption",
        "frame_type",
        "latitude",
        "longitude",
        "gps_mode",
        "gps_accuracy_m",
    }
    assert round_column_names == {"measurement_round_id"}
