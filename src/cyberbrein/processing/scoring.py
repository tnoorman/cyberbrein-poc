from cyberbrein.processing.models import (
    EncryptionCategory,
    NetworkFinding,
    ScoredNetworkFinding,
    ScoreFactor,
    attention_level_for_score,
)

_ENCRYPTION_CONTRIBUTION = {
    EncryptionCategory.WPA3: 0,
    EncryptionCategory.WPA2: 0,
    EncryptionCategory.ENTERPRISE: 0,
    EncryptionCategory.OUTDATED: 1,
    EncryptionCategory.UNKNOWN: 1,
    EncryptionCategory.OPEN: 2,
}


def score_network_finding(finding: NetworkFinding) -> ScoredNetworkFinding:
    """Calculate the report-defined weighted exposure score from three factors."""
    factors = (
        ScoreFactor(
            name="signal_strength",
            contribution=_signal_contribution(finding.representative_rssi_dbm),
            weight=1,
        ),
        ScoreFactor(
            name="encryption",
            contribution=_ENCRYPTION_CONTRIBUTION[finding.encryption],
            weight=2,
        ),
        ScoreFactor(
            name="observation_frequency",
            contribution=_frequency_contribution(finding.observation_count),
            weight=1,
        ),
    )
    score = sum(factor.weighted_points for factor in factors)
    return ScoredNetworkFinding(
        finding=finding,
        score=score,
        attention_level=attention_level_for_score(score),
        score_factors=factors,
    )


def _signal_contribution(rssi_dbm: int) -> int:
    if rssi_dbm < -80:
        return 0
    if rssi_dbm <= -67:
        return 1
    return 2


def _frequency_contribution(count: int) -> int:
    if count < 1:
        raise ValueError("observation_count must be positive")
    if count >= 10:
        return 2
    if count >= 2:
        return 1
    return 0
