from dataclasses import replace
from datetime import datetime, timezone

import pytest
from shapely.geometry import Polygon
from sqlalchemy import create_engine, inspect, select, text

from cyberbrein.processing.models import (
    ApprovedZone,
    AttentionLevel,
    EncryptionCategory,
    NetworkFinding,
    ScoredNetworkFinding,
    ScoreFactor,
)
from cyberbrein.storage.repository import (
    ActiveMeasurementRoundError,
    MeasurementRoundNotFoundError,
    StorageRepository,
    measurement_rounds,
    network_findings,
    network_scores,
    score_factors,
    zones,
)


def _zone(zone_id: str = "zone-a") -> ApprovedZone:
    return ApprovedZone(zone_id, Polygon([(0, 0), (1, 0), (1, 1), (0, 1)]))


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
        representative_latitude=0.5,
        representative_longitude=0.5,
        average_rssi_dbm=-65.0,
        strongest_rssi_dbm=-60,
        representative_channel=36,
        representative_frequency_mhz=5180,
        representative_band="5GHz",
        encryption=EncryptionCategory.OUTDATED,
        ssid_present=True,
    )
    finding_changes = {key: value for key, value in changes.items() if hasattr(finding, key)}
    finding = replace(finding, **finding_changes)
    factors = (
        ScoreFactor("signal_strength", "-60 dBm", "medium", 1, 1),
        ScoreFactor("encryption", "OUTDATED", "outdated_or_unknown", 1, 2),
        ScoreFactor("observation_frequency", "2", "multiple", 1, 1),
    )
    return ScoredNetworkFinding(finding, 4, AttentionLevel.YELLOW, factors)


@pytest.fixture
def repository(clean_postgis: str) -> StorageRepository:
    instance = StorageRepository(clean_postgis)
    instance.initialize()
    yield instance
    instance.close()


def test_round_trip_preserves_processed_contract(repository: StorageRepository) -> None:
    expected = _scored_finding()
    repository.replace_measurement_round("synthetic-round", [_zone()], [expected])
    assert repository.load_measurement_round("synthetic-round") == (expected,)
    stored_zone = repository.load_zones("synthetic-round")
    assert [zone.zone_id for zone in stored_zone] == ["zone-a"]
    assert stored_zone[0].geometry.equals(_zone().geometry)


def test_replacing_same_round_is_atomic(repository: StorageRepository) -> None:
    repository.replace_measurement_round("synthetic-round", [_zone()], [_scored_finding()])
    replacement = _scored_finding(network_id="replacement-network")
    repository.replace_measurement_round("synthetic-round", [_zone()], [replacement])
    assert repository.load_measurement_round("synthetic-round") == (replacement,)


def test_different_active_round_is_refused(repository: StorageRepository) -> None:
    repository.replace_measurement_round("synthetic-round", [_zone()], [_scored_finding()])
    with pytest.raises(ActiveMeasurementRoundError):
        repository.replace_measurement_round("other-round", [_zone()], [])
    assert repository.load_measurement_round("synthetic-round") == (_scored_finding(),)


def test_empty_round_retains_approved_zone(repository: StorageRepository) -> None:
    repository.replace_measurement_round("empty-round", [_zone()], [])
    assert repository.load_measurement_round("empty-round") == ()
    stored_zone = repository.load_zones("empty-round")
    assert [zone.zone_id for zone in stored_zone] == ["zone-a"]
    assert stored_zone[0].geometry.equals(_zone().geometry)


def test_delete_measurement_round_cascades_and_verifies_all_tables(
    repository: StorageRepository,
) -> None:
    repository.replace_measurement_round("synthetic-round", [_zone()], [_scored_finding()])

    result = repository.delete_measurement_round("synthetic-round")

    assert result.before.measurement_rounds == 1
    assert result.before.zones == 1
    assert result.before.network_findings == 1
    assert result.before.network_scores == 1
    assert result.before.score_factors == 3
    assert result.after.all_zero

    replacement = _scored_finding(
        measurement_round_id="replacement-round",
        network_id="replacement-network",
    )
    repository.replace_measurement_round("replacement-round", [_zone()], [replacement])
    assert repository.load_measurement_round("replacement-round") == (replacement,)


