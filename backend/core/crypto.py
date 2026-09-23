"""AES-256-GCM field encryption.

Ported from the legacy mapper backend (``app/core/crypto_util.py``) with two
deliberate changes:

* the key is passed in explicitly instead of being read from a module-level
  environment variable, so it can be sourced from :mod:`backend.core.config`;
* the key material may be either a hex string (as produced by
  ``secrets.token_hex(32)``) or an arbitrary passphrase, in which case a
  32-byte key is derived via SHA-256.

Ciphertext format: ``<nonce_hex>:<ciphertext_hex>`` — a fresh random 96-bit
nonce is generated for every encryption, which is the recommended nonce size
for GCM.
"""

import hashlib
import os

from cryptography.hazmat.primitives.ciphers.aead import AESGCM

_NONCE_SIZE = 12  # 96-bit nonce, per NIST SP 800-38D recommendation
_AES_KEY_SIZES = (16, 24, 32)


def _derive_key(key: str) -> bytes:
    """Resolve ``key`` into a valid AES key (16/24/32 bytes).

    Hex strings that decode to a valid AES key size are used verbatim;
    anything else is hashed with SHA-256 to produce a 32-byte key.
    """
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
    """Decrypt a value produced by :func:`encrypt_value`.

    Values that are not in ``nonce_hex:cipher_hex`` form (or that fail to
    authenticate) are returned unchanged. This keeps rows written before
    encryption was introduced readable, mirroring the legacy behaviour.
    """
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
