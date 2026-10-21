"""
Encryption at rest for stored files (Task 5.1, FR-N2): AES-256-GCM.

A stored file is `b"HV1" + 12-byte random nonce + ciphertext + 16-byte tag`. GCM also detects any change to the
stored bytes, so a damaged or tampered file is refused instead of being shown as something else.

The key comes from RECORDS_ENCRYPTION_KEY. If it is empty (development), it is derived from JWT_SECRET_KEY.
Changing the key makes older files unreadable, so set it once and keep it.
"""

import hashlib
import os

from cryptography.exceptions import InvalidTag
from cryptography.hazmat.primitives.ciphers.aead import AESGCM

from app.core.config import get_settings

MAGIC = b"HV1"


class DecryptError(Exception):
    pass


def _key() -> bytes:
    s = get_settings()
    secret = s.RECORDS_ENCRYPTION_KEY or ("derived:" + s.JWT_SECRET_KEY)
    return hashlib.sha256(b"humsafar-records-v1:" + secret.encode()).digest()


def encrypt(data: bytes) -> bytes:
    nonce = os.urandom(12)
    return MAGIC + nonce + AESGCM(_key()).encrypt(nonce, data, MAGIC)


def decrypt(blob: bytes) -> bytes:
    if len(blob) < len(MAGIC) + 12 + 16 or blob[:3] != MAGIC:
        raise DecryptError("not an encrypted record file")
    try:
        return AESGCM(_key()).decrypt(blob[3:15], blob[15:], MAGIC)
    except InvalidTag as exc:
        raise DecryptError("record file is damaged or the key changed") from exc
