"""AES-256-GCM encryption for the credential vault.

The key comes from the VAULT_KEY environment variable (base64 of 32 bytes) and is
never stored in the database. Each secret gets its own random 12-byte nonce.
"""

import base64
import os

from cryptography.hazmat.primitives.ciphers.aead import AESGCM


class VaultError(Exception):
    pass


def _load_key(key_b64: str) -> bytes:
    if not key_b64:
        raise VaultError("VAULT_KEY is not configured")
    try:
        key = base64.b64decode(key_b64)
    except Exception as exc:  # noqa: BLE001
        raise VaultError("VAULT_KEY is not valid base64") from exc
    if len(key) != 32:
        raise VaultError("VAULT_KEY must decode to exactly 32 bytes")
    return key


def encrypt_secret(plaintext: str, key_b64: str, associated_data: bytes | None = None) -> tuple[bytes, bytes]:
    """Return (ciphertext, nonce)."""
    aes = AESGCM(_load_key(key_b64))
    nonce = os.urandom(12)
    return aes.encrypt(nonce, plaintext.encode("utf-8"), associated_data), nonce


def decrypt_secret(ciphertext: bytes, nonce: bytes, key_b64: str, associated_data: bytes | None = None) -> str:
    aes = AESGCM(_load_key(key_b64))
    try:
        return aes.decrypt(nonce, ciphertext, associated_data).decode("utf-8")
    except Exception as exc:  # noqa: BLE001
        raise VaultError("Secret could not be decrypted") from exc


def generate_key() -> str:
    return base64.b64encode(os.urandom(32)).decode()
