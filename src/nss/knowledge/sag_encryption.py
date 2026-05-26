"""SAG (Secure Access Gateway) encryption for vector payloads.

Provides AES-256-GCM encryption/decryption of vector store payloads,
ensuring that sensitive document metadata is encrypted at rest.
When a ``sag_encryption_key`` is configured the Knowledge Fabric layer
transparently encrypts payloads before writing to Qdrant and decrypts
them on read.

Key format: 64 hex-character string representing 32 bytes.
"""

from __future__ import annotations

import base64
import json
import os
from typing import Any

import structlog

logger = structlog.get_logger(__name__)


class SAGEncryptor:
    """AES-256-GCM encryptor for vector payloads.

    Parameters:
        hex_key: 64-character hex string representing a 256-bit key.
            Pass an empty string to disable encryption (passthrough mode).
    """

    def __init__(self, hex_key: str = "") -> None:
        self._key: bytes | None = None
        if hex_key:
            if len(hex_key) != 64:
                raise ValueError(
                    f"SAG encryption key must be 64 hex characters (got {len(hex_key)})."
                )
            self._key = bytes.fromhex(hex_key)
            logger.info("sag_encryption_enabled")

    @property
    def enabled(self) -> bool:
        """Whether encryption is active."""
        return self._key is not None

    def encrypt_payload(self, payload: dict[str, Any]) -> dict[str, Any]:
        """Encrypt a vector payload dict.

        When disabled, returns the payload unchanged.
        When enabled, returns ``{"_sag_encrypted": "<base64>", "_sag_nonce": "<base64>"}``.
        """
        if self._key is None:
            return payload

        from cryptography.hazmat.primitives.ciphers.aead import AESGCM

        plaintext = json.dumps(payload, sort_keys=True).encode()
        nonce = os.urandom(12)  # 96-bit nonce for GCM
        aesgcm = AESGCM(self._key)
        ciphertext = aesgcm.encrypt(nonce, plaintext, None)

        return {
            "_sag_encrypted": base64.b64encode(ciphertext).decode(),
            "_sag_nonce": base64.b64encode(nonce).decode(),
        }

    def decrypt_payload(self, payload: dict[str, Any]) -> dict[str, Any]:
        """Decrypt a SAG-encrypted payload.

        If the payload does not contain ``_sag_encrypted`` it is
        returned as-is (backwards compatibility with unencrypted data).
        """
        if self._key is None:
            return payload

        if "_sag_encrypted" not in payload:
            return payload

        from cryptography.hazmat.primitives.ciphers.aead import AESGCM

        ciphertext = base64.b64decode(payload["_sag_encrypted"])
        nonce = base64.b64decode(payload["_sag_nonce"])
        aesgcm = AESGCM(self._key)
        plaintext = aesgcm.decrypt(nonce, ciphertext, None)

        decoded: dict[str, Any] = json.loads(plaintext.decode())
        return decoded
