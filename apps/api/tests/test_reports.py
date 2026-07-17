"""SEC 17a-4 report generator tests."""

import io
import re

from pypdf import PdfReader

from crypto.signer import LedgerSigner
from tests.test_api import AUTH_A, AUTH_B, FIRM_A, client, ingest_one  # noqa: F401
from tests.test_attestations import HIGH_RISK, attest

PERIOD = {"period_from": "2020-01-01T00:00:00Z", "period_to": "2099-01-01T00:00:00Z"}


def pdf_text(content: bytes) -> str:
    reader = PdfReader(io.BytesIO(content))
    return "\n".join(page.extract_text() for page in reader.pages)


def compact(text: str) -> str:
    """pypdf inserts line breaks inside wrapped strings (hashes, ledger ids);
    strip all whitespace for containment checks on long tokens."""
    return re.sub(r"\s+", "", text)


async def generate(client, body=None, headers=AUTH_A):
    return await client.post("/v1/reports/sec-17a4", json=body or dict(PERIOD), headers=headers)


async def test_report_contains_required_sections(client):
    for i in range(7):
        await ingest_one(client, i=i)
    entry = await ingest_one(client, i=99, **HIGH_RISK)
    await attest(client, entry["ledger_id"])

    resp = await generate(client, {**PERIOD, "firm_name": "Acme Capital LLC", "firm_crd": "123456"})
    assert resp.status_code == 200, resp.text
    assert resp.headers["content-type"] == "application/pdf"
    assert resp.content.startswith(b"%PDF")

    text = pdf_text(resp.content)
    # Header block
    assert "SEC RULE 17a-4" in text
    assert "Acme Capital LLC" in text
    assert "123456" in text
    # I. counts — 8 total, 1 high-risk attested
    assert "8" in text and "1 attested" in text
    # II. WORM proof
    assert "arn:aws:s3:::" in text
    assert "COMPLIANCE" in text
    # III. chain verification (real result)
    assert "VERIFIED" in text
    assert "8 entry hashes were recomputed" in text
    # IV. samples include ledger ids
    assert entry["ledger_id"] in compact(text)
    # V. attestation block. Long crypto values wrap character-by-character, so
    # (as with hashes/ledger ids above) check the labels in the raw text and
    # the values in the whitespace-stripped text.
    compacted = compact(text)
    assert "Report hash" in text and "sha256:" in compacted
    assert "Platform signature" in text and "ed25519:" in compacted
    assert "BEGIN PUBLIC KEY" in text


async def test_report_signature_verifies_via_headers(client):
    await ingest_one(client)
    resp = await generate(client)
    report_hash = resp.headers["x-trailmark-report-hash"]
    signature = resp.headers["x-trailmark-report-signature"]
    assert LedgerSigner.get().verify(report_hash, signature) is True
    # and the same hash/signature pair is embedded in the document
    assert report_hash in compact(pdf_text(resp.content))


async def test_report_is_firm_scoped(client):
    await ingest_one(client, firm_id=FIRM_A, i=1)
    resp = await generate(client, headers=AUTH_B)  # firm B: no entries
    text = pdf_text(resp.content)
    assert "0" in text
    assert "No entries were recorded during the period" in text


async def test_report_period_filters_entries(client):
    await ingest_one(client)
    resp = await generate(client, {
        "period_from": "2001-01-01T00:00:00Z",
        "period_to": "2002-01-01T00:00:00Z",
    })
    assert "No entries were recorded during the period" in pdf_text(resp.content)


async def test_invalid_period_rejected(client):
    resp = await generate(client, {
        "period_from": "2099-01-01T00:00:00Z",
        "period_to": "2020-01-01T00:00:00Z",
    })
    assert resp.status_code == 422
    assert resp.json()["error"]["code"] == "invalid_period"


async def test_broken_chain_is_reported_not_hidden(client, pool):
    entries = [await ingest_one(client, i=i) for i in range(3)]
    async with pool.acquire() as conn:
        await conn.execute("ALTER TABLE audit_entries DISABLE TRIGGER audit_entries_immutable_row")
        await conn.execute(
            "UPDATE audit_entries SET session_id = 'tampered' WHERE ledger_id = $1",
            entries[1]["ledger_id"],
        )
        await conn.execute("ALTER TABLE audit_entries ENABLE TRIGGER audit_entries_immutable_row")

    text = pdf_text((await generate(client)).content)
    assert "FAILED" in text
    assert "sequence2of3" in compact(text)
    assert "immediate escalation" in " ".join(text.split())


async def test_report_requires_auth(client):
    resp = await client.post("/v1/reports/sec-17a4", json=dict(PERIOD))
    assert resp.status_code == 401
