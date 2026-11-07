"""TOTP (RFC 6238, SHA-1, 6 digits, 30 s) and one-time recovery codes, with the standard library only."""
from __future__ import annotations

import base64
import hashlib
import hmac
import secrets
import struct
import time


def new_secret() -> str:
    return base64.b32encode(secrets.token_bytes(20)).decode().rstrip("=")


def code(secret: str, at: float | None = None, step: int = 30, digits: int = 6) -> str:
    key = base64.b32decode(secret + "=" * (-len(secret) % 8), casefold=True)
    h = hmac.new(key, struct.pack(">Q", int((at if at is not None else time.time()) // step)), hashlib.sha1).digest()
    o = h[-1] & 15
    return str((struct.unpack(">I", h[o:o + 4])[0] & 0x7FFFFFFF) % 10**digits).zfill(digits)


def verify(secret: str, given: str, window: int = 1) -> bool:
    given = (given or "").strip().replace(" ", "")
    now = time.time()
    return any(hmac.compare_digest(code(secret, now + d * 30), given) for d in range(-window, window + 1))


def uri(secret: str, email: str, issuer: str = "ContractIQ") -> str:
    from urllib.parse import quote

    return f"otpauth://totp/{quote(issuer)}:{quote(email)}?secret={secret}&issuer={quote(issuer)}&digits=6&period=30"


def new_recovery_codes(n: int = 8) -> list[str]:
    return [f"{secrets.token_hex(2)}-{secrets.token_hex(2)}-{secrets.token_hex(2)}" for _ in range(n)]


def hash_code(c: str) -> str:
    return hashlib.sha256(c.strip().lower().encode()).hexdigest()
