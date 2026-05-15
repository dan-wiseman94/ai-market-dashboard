"""Encryption key derivation.

Key = HKDF(DJANGO_SECRET_KEY, salt=file(/data/secret.salt)). The salt is a 32-byte
random file, generated on first call if missing. Losing the salt destroys all
stored credentials — back it up alongside /data if you care.
"""

from __future__ import annotations

import base64
import os
import secrets as py_secrets
from pathlib import Path

from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.kdf.hkdf import HKDF
from django.conf import settings


def _load_or_create_salt(path: Path) -> bytes:
    if path.exists():
        return path.read_bytes()
    path.parent.mkdir(parents=True, exist_ok=True)
    salt = py_secrets.token_bytes(32)
    path.write_bytes(salt)
    os.chmod(path, 0o600)
    return salt


def derive_fernet_key_from_settings() -> bytes:
    salt_path = Path(getattr(settings, "_ENCRYPTION_SALT_PATH", "/data/secret.salt"))
    salt = _load_or_create_salt(salt_path)
    return derive_fernet_key(settings.SECRET_KEY.encode("utf-8"), salt)


def derive_fernet_key(secret: bytes, salt: bytes) -> bytes:
    """HKDF-SHA256 → 32 bytes → urlsafe-base64 (Fernet expects this form)."""
    raw = HKDF(
        algorithm=hashes.SHA256(),
        length=32,
        salt=salt,
        info=b"ai-dashboard-fernet-v1",
    ).derive(secret)
    return base64.urlsafe_b64encode(raw)
