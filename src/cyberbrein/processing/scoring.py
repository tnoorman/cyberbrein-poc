from cyberbrein.processing.models import (
    EncryptionCategory,
    NetworkFinding,
    ScoredNetworkFinding,
    ScoreFactor,
    attention_level_for_score,
)

_ENCRYPTION_CONTRIBUTION = {
    EncryptionCategory.WPA3: 0,
    EncryptionCategory.WPA2_OR_WPA3: 0,
    EncryptionCategory.WPA2: 0,
    EncryptionCategory.ENTERPRISE: 0,
    EncryptionCategory.OUTDATED: 1,
    EncryptionCategory.UNKNOWN: 1,
    EncryptionCategory.OPEN: 2,
}


def score_network_finding(finding: NetworkFinding) -> ScoredNetworkFinding:
    """Calculate the report-defined weighted exposure score from three factors."""
    signal_contribution = _signal_contribution(finding.strongest_rssi_dbm)
    encryption_contribution = _ENCRYPTION_CONTRIBUTION[finding.encryption]
    frequency_contribution = _frequency_contribution(finding.observation_count)
    factors = (
        ScoreFactor(
            name="signal_strength",
            observed_value=f"{finding.strongest_rssi_dbm} dBm",
            category=("weak", "medium", "strong")[signal_contribution],
            contribution=signal_contribution,
            weight=1,
        ),
        ScoreFactor(
            name="encryption",
            observed_value=finding.encryption.value,
            category=("current", "outdated_or_unknown", "open")[encryption_contribution],
            contribution=encryption_contribution,
            weight=2,
        ),
        ScoreFactor(
            name="observation_frequency",
            observed_value=str(finding.observation_count),
            category=("incidental", "multiple", "frequent")[frequency_contribution],
            contribution=frequency_contribution,
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
