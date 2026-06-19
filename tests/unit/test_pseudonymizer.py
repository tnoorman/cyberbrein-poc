import pytest

from cyberbrein.privacy.pseudonymizer import pseudonymize_bssid


def test_pseudonymize_bssid_is_deterministic() -> None:
    bssid = "AA:BB:CC:DD:EE:FF"
    secret = "test-secret"

    first_result = pseudonymize_bssid(bssid, secret)
    second_result = pseudonymize_bssid("aa:bb:cc:dd:ee:ff", secret)

    assert first_result == second_result
    assert first_result != bssid
    assert len(first_result) == 64


def test_pseudonymize_bssid_uses_secret() -> None:
    bssid = "AA:BB:CC:DD:EE:FF"

    first_result = pseudonymize_bssid(bssid, "secret-one")
    second_result = pseudonymize_bssid(bssid, "secret-two")

    assert first_result != second_result


def test_pseudonymize_bssid_requires_secret() -> None:
    with pytest.raises(ValueError):
        pseudonymize_bssid("AA:BB:CC:DD:EE:FF", "")
