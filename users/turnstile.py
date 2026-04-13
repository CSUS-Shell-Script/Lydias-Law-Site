import requests
from django.conf import settings

TURNSTILE_VERIFY_URL = "https://challenges.cloudflare.com/turnstile/v0/siteverify"


def validate_turnstile(token: str, remoteip: str | None = None) -> bool:
    """
    Verify a Cloudflare Turnstile token against the siteverify API.

    Returns True if the token is valid, False otherwise.
    Never raises — a network error is treated as a failed verification.
    """
    if not token:
        return False

    payload = {
        "secret": settings.TURNSTILE_SECRET_KEY,
        "response": token,
    }
    if remoteip:
        payload["remoteip"] = remoteip

    try:
        resp = requests.post(TURNSTILE_VERIFY_URL, data=payload, timeout=5)
        resp.raise_for_status()
        return resp.json().get("success", False)
    except Exception:
        return False
