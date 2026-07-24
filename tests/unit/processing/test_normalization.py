import pytest

from cyberbrein.processing.models import EncryptionCategory
from cyberbrein.processing.normalization import normalize_encryption


@pytest.mark.parametrize(
    ("raw_value", "expected"),
    [
        ("OPN", EncryptionCategory.OPEN),
        ("open", EncryptionCategory.OPEN),
        ("WEP_OR_UNKNOWN", EncryptionCategory.OUTDATED),
        ("WPA/PSK", EncryptionCategory.OUTDATED),
        ("WPA2/802.1X", EncryptionCategory.ENTERPRISE),
        ("WPA-EAP", EncryptionCategory.ENTERPRISE),
        ("WPA2,WPA3", EncryptionCategory.WPA3),
        ("RSN_WPA2_OR_WPA3", EncryptionCategory.WPA3),
        ("RSN", EncryptionCategory.WPA2),
        ("", EncryptionCategory.UNKNOWN),
        ("vendor-specific", EncryptionCategory.UNKNOWN),
    ],
)
def test_normalize_encryption(raw_value: str, expected: EncryptionCategory) -> None:
    assert normalize_encryption(raw_value) is expected
