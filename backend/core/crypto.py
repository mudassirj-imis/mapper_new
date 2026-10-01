import hashlib
import os

from cryptography.hazmat.primitives.ciphers.aead import AESGCM

_NONCE_SIZE = 12
_AES_KEY_SIZES = (16, 24, 32)


def _derive_key(key: str) -> bytes:

    if not key:
        raise ValueError("Encryption key must not be empty")

    if len(key) % 2 == 0:
        try:
            raw = bytes.fromhex(key)
        except ValueError:
            raw = b""
        if len(raw) in _AES_KEY_SIZES:
            return raw

    return hashlib.sha256(key.encode("utf-8")).digest()


def encrypt_value(value: str, key: str) -> str:
    """Encrypt ``value`` with AES-256-GCM and return ``nonce_hex:cipher_hex``."""
    aesgcm = AESGCM(_derive_key(key))
    nonce = os.urandom(_NONCE_SIZE)
    ciphertext = aesgcm.encrypt(nonce, value.encode("utf-8"), None)
    return f"{nonce.hex()}:{ciphertext.hex()}"


def decrypt_value(encrypted: str, key: str) -> str:
    """Decrypt a value produced by :func:`encrypt_value`."""
    try:
        if ":" not in encrypted:
            return encrypted

        nonce_hex, ciphertext_hex = encrypted.split(":", 1)
        aesgcm = AESGCM(_derive_key(key))
        plaintext = aesgcm.decrypt(
            bytes.fromhex(nonce_hex), bytes.fromhex(ciphertext_hex), None
        )
        return plaintext.decode("utf-8")
    except Exception:
        return encrypted
