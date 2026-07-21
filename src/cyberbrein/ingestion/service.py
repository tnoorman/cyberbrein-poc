from collections import Counter
from pathlib import Path
from typing import cast

from cyberbrein.ingestion.models import AcceptedObservation, IngestionResult
from cyberbrein.ingestion.pseudonymizer import pseudonymize_bssid
from cyberbrein.ingestion.sqlite_reader import read_raw_observations
from cyberbrein.ingestion.validator import validate_observation


class IngestionService:
    def __init__(self, database_path: str | Path) -> None:
        self._database_path = Path(database_path)

    def ingest(self, secret: str) -> IngestionResult:
        """Validate and transform raw SQLite observations without retaining the secret."""
        if not secret:
            raise ValueError("secret is required")

        accepted: list[AcceptedObservation] = []
        rejection_reasons: Counter[str] = Counter()
        rejected_count = 0

        for observation in read_raw_observations(self._database_path):
            rejection_reason = validate_observation(observation)
            if rejection_reason is not None:
                rejected_count += 1
                rejection_reasons[rejection_reason] += 1
                continue

            accepted.append(
                AcceptedObservation(
                    measurement_round_id=observation.measurement_round_id,
                    observed_at_utc=observation.observed_at_utc,
                    network_id=pseudonymize_bssid(observation.bssid, secret),
                    ssid_present=bool(observation.ssid),
                    rssi_dbm=observation.rssi_dbm,
                    channel=observation.channel,
                    frequency_mhz=observation.frequency_mhz,
                    band=observation.band,
                    encryption=observation.encryption,
                    latitude=cast(float, observation.latitude),
                    longitude=cast(float, observation.longitude),
                    gps_mode=cast(int, observation.gps_mode),
                    gps_accuracy_m=observation.gps_accuracy_m,
                )
            )

        return IngestionResult(
            accepted=tuple(accepted),
            accepted_count=len(accepted),
            rejected_count=rejected_count,
            rejection_reasons=dict(sorted(rejection_reasons.items())),
        )
