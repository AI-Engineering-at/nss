"""Tests for SAG (Secure Access Gateway) AES-256-GCM encryption."""

from __future__ import annotations

import os

import pytest

from nss.knowledge.sag_encryption import SAGEncryptor


def _generate_hex_key() -> str:
    """Generate a random 64-char hex key (256 bits)."""
    return os.urandom(32).hex()


class TestSAGEncryptor:
    """SAGEncryptor unit tests."""

    def test_passthrough_when_disabled(self):
        """Without a key, payloads pass through unchanged."""
        enc = SAGEncryptor()
        payload = {"text": "hello", "user_id": "u1"}
        assert enc.encrypt_payload(payload) == payload
        assert enc.decrypt_payload(payload) == payload
        assert enc.enabled is False

    def test_empty_key_disables_encryption(self):
        """Empty string key means passthrough."""
        enc = SAGEncryptor(hex_key="")
        assert enc.enabled is False

    def test_invalid_key_length_raises(self):
        """Key must be exactly 64 hex characters."""
        with pytest.raises(ValueError, match="64 hex characters"):
            SAGEncryptor(hex_key="abcd")

    def test_encrypt_decrypt_roundtrip(self):
        """Encrypt then decrypt returns original payload."""
        key = _generate_hex_key()
        enc = SAGEncryptor(hex_key=key)
        assert enc.enabled is True

        payload = {"text": "confidential data", "user_id": "u1", "score": 0.95}
        encrypted = enc.encrypt_payload(payload)

        # Encrypted payload has special keys
        assert "_sag_encrypted" in encrypted
        assert "_sag_nonce" in encrypted
        assert "text" not in encrypted

        # Decrypt recovers original
        decrypted = enc.decrypt_payload(encrypted)
        assert decrypted == payload

    def test_decrypt_unencrypted_payload_returns_as_is(self):
        """Decrypting a non-encrypted payload returns it unchanged."""
        key = _generate_hex_key()
        enc = SAGEncryptor(hex_key=key)
        plain = {"text": "not encrypted"}
        assert enc.decrypt_payload(plain) == plain

    def test_different_nonces_produce_different_ciphertexts(self):
        """GCM uses random nonces so same plaintext -> different ciphertext."""
        key = _generate_hex_key()
        enc = SAGEncryptor(hex_key=key)
        payload = {"text": "same content"}

        ct1 = enc.encrypt_payload(payload)
        ct2 = enc.encrypt_payload(payload)

        assert ct1["_sag_encrypted"] != ct2["_sag_encrypted"]
        # But both decrypt to the same payload
        assert enc.decrypt_payload(ct1) == payload
        assert enc.decrypt_payload(ct2) == payload

    def test_wrong_key_fails_to_decrypt(self):
        """Decryption with the wrong key raises."""
        key1 = _generate_hex_key()
        key2 = _generate_hex_key()
        enc1 = SAGEncryptor(hex_key=key1)
        enc2 = SAGEncryptor(hex_key=key2)

        encrypted = enc1.encrypt_payload({"secret": "data"})
        with pytest.raises(Exception):  # noqa: B017 — SAG decrypt raises various low-level crypto errors; broad catch is intentional
            enc2.decrypt_payload(encrypted)

    def test_empty_payload(self):
        """Encrypting an empty dict works."""
        key = _generate_hex_key()
        enc = SAGEncryptor(hex_key=key)
        encrypted = enc.encrypt_payload({})
        assert enc.decrypt_payload(encrypted) == {}
