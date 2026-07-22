from collections import defaultdict
from collections.abc import Iterable

from cyberbrein.processing.models import EncryptionCategory, NetworkFinding, ZonedObservation

_ENCRYPTION_STRENGTH = {
    EncryptionCategory.UNKNOWN: 0,
    EncryptionCategory.OPEN: 1,
    EncryptionCategory.WEP: 2,
    EncryptionCategory.WPA: 3,
    EncryptionCategory.WPA2: 4,
    EncryptionCategory.WPA3: 5,
}


def aggregate_network_findings(
    observations: Iterable[ZonedObservation],
) -> tuple[NetworkFinding, ...]:
    """Aggregate observations without inventing an access-point location."""
    grouped: dict[tuple[str, str, str], list[ZonedObservation]] = defaultdict(list)
    for observation in observations:
        source = observation.observation
        grouped[(source.measurement_round_id, observation.zone_id, source.network_id)].append(
            observation
        )

    findings = [_aggregate_group(key, group) for key, group in grouped.items()]
    return tuple(
        sorted(
            findings,
            key=lambda item: (item.measurement_round_id, item.zone_id, item.network_id),
        )
    )


def _aggregate_group(
    key: tuple[str, str, str],
    group: list[ZonedObservation],
) -> NetworkFinding:
    measurement_round_id, zone_id, network_id = key
    representative = min(group, key=_representative_key).observation
    encryption = min(group, key=lambda item: _ENCRYPTION_STRENGTH[item.encryption]).encryption
    timestamps = [item.observation.observed_at_utc for item in group]
    return NetworkFinding(
        measurement_round_id=measurement_round_id,
        zone_id=zone_id,
        network_id=network_id,
        observation_count=len(group),
        first_observed_at_utc=min(timestamps),
        last_observed_at_utc=max(timestamps),
        representative_observed_at_utc=representative.observed_at_utc,
        representative_latitude=representative.latitude,
        representative_longitude=representative.longitude,
        representative_rssi_dbm=representative.rssi_dbm,
        representative_channel=representative.channel,
        representative_frequency_mhz=representative.frequency_mhz,
        representative_band=representative.band,
        encryption=encryption,
        ssid_present=any(item.observation.ssid_present for item in group),
    )


def _representative_key(item: ZonedObservation) -> tuple[object, ...]:
    observation = item.observation
    return (
        -observation.rssi_dbm,
        observation.observed_at_utc,
        observation.latitude,
        observation.longitude,
        observation.channel,
        observation.frequency_mhz if observation.frequency_mhz is not None else -1,
        observation.band,
        item.encryption.value,
    )

