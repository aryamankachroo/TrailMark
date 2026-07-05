#!/usr/bin/env python3
"""Seed the local TrailMark stack with realistic demo ledger activity.

Usage (API must be running on :8000):
    python scripts/seed_demo.py [--firm firm_demo] [--entries 40]

Writes through the real ingest API — every seeded entry is hash-chained,
signed, and WORM-stored exactly like production traffic.
"""

import argparse
import json
import random
import urllib.request

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

    created = []
    for i in range(args.entries):
        action_type, action_name, base, flags = rng.choice(ACTIONS)
        score = round(min(0.99, max(0.01, rng.gauss(base, 0.07))), 3)
        requires = score > 0.75
        event = {
            "firm_id": args.firm,
            "agent": dict(zip(("agent_id", "framework"), rng.choice(AGENTS))),
            "session": {
                "session_id": f"sess_{rng.randrange(16**8):08x}",
                "registered_rep_id": rng.choice(REPS),
            },
            "action": {"action_type": action_type, "action_name": action_name},
            "policy": {
                "policy_version_id": "polv_2026_q2_007",
                "policy_version_hash": "sha256:" + "7d" * 32,
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


if __name__ == "__main__":
    main()
