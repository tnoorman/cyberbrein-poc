import hmac
from hashlib import sha256


def pseudonymize_bssid(bssid: str, secret: str) -> str:
    if not bssid:
        raise ValueError("bssid is required")

    if not secret:
        raise ValueError("secret is required")

    normalized_bssid = bssid.strip().lower()

    return hmac.new(
        secret.encode("utf-8"),
        normalized_bssid.encode("utf-8"),
        sha256,
    ).hexdigest()
