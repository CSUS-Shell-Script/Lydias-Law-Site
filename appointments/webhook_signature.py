"""
Calendly webhook HMAC verification.

Calendly sends header ``Calendly-Webhook-Signature`` shaped like::

    t=<unix_timestamp>,v1=<signature>

The signed string is ``f\"{t}.{request_body_as_utf8}\"`` (literal dot between
timestamp and body). ``v1`` is the HMAC-SHA256 digest of that string using your
webhook signing key, typically shown as URL-safe Base64 (padding optional); a
64-character hex encoding is also accepted.

See: https://developer.calendly.com/api-docs/4c305798a61d3-webhook-signatures
"""

from __future__ import annotations

import base64
import hashlib
import hmac
import time
from typing import Optional


def _digest_for_timestamp_body(signing_key: str, ts: int, body_text: str) -> bytes:
    signed_message = f"{ts}.{body_text}".encode("utf-8")
    return hmac.new(signing_key.encode("utf-8"), signed_message, hashlib.sha256).digest()


def _decode_v1_signature_blob(v1: str) -> Optional[bytes]:
    v1 = v1.strip()
    if len(v1) == 64 and all(c in "0123456789abcdefABCDEF" for c in v1):
        try:
            return bytes.fromhex(v1)
        except ValueError:
            return None
    for decoder in (base64.urlsafe_b64decode, base64.standard_b64decode):
        try:
            pad = "=" * ((4 - len(v1) % 4) % 4)
            raw = decoder((v1 + pad).encode("ascii"))
        except Exception:
            continue
        if len(raw) == hashlib.sha256().digest_size:
            return raw
    return None


def verify_calendly_webhook_signature(
    raw_body: bytes,
    signature_header: Optional[str],
    signing_key: str,
    *,
    tolerance_seconds: int = 300,
    now: Optional[float] = None,
) -> bool:
    if not signing_key:
        return False

    if not signature_header or not signature_header.strip():
        return False

    parts: dict[str, str] = {}
    for segment in signature_header.split(","):
        segment = segment.strip()
        if "=" not in segment:
            continue
        k, _, v = segment.partition("=")
        parts[k.strip()] = v.strip()

    t_raw = parts.get("t")
    v1 = parts.get("v1")
    if not t_raw or not v1:
        return False
    try:
        ts = int(t_raw)
    except ValueError:
        return False

    clock = time.time() if now is None else float(now)
    if abs(clock - ts) > tolerance_seconds:
        return False

    try:
        body_text = raw_body.decode("utf-8")
    except UnicodeDecodeError:
        return False

    expected_digest = _digest_for_timestamp_body(signing_key, ts, body_text)
    received = _decode_v1_signature_blob(v1)
    if received is None:
        return False
    return hmac.compare_digest(expected_digest, received)


def build_calendly_webhook_signature_header(
    raw_body: bytes,
    signing_key: str,
    *,
    timestamp: Optional[int] = None,
) -> str:
    """
    Build a ``Calendly-Webhook-Signature`` header value (for tests or tooling).

    Uses ``{t}.{utf8_body}`` as the HMAC message, with ``v1`` as URL-safe Base64
    of the digest (padding stripped), matching typical Calendly deliveries.
    """
    ts = int(time.time()) if timestamp is None else int(timestamp)
    digest = _digest_for_timestamp_body(signing_key, ts, raw_body.decode("utf-8"))
    v1 = base64.urlsafe_b64encode(digest).decode("ascii").rstrip("=")
    return f"t={ts},v1={v1}"
