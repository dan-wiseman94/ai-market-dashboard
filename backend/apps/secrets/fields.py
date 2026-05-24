"""Django field that transparently encrypts JSON payloads with Fernet.

Usage:
    class MyModel(models.Model):
        token = EncryptedJSONField(null=True)

Stored on disk as raw Fernet ciphertext in a BYTEA column. Decrypted lazily on read.
"""

from __future__ import annotations

import json
from typing import Any

from cryptography.fernet import Fernet
from django.db import models

from apps.secrets.keys import derive_fernet_key, derive_fernet_key_from_settings

__all__ = ["EncryptedJSONField", "derive_fernet_key"]


def _fernet() -> Fernet:
    return Fernet(derive_fernet_key_from_settings())


class EncryptedJSONField(models.BinaryField):
    """Stores an arbitrary JSON-serializable value encrypted with Fernet."""

    description = "JSON value encrypted with Fernet"

    def from_db_value(self, value: bytes | None, expression, connection) -> Any:
        if value is None:
            return None
        plaintext = _fernet().decrypt(bytes(value))
        return json.loads(plaintext.decode("utf-8"))

    def to_python(self, value: Any) -> Any:
        # Pass-through for freshly-assigned Python values; only decrypt raw DB bytes.
        if value is None or isinstance(value, dict | list | str | int | float | bool):
            return value
        return self.from_db_value(value, None, None)

    def get_prep_value(self, value: Any) -> bytes | None:
        if value is None:
            return None
        plaintext = json.dumps(value, separators=(",", ":"), sort_keys=True).encode("utf-8")
        return _fernet().encrypt(plaintext)
