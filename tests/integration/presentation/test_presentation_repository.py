from dataclasses import replace
from datetime import datetime, timezone

from shapely.geometry import Polygon

from cyberbrein.presentation.models import DashboardFilters
from cyberbrein.presentation.repository import PresentationRepository
from cyberbrein.processing.models import (
    ApprovedZone,
    AttentionLevel,
    EncryptionCategory,
    NetworkFinding,
    ScoredNetworkFinding,
    ScoreFactor,
)
from cyberbrein.storage.repository import StorageRepository


def _scored(
    *,
    network_id: str,
    zone_id: str,
    band: str,
    channel: int,
    encryption: EncryptionCategory,
    color: AttentionLevel,
    score: int,
    signal_category: str,
) -> ScoredNetworkFinding:
    observed_at = datetime(2026, 1, 1, 12, 0, tzinfo=timezone.utc)
    finding = NetworkFinding(
        measurement_round_id="round-a",
        zone_id=zone_id,
        network_id=network_id,
        observation_count=2,
        first_observed_at_utc=observed_at,
        last_observed_at_utc=observed_at,
        representative_observed_at_utc=observed_at,
        representative_latitude=0.5,
        representative_longitude=0.5,
        average_rssi_dbm=-65.0,
        strongest_rssi_dbm=-60,
        representative_channel=channel,
        representative_frequency_mhz=5180 if band == "5GHz" else 2412,
        representative_band=band,
        encryption=encryption,
        ssid_present=False,
    )
    signal_points = {"weak": 0, "medium": 1, "strong": 2}[signal_category]
    factors = (
        ScoreFactor("signal_strength", "-60 dBm", signal_category, signal_points, 1),
        ScoreFactor("encryption", encryption.value, "current", 0, 2),
        ScoreFactor("observation_frequency", "2", "multiple", 1, 1),
    )
    return ScoredNetworkFinding(finding, score, color, tuple(factors))


def _dataset() -> tuple[tuple[ApprovedZone, ...], tuple[ScoredNetworkFinding, ...]]:
    zones = (
        ApprovedZone("zone-a", Polygon([(0, 0), (1, 0), (1, 1), (0, 1)])),
        ApprovedZone("zone-b", Polygon([(2, 0), (3, 0), (3, 1), (2, 1)])),
    )
    green = _scored(
        network_id="green-network",
        zone_id="zone-a",
        band="2.4GHz",
        channel=1,
        encryption=EncryptionCategory.WPA2,
        color=AttentionLevel.GREEN,
        score=1,
        signal_category="weak",
    )
    yellow_finding = replace(
        green.finding,
        network_id="yellow-network",
        zone_id="zone-b",
        representative_band="5GHz",
        representative_channel=36,
        representative_frequency_mhz=5180,
        encryption=EncryptionCategory.OUTDATED,
    )
    yellow = ScoredNetworkFinding(
        yellow_finding,
        3,
        AttentionLevel.YELLOW,
        (
            ScoreFactor("signal_strength", "-70 dBm", "medium", 1, 1),
            ScoreFactor("encryption", "OUTDATED", "outdated_or_unknown", 1, 2),
            ScoreFactor("observation_frequency", "1", "incidental", 0, 1),
        ),
    )
    return zones, (green, yellow)


def test_repository_reads_round_zones_findings_and_filter_options(clean_postgis: str) -> None:
    zones, findings = _dataset()
    storage = StorageRepository(clean_postgis)
    storage.initialize()
    storage.replace_measurement_round("round-a", zones, findings)
    storage.close()

    repository = PresentationRepository(clean_postgis)
    try:
        assert [item.measurement_round_id for item in repository.list_measurement_rounds()] == [
            "round-a"
        ]
        dashboard = repository.load_dashboard("round-a")
    finally:
        repository.close()

    assert dashboard.total_count == 2
    assert dashboard.elevated_count == 1
    assert dashboard.high_count == 0
    assert [zone.zone_id for zone in dashboard.zones] == ["zone-a", "zone-b"]
    assert dashboard.filter_options.zone_ids == ("zone-a", "zone-b")
    assert dashboard.filter_options.bands == ("2.4GHz", "5GHz")
    assert dashboard.filter_options.channels == (1, 36)
    assert dashboard.filter_options.score_colors == ("GREEN", "YELLOW")


def test_combined_filters_return_only_matching_finding_and_zone(clean_postgis: str) -> None:
    zones, findings = _dataset()
    storage = StorageRepository(clean_postgis)
    storage.initialize()
    storage.replace_measurement_round("round-a", zones, findings)
    storage.close()

    repository = PresentationRepository(clean_postgis)
    try:
        dashboard = repository.load_dashboard(
            "round-a",
            DashboardFilters(
                zone_ids=frozenset({"zone-b"}),
                bands=frozenset({"5GHz"}),
                channels=frozenset({36}),
                encryptions=frozenset({"OUTDATED"}),
                score_colors=frozenset({"YELLOW"}),
                signal_categories=frozenset({"medium"}),
            ),
        )
    finally:
        repository.close()

    assert [zone.zone_id for zone in dashboard.zones] == ["zone-b"]
    assert [finding.network_id for finding in dashboard.findings] == ["yellow-network"]


def test_empty_completed_round_still_returns_zone(clean_postgis: str) -> None:
    zone = ApprovedZone("zone-a", Polygon([(0, 0), (1, 0), (1, 1), (0, 1)]))
    storage = StorageRepository(clean_postgis)
    storage.initialize()
    storage.replace_measurement_round("round-a", [zone], [])
    storage.close()

    repository = PresentationRepository(clean_postgis)
    try:
        dashboard = repository.load_dashboard("round-a")
    finally:
        repository.close()

    assert dashboard.total_count == 0
    assert [item.zone_id for item in dashboard.zones] == ["zone-a"]
