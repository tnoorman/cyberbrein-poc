from cyberbrein.processing.models import EncryptionCategory


def normalize_encryption(value: str) -> EncryptionCategory:
    """Map parser and vendor spellings to a small deterministic category set."""
    normalized = value.strip().upper() if isinstance(value, str) else ""
    if "WPA3" in normalized:
        return EncryptionCategory.WPA3
    if "WPA2" in normalized or "RSN" in normalized:
        return EncryptionCategory.WPA2
    if "WPA" in normalized:
        return EncryptionCategory.WPA
    if "WEP" in normalized:
        return EncryptionCategory.WEP
    if normalized in {"OPEN", "OPN"}:
        return EncryptionCategory.OPEN
    return EncryptionCategory.UNKNOWN

