#!/usr/bin/env python3
"""Seed the local TrailMark stack with realistic demo ledger activity.

Usage (API must be running on :8000):
    python scripts/seed_demo.py [--firm firm_demo] [--entries 40]

Writes through the real ingest API — every seeded entry is hash-chained,
signed, and WORM-stored exactly like production traffic. Also registers a
small policy registry so SEC 206(4)-7 replay demonstrates all three verdicts
(reconstructed-consistent, discrepancy, and not-in-registry).
"""

import argparse
import hashlib
import json
import random
import urllib.error
import urllib.request
from datetime import datetime, timedelta, timezone

API = "http://localhost:8000"

AGENTS = [
    ("agent_portfolio_rebalancer", "langchain"),
    ("agent_trade_surveillance", "openai_assistants"),
    ("agent_client_comms", "anthropic_sdk"),
    ("agent_kyc_screening", "crewai"),
]

ACTIONS = [
    # (action_type, action_name, base_risk, flags)
    ("tool_call", "portfolio_rebalance", 0.15, []),
    ("tool_call", "generate_client_email", 0.10, []),
    ("tool_call", "kyc_watchlist_screen", 0.30, []),
    ("decision", "trade_recommendation", 0.55, ["unsolicited_recommendation"]),
    ("tool_call", "wire_transfer_review", 0.82, ["large_notional"]),
    ("decision", "margin_extension_approval", 0.88, ["margin_risk", "large_notional"]),
    ("tool_call", "options_strategy_proposal", 0.91, ["complex_product", "retail_account"]),
    ("decision", "account_liquidation", 0.95, ["full_liquidation", "off_hours_trading"]),
]

REPS = ["rep_1042", "rep_2210", "rep_3308", None]


def post(path: str, token: str, body: dict) -> dict:
    req = urllib.request.Request(
        f"{API}{path}",
        data=json.dumps(body).encode(),
        headers={"Content-Type": "application/json", "Authorization": f"Bearer {token}"},
        method="POST",
    )
    with urllib.request.urlopen(req) as resp:
        return json.loads(resp.read())


def get(path: str, token: str) -> dict:
    req = urllib.request.Request(
        f"{API}{path}", headers={"Authorization": f"Bearer {token}"}
    )
    with urllib.request.urlopen(req) as resp:
        return json.loads(resp.read())


def content_hash(content: str) -> str:
    """Mirror the API's hash_payload(str) so we can locate an already-registered
    version by its content on a re-seed (policy_hash is globally unique)."""
    return "sha256:" + hashlib.sha256(content.encode("utf-8")).hexdigest()


def iso_days_ago(days: int) -> str:
    return (datetime.now(timezone.utc) - timedelta(days=days)).isoformat()


# Realistic written-supervisory-procedure text so the replay viewer shows
# something a compliance officer would actually read.
WSP_TRADE_V1 = """WRITTEN SUPERVISORY PROCEDURES — TRADE SURVEILLANCE (v1)

1. Scope. All agent-initiated orders are subject to pre-trade review.
2. Notional limits. Orders above USD 100,000 require principal approval.
3. Restricted list. Orders in restricted securities are blocked.
4. Recordkeeping. Every decision is preserved under SEC Rule 17a-4.
"""

WSP_TRADE_V2 = """WRITTEN SUPERVISORY PROCEDURES — TRADE SURVEILLANCE (v2)

1. Scope. All agent-initiated orders are subject to pre-trade review.
2. Notional limits. Orders above USD 50,000 require principal approval
   (threshold lowered from USD 100,000 effective this version).
3. Restricted list. Orders in restricted securities are blocked and escalated.
4. Options & margin. Complex products require Series 24 principal attestation.
5. Recordkeeping. Every decision is preserved under SEC Rule 17a-4.
"""

WSP_COMMS_V1 = """WRITTEN SUPERVISORY PROCEDURES — CLIENT COMMUNICATIONS (v1)

1. Suitability. Recommendations must document a reasonable basis.
2. Disclosures. Material conflicts must be disclosed in the communication.
3. Retention. All client communications are retained for six years.
"""


def register_or_recover(token: str, policy_id: str, name: str, content: str, effective_at: str) -> dict:
    """Register a policy version, or recover the existing one on re-seed
    (identical content collides on the globally-unique policy_hash)."""
    try:
        return post(
            "/v1/policies",
            token,
            {
                "policy_id": policy_id,
                "name": name,
                "content": content,
                "effective_at": effective_at,
            },
        )
    except urllib.error.HTTPError as exc:
        if exc.code != 409:
            raise
        target = content_hash(content)
        for version in get(f"/v1/policies/{policy_id}/versions", token):
            if version["policy_hash"] == target:
                return version
        raise


