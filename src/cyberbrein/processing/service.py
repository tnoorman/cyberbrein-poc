from collections import Counter
from collections.abc import Iterable, Sequence

from cyberbrein.ingestion.models import AcceptedObservation
from cyberbrein.processing.aggregation import aggregate_network_findings
from cyberbrein.processing.models import (
    ApprovedZone,
    ProcessingPolicy,
    ProcessingResult,
    ZonedObservation,
)
from cyberbrein.processing.normalization import normalize_encryption
from cyberbrein.processing.quality import validate_processing_quality
from cyberbrein.processing.scoring import score_network_finding
from cyberbrein.processing.zones import match_approved_zone


class ProcessingService:
    def __init__(self, zones: Sequence[ApprovedZone], policy: ProcessingPolicy) -> None:
        zone_ids = [zone.zone_id for zone in zones]
        if len(zone_ids) != len(set(zone_ids)):
            raise ValueError("zone IDs must be unique")
        self._zones = tuple(zones)
        self._policy = policy

    def process(self, observations: Iterable[AcceptedObservation]) -> ProcessingResult:
        rejection_reasons: Counter[str] = Counter()
        zoned_observations: list[ZonedObservation] = []
        input_count = 0

        for observation in observations:
            input_count += 1
            quality_rejection = validate_processing_quality(observation, self._policy)
            if quality_rejection is not None:
                rejection_reasons[quality_rejection.value] += 1
                continue

            zone_match = match_approved_zone(observation, self._zones)
            if zone_match.rejection_reason is not None:
                rejection_reasons[zone_match.rejection_reason.value] += 1
                continue

            assert zone_match.zone_id is not None
            zoned_observations.append(
                ZonedObservation(
                    observation=observation,
                    zone_id=zone_match.zone_id,
                    encryption=normalize_encryption(observation.encryption),
                )
            )

        findings = tuple(
            score_network_finding(finding)
            for finding in aggregate_network_findings(zoned_observations)
        )
        rejected_count = sum(rejection_reasons.values())
        return ProcessingResult(
            findings=findings,
            input_observation_count=input_count,
            accepted_observation_count=len(zoned_observations),
            rejected_observation_count=rejected_count,
            rejection_reasons=dict(sorted(rejection_reasons.items())),
        )
