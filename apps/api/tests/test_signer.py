from crypto.signer import SIGNATURE_PREFIX, LedgerSigner, verify_signature


def test_sign_produces_prefixed_signature():
    signer = LedgerSigner.get()
    sig = signer.sign("sha256:" + "a" * 64)
    assert sig.startswith(SIGNATURE_PREFIX)


def test_sign_verify_roundtrip():
    signer = LedgerSigner.get()
    entry_hash = "sha256:" + "a" * 64
    sig = signer.sign(entry_hash)
    assert signer.verify(entry_hash, sig) is True
    assert verify_signature(signer.public_key_pem, entry_hash, sig) is True


def test_verify_rejects_tampered_hash():
    signer = LedgerSigner.get()
    sig = signer.sign("sha256:" + "a" * 64)
    assert signer.verify("sha256:" + "b" * 64, sig) is False


def test_verify_rejects_foreign_signature():
    signer = LedgerSigner.get()
    entry_hash = "sha256:" + "a" * 64
    other = LedgerSigner()  # fresh ephemeral key
    assert signer.verify(entry_hash, other.sign(entry_hash)) is False


def test_verify_rejects_malformed_signature():
    signer = LedgerSigner.get()
    assert signer.verify("sha256:" + "a" * 64, "not-a-signature") is False


def test_singleton_returns_same_instance():
    assert LedgerSigner.get() is LedgerSigner.get()
