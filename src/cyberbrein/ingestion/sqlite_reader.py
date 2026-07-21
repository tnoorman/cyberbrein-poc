import sqlite3
from collections.abc import Iterator
from datetime import datetime
from pathlib import Path
from typing import cast

from cyberbrein.collection.models import RawObservation


def _parse_timestamp(value: object) -> datetime | None:
    if not isinstance(value, str):
        return None
    try:
        return datetime.fromisoformat(value)
    except ValueError:
        return None


def read_raw_observations(database_path: str | Path) -> Iterator[RawObservation]:
    """Read the explicit Ingestion input contract from the Collection buffer."""
    connection = sqlite3.connect(database_path)
    connection.row_factory = sqlite3.Row
    try:
        rows = connection.execute(
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
            ORDER BY raw_observation_id
            """
        )
        for row in rows:
            yield RawObservation(
                measurement_round_id=row["measurement_round_id"],
                observed_at_utc=cast(datetime, _parse_timestamp(row["observed_at_utc"])),
                bssid=row["bssid"],
                ssid=row["ssid"],
                rssi_dbm=row["rssi_dbm"],
                channel=row["channel"],
                frequency_mhz=row["frequency_mhz"],
                band=row["band"],
                encryption=row["encryption"],
                frame_type=row["frame_type"],
                latitude=row["latitude"],
                longitude=row["longitude"],
                gps_mode=row["gps_mode"],
                gps_accuracy_m=row["gps_accuracy_m"],
            )
    finally:
        connection.close()