def seed_policies(token: str) -> dict:
    """Register two policies (one with a superseding v2) and return the version
    references the entry loop uses to exercise each replay verdict."""
    ts_v1 = register_or_recover(
        token, "wsp_trade_surveillance",
        "Written Supervisory Procedures — Trade Surveillance",
        WSP_TRADE_V1, iso_days_ago(60),
    )
    ts_v2 = register_or_recover(
        token, "wsp_trade_surveillance",
        "Written Supervisory Procedures — Trade Surveillance",
        WSP_TRADE_V2, iso_days_ago(30),
    )
    cc_v1 = register_or_recover(
        token, "wsp_client_communications",
        "Written Supervisory Procedures — Client Communications",
        WSP_COMMS_V1, iso_days_ago(90),
    )
    return {
        # Versions currently in force → entries referencing them replay CONSISTENT
        "in_force": [
            (ts_v2["id"], ts_v2["policy_hash"]),
            (cc_v1["id"], cc_v1["policy_hash"]),
        ],
        # Superseded v1 → an entry recorded under it now reconstructs to v2 → DISCREPANCY
        "stale": (ts_v1["id"], ts_v1["policy_hash"]),
    }


def policy_reference(policies: dict, rng: random.Random) -> tuple[str, str]:
    """Pick a policy reference for an entry, weighted to show all three
    replay verdicts across the seeded ledger."""
    roll = rng.random()
    if roll < 0.15:
        return policies["stale"]  # RECONSTRUCTION_DISCREPANCY
    if roll < 0.30:
        # An externally managed policy never uploaded to the registry.
        fake_hash = "sha256:" + "".join(rng.choice("0123456789abcdef") for _ in range(64))
        return f"polv_external_{rng.randrange(10**6):06d}", fake_hash
    return rng.choice(policies["in_force"])  # RECONSTRUCTED_CONSISTENT


def tier(score: float) -> str:
    if score > 0.85:
        return "CRITICAL"
    if score > 0.75:
        return "HIGH"
    if score >= 0.4:
        return "MEDIUM"
    return "LOW"


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--firm", default="firm_demo")
    parser.add_argument("--entries", type=int, default=40)
    args = parser.parse_args()
    token = f"tmk_dev_{args.firm}"
    rng = random.Random(17)  # deterministic demo data

    policies = seed_policies(token)

    created = []
    for i in range(args.entries):
        action_type, action_name, base, flags = rng.choice(ACTIONS)
        score = round(min(0.99, max(0.01, rng.gauss(base, 0.07))), 3)
        requires = score > 0.75
        policy_version_id, policy_version_hash = policy_reference(policies, rng)
        event = {
            "firm_id": args.firm,
            "agent": dict(zip(("agent_id", "framework"), rng.choice(AGENTS))),
            "session": {
                "session_id": f"sess_{rng.randrange(16**8):08x}",
                "registered_rep_id": rng.choice(REPS),
            },
            "action": {"action_type": action_type, "action_name": action_name},
            "policy": {
                "policy_version_id": policy_version_id,
                "policy_version_hash": policy_version_hash,
            },
            "risk": {
                "risk_score": score,
                "risk_tier": tier(score),
                "risk_flags": flags if requires else [],
                "requires_supervisor_review": requires,
            },
            "input": {"account_id": f"acct_{rng.randrange(10**6):06d}", "request_index": i},
            "output": {"status": "executed", "confirmation": f"cnf_{rng.randrange(16**6):06x}"},
            "reasoning_trace": f"Evaluated {action_name} against policy polv_2026_q2_007; "
            f"risk factors scored {score}.",
        }
        created.append((post("/v1/ingest", token, event), requires))

    # Attest roughly half of the older review-required entries so the ledger
    # shows a realistic mix of PENDING / APPROVED / REJECTED / ESCALATED.
    decisions = [
        ("APPROVED", "APPROVED_POLICY_CONSISTENT"),
        ("APPROVED", "APPROVED_WITH_CONDITIONS"),
        ("REJECTED", "REJECTED_RISK_LIMIT_EXCEEDED"),
        ("ESCALATED", "ESCALATED_TO_COMPLIANCE"),
    ]
    pending = [entry for entry, requires in created if requires]
    attested = 0
    for entry in pending[: max(1, len(pending) // 2)]:
        decision, reason = rng.choice(decisions)
        post(
            "/v1/attestations",
            token,
            {
                "audit_entry_id": entry["ledger_id"],
                "decision": decision,
                "reason_code": reason,
                "notes": "Seeded supervisory review for demonstration.",
                "supervisor_finra_crd": "5551234",
                "supervisor_role": "Series 24 Principal",
            },
        )
        attested += 1

    print(
        f"Seeded {len(created)} entries for {args.firm} "
        f"({len(pending)} required review; {attested} attested, "
        f"{len(pending) - attested} left pending)."
    )
    print(
        "Registered 2 policies (3 versions) — replay shows consistent, "
        "discrepancy, and not-in-registry verdicts across the ledger."
    )


if __name__ == "__main__":
    main()
