"""Ed25519 platform signing for ledger entries.

The platform private key signs every entry hash, proving the entry was recorded
by TrailMark (chain of custody). In production the key lives ONLY in AWS
Secrets Manager (secret id: trailmark/signing-key) — never in code, environment
variables, or the database. Local dev generates an ephemeral per-process key.
"""

import base64
import os

from cryptography.exceptions import InvalidSignature
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import (
    Ed25519PrivateKey,
    Ed25519PublicKey,
)

SIGNATURE_PREFIX = "ed25519:"
SIGNING_KEY_SECRET_ID = "trailmark/signing-key"


class LedgerSigner:
    _instance: "LedgerSigner | None" = None

    def __init__(self) -> None:
        pem = self._load_private_key()
        private_key = serialization.load_pem_private_key(pem, password=None)
        if not isinstance(private_key, Ed25519PrivateKey):
            raise TypeError("trailmark/signing-key must be an Ed25519 private key")
        self.private_key: Ed25519PrivateKey = private_key
        pub = self.private_key.public_key()
        self.public_key_pem = pub.public_bytes(
            serialization.Encoding.PEM,
            serialization.PublicFormat.SubjectPublicKeyInfo,
        ).decode()

    def _load_private_key(self) -> bytes:
        if os.getenv("ENV") == "production":
            import boto3

            client = boto3.client("secretsmanager")
            secret = client.get_secret_value(SecretId=SIGNING_KEY_SECRET_ID)
            return secret["SecretString"].encode()
        # Local dev: ephemeral per-process key. Never persisted anywhere.
        key = Ed25519PrivateKey.generate()
        return key.private_bytes(
            serialization.Encoding.PEM,
            serialization.PrivateFormat.PKCS8,
            serialization.NoEncryption(),
        )

    def sign(self, entry_hash: str) -> str:
        sig = self.private_key.sign(entry_hash.encode("utf-8"))
        return SIGNATURE_PREFIX + base64.b64encode(sig).decode()

    def verify(self, entry_hash: str, signature: str) -> bool:
        """Verify a platform signature against this signer's public key."""
        return verify_signature(self.public_key_pem, entry_hash, signature)

    @classmethod
    def get(cls) -> "LedgerSigner":
        if cls._instance is None:
            cls._instance = cls()
        return cls._instance


def verify_signature(public_key_pem: str, entry_hash: str, signature: str) -> bool:
    """Verify an entry-hash signature against a given public key.

    Standalone so examiners/auditors can verify exported evidence with nothing
    but the published platform public key.
    """
    if not signature.startswith(SIGNATURE_PREFIX):
        return False
    public_key = serialization.load_pem_public_key(public_key_pem.encode())
    if not isinstance(public_key, Ed25519PublicKey):
        return False
    raw_sig = base64.b64decode(signature[len(SIGNATURE_PREFIX):])
    try:
        public_key.verify(raw_sig, entry_hash.encode("utf-8"))
        return True
    except InvalidSignature:
        return False
