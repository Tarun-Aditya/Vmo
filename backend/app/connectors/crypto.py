"""Secrets (client secrets, private keys, refresh tokens) are stored encrypted. The key is SECRET_KEY (a Fernet key) or, if unset, a key file
created next to the data (data/.secret_key). Losing the key means re-entering the secrets."""
from __future__ import annotations

import json
import os

from cryptography.fernet import Fernet

from app.config import data_path


def _key() -> bytes:
    k = os.environ.get("SECRET_KEY")
    if k:
        return k.encode()
    f = data_path() / ".secret_key"
    if not f.exists():
        f.parent.mkdir(parents=True, exist_ok=True)
        f.write_bytes(Fernet.generate_key())
        f.chmod(0o600)
    return f.read_bytes()


def encrypt(d: dict) -> str:
    return Fernet(_key()).encrypt(json.dumps(d).encode()).decode()


def decrypt(s: str | None) -> dict:
    return json.loads(Fernet(_key()).decrypt(s.encode()).decode()) if s else {}


def mask(d: dict) -> dict:
    return {k: ("••••••••" if v else "") for k, v in d.items()}
