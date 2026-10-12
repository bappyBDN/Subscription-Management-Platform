import pytest

from app.core import crypto


def test_round_trip_and_unique_nonce():
    key = crypto.generate_key()
    ct1, n1 = crypto.encrypt_secret("p@ss-123", key)
    ct2, n2 = crypto.encrypt_secret("p@ss-123", key)
    assert n1 != n2 and ct1 != ct2
    assert b"p@ss-123" not in ct1
    assert crypto.decrypt_secret(ct1, n1, key) == "p@ss-123"


def test_wrong_key_fails():
    ct, n = crypto.encrypt_secret("secret", crypto.generate_key())
    with pytest.raises(crypto.VaultError):
        crypto.decrypt_secret(ct, n, crypto.generate_key())


def test_missing_or_bad_key():
    with pytest.raises(crypto.VaultError):
        crypto.encrypt_secret("x", "")
    with pytest.raises(crypto.VaultError):
        crypto.encrypt_secret("x", "c2hvcnQ=")  # "short"
