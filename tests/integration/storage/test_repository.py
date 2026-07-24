from dataclasses import replace
from datetime import datetime, timezone
from pathlib import Path

import pytest
from sqlalchemy import create_engine, inspect, select

from cyberbrein.processing.models import (
    AttentionLevel,
    EncryptionCategory,
    NetworkFinding,
    ScoredNetworkFinding,
    ScoreFactor,
)
from cyberbrein.storage.repository import (
    StorageRepository,
    measurement_rounds,
    network_findings,
    score_factors,
)


def _scored_finding(**changes: object) -> ScoredNetworkFinding:
    observed_at = datetime(2026, 1, 1, 12, 0, tzinfo=timezone.utc)
    finding = NetworkFinding(
        measurement_round_id="synthetic-round",
        zone_id="zone-a",
        network_id="synthetic-network-id",
        observation_count=2,
        first_observed_at_utc=observed_at,
        last_observed_at_utc=observed_at,
        representative_observed_at_utc=observed_at,
        representative_latitude=1.0,
        representative_longitude=2.0,
        representative_rssi_dbm=-60,
        representative_channel=36,
        representative_frequency_mhz=5180,
        representative_band="5GHz",
        encryption=EncryptionCategory.WPA2,
        ssid_present=True,
    )
    finding_changes = {key: value for key, value in changes.items() if hasattr(finding, key)}
    finding = replace(finding, **finding_changes)
    factors = (
        ScoreFactor("signal_strength", contribution=1, weight=1),
        ScoreFactor("encryption", contribution=1, weight=2),
        ScoreFactor("observation_frequency", contribution=0, weight=1),
    )
    return ScoredNetworkFinding(finding, 3, AttentionLevel.YELLOW, factors)


@pytest.fixture
def repository(tmp_path: Path) -> tuple[StorageRepository, Path]:
    database_path = tmp_path / "storage.sqlite"
    instance = StorageRepository(f"sqlite:///{database_path}")
    instance.initialize()
    yield instance, database_path
    instance.close()


def test_round_trip_preserves_processed_contract(
    repository: tuple[StorageRepository, Path],
) -> None:
    instance, _ = repository
    expected = _scored_finding()
    instance.replace_measurement_round("synthetic-round", [expected])
    assert instance.load_measurement_round("synthetic-round") == (expected,)


def test_replacing_round_removes_old_findings_and_factors(
    repository: tuple[StorageRepository, Path],
) -> None:
    instance, _ = repository
    instance.replace_measurement_round("synthetic-round", [_scored_finding()])
    replacement = _scored_finding(network_id="replacement-network")
    instance.replace_measurement_round("synthetic-round", [replacement])
    assert instance.load_measurement_round("synthetic-round") == (replacement,)


def test_invalid_replacement_leaves_existing_round_unchanged(
    repository: tuple[StorageRepository, Path],
) -> None:
    instance, _ = repository
    existing = _scored_finding()
    instance.replace_measurement_round("synthetic-round", [existing])
    invalid = _scored_finding(measurement_round_id="different-round")
    with pytest.raises(ValueError, match="requested measurement round"):
        instance.replace_measurement_round("synthetic-round", [invalid])
    assert instance.load_measurement_round("synthetic-round") == (existing,)


def test_empty_completed_round_is_retained(repository: tuple[StorageRepository, Path]) -> None:
    instance, database_path = repository
    instance.replace_measurement_round("empty-round", [])
    assert instance.load_measurement_round("empty-round") == ()
    engine = create_engine(f"sqlite:///{database_path}")
    with engine.connect() as connection:
        assert connection.execute(select(measurement_rounds.c.measurement_round_id)).scalar_one()
    engine.dispose()


def test_schema_contains_no_raw_identifiers_or_secret(
    repository: tuple[StorageRepository, Path],
) -> None:
    _, database_path = repository
    engine = create_engine(f"sqlite:///{database_path}")
    schema = inspect(engine)
    columns = {
        column["name"]
        for table_name in schema.get_table_names()
        for column in schema.get_columns(table_name)
    }
    assert {"bssid", "ssid", "secret", "raw_observation"}.isdisjoint(columns)
    assert {measurement_rounds.name, network_findings.name, score_factors.name} == set(
        schema.get_table_names()
    )
    engine.dispose()


def test_schema_stores_explainable_score_components(
    repository: tuple[StorageRepository, Path],
) -> None:
    instance, database_path = repository
    instance.replace_measurement_round("synthetic-round", [_scored_finding()])
    engine = create_engine(f"sqlite:///{database_path}")
    with engine.connect() as connection:
        finding = connection.execute(select(network_findings)).mappings().one()
        factors = connection.execute(
            select(score_factors).order_by(score_factors.c.position)
        ).mappings()
        assert finding["score"] == 3
        assert finding["attention_level"] == "YELLOW"
        assert [
            (
                factor["name"],
                factor["contribution"],
                factor["weight"],
                factor["weighted_points"],
            )
            for factor in factors
        ] == [
            ("signal_strength", 1, 1, 1),
            ("encryption", 1, 2, 2),
            ("observation_frequency", 0, 1, 0),
        ]
    engine.dispose()


def test_sqlite_storage_file_is_restricted(repository: tuple[StorageRepository, Path]) -> None:
    _, database_path = repository
    assert database_path.stat().st_mode & 0o777 == 0o600
