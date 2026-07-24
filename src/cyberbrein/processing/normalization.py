from cyberbrein.processing.models import EncryptionCategory


def normalize_encryption(value: str) -> EncryptionCategory:
    """Map parser and vendor spellings to a small deterministic category set."""
    normalized = value.strip().upper() if isinstance(value, str) else ""
    if "802.1X" in normalized or "ENTERPRISE" in normalized or "EAP" in normalized:
        return EncryptionCategory.ENTERPRISE
    if "WPA3" in normalized:
        return EncryptionCategory.WPA3
    if "WPA2" in normalized or "RSN" in normalized:
        return EncryptionCategory.WPA2
    if "WPA" in normalized or "WEP" in normalized:
        return EncryptionCategory.OUTDATED
    if normalized in {"OPEN", "OPN"}:
        return EncryptionCategory.OPEN
    return EncryptionCategory.UNKNOWN
