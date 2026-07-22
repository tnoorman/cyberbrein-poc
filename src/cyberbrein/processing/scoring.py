from cyberbrein.processing.models import (
    EncryptionCategory,
    NetworkFinding,
    ScoredNetworkFinding,
    ScoreFactor,
)

_ENCRYPTION_POINTS = {
    EncryptionCategory.WPA3: 0,
    EncryptionCategory.WPA2: 10,
    EncryptionCategory.WPA: 30,
    EncryptionCategory.WEP: 45,
    EncryptionCategory.OPEN: 50,
    EncryptionCategory.UNKNOWN: 40,
}


def score_network_finding(finding: NetworkFinding) -> ScoredNetworkFinding:
    """Calculate a bounded PoC exposure score with independently visible factors."""
    factors = (
        ScoreFactor("encryption", _ENCRYPTION_POINTS[finding.encryption]),
        ScoreFactor("signal_strength", _signal_points(finding.representative_rssi_dbm)),
        ScoreFactor("ssid_present", 10 if finding.ssid_present else 0),
        ScoreFactor("observation_count", _observation_count_points(finding.observation_count)),
    )
    return ScoredNetworkFinding(
        finding=finding,
        score=sum(factor.points for factor in factors),
        score_factors=factors,
    )


def _signal_points(rssi_dbm: int) -> int:
    if rssi_dbm >= -50:
        return 30
    if rssi_dbm >= -70:
        return 20
    return 10


def _observation_count_points(count: int) -> int:
    if count >= 10:
        return 10
    if count >= 2:
        return 5
    return 0

