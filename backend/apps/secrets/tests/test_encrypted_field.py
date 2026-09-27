from apps.secrets.fields import EncryptedJSONField, derive_fernet_key


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
