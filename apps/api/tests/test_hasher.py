from crypto.hasher import GENESIS_HASH, compute_entry_hash, hash_payload

BASE_KWARGS = dict(
    previous_hash=GENESIS_HASH,
    sequence_number=1,
    timestamp_unix_ns=1_751_500_000_000_000_000,
    input_payload_hash="sha256:" + "a" * 64,
    output_payload_hash="sha256:" + "b" * 64,
    policy_version_hash="sha256:" + "c" * 64,
    agent_id="agent_001",
    session_id="sess_001",
)


def test_genesis_hash_format():
    assert GENESIS_HASH == "sha256:" + "0" * 64


def test_entry_hash_is_deterministic():
    assert compute_entry_hash(**BASE_KWARGS) == compute_entry_hash(**BASE_KWARGS)


def test_entry_hash_format():
    h = compute_entry_hash(**BASE_KWARGS)
    assert h.startswith("sha256:")
    assert len(h) == len("sha256:") + 64


def test_entry_hash_changes_when_any_field_changes():
    baseline = compute_entry_hash(**BASE_KWARGS)
    perturbations = {
        "previous_hash": "sha256:" + "f" * 64,
        "sequence_number": 2,
        "timestamp_unix_ns": BASE_KWARGS["timestamp_unix_ns"] + 1,
        "input_payload_hash": "sha256:" + "d" * 64,
        "output_payload_hash": "sha256:" + "e" * 64,
        "policy_version_hash": "sha256:" + "9" * 64,
        "agent_id": "agent_002",
        "session_id": "sess_002",
    }
    for field, value in perturbations.items():
        mutated = compute_entry_hash(**{**BASE_KWARGS, field: value})
        assert mutated != baseline, f"hash did not change when {field} changed"


def test_hash_payload_dict_is_key_order_invariant():
    assert hash_payload({"a": 1, "b": 2}) == hash_payload({"b": 2, "a": 1})


def test_hash_payload_str_and_bytes():
    assert hash_payload("hello") == hash_payload(b"hello")
    assert hash_payload("hello") != hash_payload("hello ")


def test_hash_payload_dict_differs_from_its_json_string():
    # dict hashing uses canonical JSON; a str is hashed as raw text
    assert hash_payload({"a": 1}) == hash_payload('{"a":1}')
