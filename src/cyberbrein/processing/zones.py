from collections.abc import Sequence

from shapely.geometry import Point

from cyberbrein.ingestion.models import AcceptedObservation
from cyberbrein.processing.models import (
    ApprovedZone,
    ProcessingRejectionReason,
    ZoneMatch,
)


def match_approved_zone(
    observation: AcceptedObservation,
    zones: Sequence[ApprovedZone],
) -> ZoneMatch:
    """Match a measurement point to exactly one zone, including its outer boundary."""
    point = Point(observation.longitude, observation.latitude)
    matches = [zone.zone_id for zone in zones if zone.geometry.covers(point)]
    if not matches:
        return ZoneMatch(rejection_reason=ProcessingRejectionReason.OUTSIDE_APPROVED_ZONE)
    if len(matches) > 1:
        return ZoneMatch(rejection_reason=ProcessingRejectionReason.AMBIGUOUS_ZONE)
    return ZoneMatch(zone_id=matches[0])

