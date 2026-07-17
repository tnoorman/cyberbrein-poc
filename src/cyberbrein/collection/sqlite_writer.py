import os
import sqlite3
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path

from cyberbrein.collection.models import RawObservation


class ObservationTransaction:
    def __init__(self, connection: sqlite3.Connection) -> None:
        self._connection = connection

    def add(self, observation: RawObservation) -> None:
        """Add one raw observation to the active transaction."""
        self._connection.execute(
            """
            INSERT INTO measurement_round (measurement_round_id)
            VALUES (:measurement_round_id)
            ON CONFLICT (measurement_round_id) DO NOTHING
            """,
            {"measurement_round_id": observation.measurement_round_id},
        )
        self._connection.execute(
            """
            INSERT INTO raw_observation (
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
            )
            VALUES (
                :measurement_round_id,
                :observed_at_utc,
                :bssid,
                :ssid,
                :rssi_dbm,
                :channel,
                :frequency_mhz,
                :band,
                :encryption,
                :frame_type,
                :latitude,
                :longitude,
                :gps_mode,
                :gps_accuracy_m
            )
            """,
            {
                "measurement_round_id": observation.measurement_round_id,
                "observed_at_utc": observation.observed_at_utc.isoformat(),
                "bssid": observation.bssid,
                "ssid": observation.ssid,
                "rssi_dbm": observation.rssi_dbm,
                "channel": observation.channel,
                "frequency_mhz": observation.frequency_mhz,
                "band": observation.band,
                "encryption": observation.encryption,
                "frame_type": observation.frame_type,
                "latitude": observation.latitude,
                "longitude": observation.longitude,
                "gps_mode": observation.gps_mode,
                "gps_accuracy_m": observation.gps_accuracy_m,
            },
        )


class SQLiteObservationWriter:
    def __init__(self, database_path: str | Path) -> None:
        self._database_path = Path(database_path)
        self._create_database_file()
        self._initialize_schema()

    def _create_database_file(self) -> None:
        if os.name != "posix":
            return
        descriptor = os.open(self._database_path, os.O_CREAT | os.O_RDWR, 0o600)
        os.close(descriptor)
        os.chmod(self._database_path, 0o600)

    def _connect(self) -> sqlite3.Connection:
        connection = sqlite3.connect(self._database_path)
        connection.execute("PRAGMA foreign_keys = ON")
        return connection

    def _initialize_schema(self) -> None:
        connection = self._connect()
        try:
            with connection:
                connection.execute(
                    """
                    CREATE TABLE IF NOT EXISTS measurement_round (
                        measurement_round_id TEXT PRIMARY KEY
                    )
                    """
                )
                connection.execute(
                    """
                    CREATE TABLE IF NOT EXISTS raw_observation (
                        raw_observation_id INTEGER PRIMARY KEY AUTOINCREMENT,
                        measurement_round_id TEXT NOT NULL,
                        observed_at_utc TEXT NOT NULL,
                        bssid TEXT NOT NULL,
                        ssid TEXT,
                        rssi_dbm INTEGER NOT NULL,
                        channel INTEGER NOT NULL,
                        frequency_mhz INTEGER,
                        band TEXT NOT NULL,
                        encryption TEXT NOT NULL,
                        frame_type TEXT NOT NULL,
                        latitude REAL,
                        longitude REAL,
                        gps_mode INTEGER,
                        gps_accuracy_m REAL,
                        FOREIGN KEY (measurement_round_id)
                            REFERENCES measurement_round (measurement_round_id)
                    )
                    """
                )
        finally:
            connection.close()

    def write(self, observation: RawObservation) -> None:
        """Persist one raw observation in its own transaction."""
        with self.transaction() as transaction:
            transaction.add(observation)

    @contextmanager
    def transaction(self) -> Iterator[ObservationTransaction]:
        """Create a transaction that commits atomically or rolls back on failure."""
        connection = self._connect()
        try:
            connection.execute("BEGIN")
            yield ObservationTransaction(connection)
        except BaseException:
            connection.rollback()
            raise
        else:
            connection.commit()
        finally:
            connection.close()
