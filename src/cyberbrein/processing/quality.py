import math

from cyberbrein.ingestion.models import AcceptedObservation
from cyberbrein.processing.models import ProcessingPolicy, ProcessingRejectionReason


def validate_processing_quality(
    observation: AcceptedObservation,
    policy: ProcessingPolicy,
) -> ProcessingRejectionReason | None:
    """Return a safe reason when an accepted observation is unsuitable for Processing."""
    frequency = observation.frequency_mhz
    if frequency is not None:
        if not isinstance(frequency, int) or isinstance(frequency, bool) or frequency <= 0:
            return ProcessingRejectionReason.INVALID_FREQUENCY
        expected_band = _band_for_frequency(frequency)
        if expected_band is None:
            return ProcessingRejectionReason.INVALID_FREQUENCY
        if observation.band != expected_band:
            return ProcessingRejectionReason.FREQUENCY_BAND_MISMATCH

    if (
        not isinstance(observation.gps_mode, int)
        or isinstance(observation.gps_mode, bool)
        or observation.gps_mode < 3
    ):
        return ProcessingRejectionReason.INVALID_GPS_MODE

    accuracy = observation.gps_accuracy_m
    if accuracy is None:
        return ProcessingRejectionReason.MISSING_GPS_ACCURACY
    if (
        isinstance(accuracy, bool)
        or not isinstance(accuracy, (int, float))
        or not math.isfinite(accuracy)
        or accuracy < 0
    ):
        return ProcessingRejectionReason.INVALID_GPS_ACCURACY
    if accuracy > policy.max_gps_accuracy_m:
        return ProcessingRejectionReason.GPS_ACCURACY_EXCEEDED
    return None


def _band_for_frequency(frequency_mhz: int) -> str | None:
    if 2400 <= frequency_mhz < 2500:
        return "2.4GHz"
    if 5000 <= frequency_mhz < 5900:
        return "5GHz"
    return None
