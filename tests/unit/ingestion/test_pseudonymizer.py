import pytest

from cyberbrein.ingestion.pseudonymizer import pseudonymize_bssid

SYNTHETIC_BSSID = "02:00:00:00:00:01"
TEST_SECRET = "synthetic-test-secret"


def test_pseudonymize_bssid_requires_bssid() -> None:
    with pytest.raises(ValueError, match="bssid is required"):
        pseudonymize_bssid("", TEST_SECRET)


def test_pseudonymize_bssid_requires_secret() -> None:
    with pytest.raises(ValueError, match="secret is required"):
        pseudonymize_bssid(SYNTHETIC_BSSID, "")


def test_pseudonymize_bssid_normalizes_case_and_whitespace() -> None:
    lowercase_result = pseudonymize_bssid(SYNTHETIC_BSSID, TEST_SECRET)
    uppercase_result = pseudonymize_bssid(f"  {SYNTHETIC_BSSID.upper()}  ", TEST_SECRET)

    assert uppercase_result == lowercase_result


def test_pseudonymize_bssid_matches_known_digest() -> None:
    result = pseudonymize_bssid(SYNTHETIC_BSSID, TEST_SECRET)

    assert result == "2895b7c322e2a808c054314a168498382c5289a0f705baeccf47e5f02e319b18"
    assert len(result) == 64


def test_pseudonymize_bssid_does_not_contain_original_bssid() -> None:
    result = pseudonymize_bssid(SYNTHETIC_BSSID, TEST_SECRET)

    assert SYNTHETIC_BSSID not in result


def test_pseudonymize_bssid_uses_secret() -> None:
    first_result = pseudonymize_bssid(SYNTHETIC_BSSID, "synthetic-secret-one")
    second_result = pseudonymize_bssid(SYNTHETIC_BSSID, "synthetic-secret-two")

    assert first_result != second_result
