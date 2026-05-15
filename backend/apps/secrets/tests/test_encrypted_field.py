import pytest

from apps.secrets.fields import EncryptedJSONField, derive_fernet_key


def test_derive_fernet_key_is_deterministic_for_same_inputs():
    k1 = derive_fernet_key(b"secret-key-abc", b"salt-bytes-16xxx")
    k2 = derive_fernet_key(b"secret-key-abc", b"salt-bytes-16xxx")
    assert k1 == k2
    # Fernet keys are 44-char urlsafe-base64-encoded 32-byte strings
    assert len(k1) == 44
    assert isinstance(k1, bytes)


def test_derive_fernet_key_changes_with_salt():
    k1 = derive_fernet_key(b"same-key", b"salt-one-bytes..")
    k2 = derive_fernet_key(b"same-key", b"salt-two-bytes..")
    assert k1 != k2


def test_field_roundtrip_encrypts_json():
    field = EncryptedJSONField()
    payload = {"access_token": "abc123", "expires_at": 1234567890, "nested": [1, 2, {"k": "v"}]}
    encrypted = field.get_prep_value(payload)
    assert isinstance(encrypted, bytes)
    # Ciphertext must NOT contain the plaintext
    assert b"abc123" not in encrypted

    decrypted = field.from_db_value(encrypted, expression=None, connection=None)
    assert decrypted == payload


def test_field_handles_none():
    field = EncryptedJSONField(null=True)
    assert field.get_prep_value(None) is None
    assert field.from_db_value(None, expression=None, connection=None) is None


def test_field_rejects_tampered_ciphertext():
    from cryptography.fernet import InvalidToken

    field = EncryptedJSONField()
    encrypted = field.get_prep_value({"a": 1})
    assert encrypted is not None  # satisfy mypy
    tampered = encrypted[:-5] + b"XXXXX"
    with pytest.raises(InvalidToken):
        field.from_db_value(tampered, expression=None, connection=None)
