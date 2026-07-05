"""SHA-256 hash chaining for the audit ledger.

Every entry's hash commits to the previous entry's hash, forming a per-firm
chain: altering any historical entry changes its hash, which breaks every
subsequent link. Hashes are computed over a canonical JSON encoding (sorted
keys, compact separators) so they are stable across processes and languages.
"""

import hashlib
import json

GENESIS_HASH = "sha256:" + "0" * 64


def compute_entry_hash(
    previous_hash: str,
    sequence_number: int,
    timestamp_unix_ns: int,
    input_payload_hash: str,
    output_payload_hash: str,
    policy_version_hash: str,
    agent_id: str,
    session_id: str,
) -> str:
    canonical = {
        "previous_hash": previous_hash,
        "sequence_number": sequence_number,
        "timestamp_unix_ns": timestamp_unix_ns,
        "input_payload_hash": input_payload_hash,
        "output_payload_hash": output_payload_hash,
        "policy_version_hash": policy_version_hash,
        "agent_id": agent_id,
        "session_id": session_id,
    }
    raw = json.dumps(canonical, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return "sha256:" + hashlib.sha256(raw).hexdigest()


def hash_payload(payload: dict | str | bytes) -> str:
    if isinstance(payload, dict):
        raw = json.dumps(payload, sort_keys=True, separators=(",", ":")).encode("utf-8")
    elif isinstance(payload, str):
        raw = payload.encode("utf-8")
    else:
        raw = payload
    return "sha256:" + hashlib.sha256(raw).hexdigest()