def test_delete_unknown_measurement_round_is_not_reported_as_success(
    repository: StorageRepository,
) -> None:
    with pytest.raises(MeasurementRoundNotFoundError):
        repository.delete_measurement_round("missing-round")


def test_invalid_replacement_leaves_existing_round_unchanged(
    repository: StorageRepository,
) -> None:
    expected = _scored_finding()
    repository.replace_measurement_round("synthetic-round", [_zone()], [expected])
    invalid = _scored_finding(measurement_round_id="different-round")
    with pytest.raises(ValueError, match="requested measurement round"):
        repository.replace_measurement_round("synthetic-round", [_zone()], [invalid])
    assert repository.load_measurement_round("synthetic-round") == (expected,)


def test_schema_has_postgis_types_indexes_and_no_raw_identifiers(
    repository: StorageRepository,
    postgres_url: str,
) -> None:
    del repository
    engine = create_engine(postgres_url)
    schema = inspect(engine)
    table_names = set(schema.get_table_names())
    application_tables = {
        "measurement_round",
        "zone",
        "network_finding",
        "network_score",
        "score_factor",
    }
    assert application_tables <= table_names
    assert "spatial_ref_sys" in table_names
    columns = {
        column["name"]
        for table_name in application_tables
        for column in schema.get_columns(table_name)
    }
    assert {"bssid", "ssid", "secret", "raw_observation"}.isdisjoint(columns)
    with engine.connect() as connection:
        geometry = connection.execute(
            text(
                "SELECT f_table_name, f_geometry_column, type, srid "
                "FROM geometry_columns WHERE f_table_name IN ('zone', 'network_finding') "
                "ORDER BY f_table_name"
            )
        ).all()
    assert geometry == [
        ("network_finding", "display_point", "POINT", 4326),
        ("zone", "polygon", "MULTIPOLYGON", 4326),
    ]
    assert any(
        index["name"].endswith("display_point") for index in schema.get_indexes("network_finding")
    )
    assert any(index["name"].endswith("polygon") for index in schema.get_indexes("zone"))
    engine.dispose()


def test_schema_stores_separate_scores_and_explainable_factors(
    repository: StorageRepository,
    postgres_url: str,
) -> None:
    repository.replace_measurement_round("synthetic-round", [_zone()], [_scored_finding()])
    engine = create_engine(postgres_url)
    with engine.connect() as connection:
        round_row = connection.execute(select(measurement_rounds)).mappings().one()
        finding = connection.execute(select(network_findings)).mappings().one()
        score = connection.execute(select(network_scores)).mappings().one()
        factors = connection.execute(
            select(score_factors).order_by(score_factors.c.position)
        ).mappings()
        zone_count = connection.execute(select(zones.c.zone_id)).scalar_one()
    assert round_row["status"] == "COMPLETED"
    assert finding["average_rssi_dbm"] == -65.0
    assert score["total_points"] == 4
    assert score["score_color"] == "YELLOW"
    assert zone_count == "zone-a"
    assert [
        (
            factor["factor_type"],
            factor["observed_value"],
            factor["category"],
            factor["points"],
            factor["weight"],
        )
        for factor in factors
    ] == [
        ("signal_strength", "-60 dBm", "medium", 1, 1),
        ("encryption", "OUTDATED", "outdated_or_unknown", 1, 2),
        ("observation_frequency", "2", "multiple", 1, 1),
    ]
    engine.dispose()


def test_non_postgresql_backend_is_rejected() -> None:
    with pytest.raises(ValueError, match="PostgreSQL"):
        StorageRepository("sqlite:///:memory:")
