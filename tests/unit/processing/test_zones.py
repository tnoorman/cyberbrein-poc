from dataclasses import replace
from datetime import datetime, timezone

import pytest
from shapely.geometry import LineString, Polygon

from cyberbrein.ingestion.models import AcceptedObservation
from cyberbrein.processing.models import ApprovedZone, ProcessingRejectionReason
from cyberbrein.processing.zones import match_approved_zone


def _observation(longitude: float, latitude: float) -> AcceptedObservation:
    return AcceptedObservation(
        measurement_round_id="synthetic-round",
        observed_at_utc=datetime(2026, 1, 1, tzinfo=timezone.utc),
        network_id="synthetic-network",
        ssid_present=False,
        rssi_dbm=-50,
        channel=1,
        frequency_mhz=2412,
        band="2.4GHz",
        encryption="WPA2",
        latitude=latitude,
        longitude=longitude,
        gps_mode=3,
        gps_accuracy_m=2.0,
    )


def _zone(zone_id: str = "zone-a", offset: float = 0.0) -> ApprovedZone:
    return ApprovedZone(
        zone_id,
        Polygon(
            [
                (offset, offset),
                (offset + 1, offset),
                (offset + 1, offset + 1),
                (offset, offset + 1),
            ]
        ),
    )


def test_point_inside_zone_is_matched() -> None:
    assert match_approved_zone(_observation(0.5, 0.5), [_zone()]).zone_id == "zone-a"


def test_point_on_outer_boundary_is_matched() -> None:
    assert match_approved_zone(_observation(0.0, 0.5), [_zone()]).zone_id == "zone-a"


def test_point_outside_zones_is_rejected() -> None:
    match = match_approved_zone(_observation(2.0, 2.0), [_zone()])
    assert match.rejection_reason is ProcessingRejectionReason.OUTSIDE_APPROVED_ZONE


def test_overlapping_zones_are_ambiguous() -> None:
    match = match_approved_zone(_observation(0.75, 0.75), [_zone(), _zone("zone-b", 0.5)])
    assert match.rejection_reason is ProcessingRejectionReason.AMBIGUOUS_ZONE


def test_touching_zone_boundaries_are_ambiguous() -> None:
    adjacent = ApprovedZone("zone-b", Polygon([(1, 0), (2, 0), (2, 1), (1, 1)]))
    match = match_approved_zone(_observation(1.0, 0.5), [_zone(), adjacent])
    assert match.rejection_reason is ProcessingRejectionReason.AMBIGUOUS_ZONE


@pytest.mark.parametrize(
    ("zone_id", "geometry"),
    [
        ("", Polygon([(0, 0), (1, 0), (1, 1), (0, 1)])),
        ("zone-a", Polygon()),
        ("zone-a", LineString([(0, 0), (1, 1)])),
    ],
)
def test_invalid_zone_is_rejected(zone_id: str, geometry: object) -> None:
    with pytest.raises(ValueError):
        ApprovedZone(zone_id, geometry)  # type: ignore[arg-type]


def test_observation_helper_can_be_changed_without_mutation() -> None:
    original = _observation(0.5, 0.5)
    changed = replace(original, longitude=0.75)
    assert original.longitude == 0.5
    assert changed.longitude == 0.75
