import pytest

import trailmark
from trailmark import audit, session, trace


def wait_for_events(client, received, count, timeout=5.0):
    assert client.flush(timeout)
    assert len(received) == count, f"expected {count} events, got {len(received)}"


# ---------------------------------------------------------------- decorator

def test_audit_decorator_sync(client, received):
    @audit(action_name="portfolio_rebalance")
    def rebalance(portfolio_id: str, dry_run: bool = False):
        return {"orders": 3}

    assert rebalance("pf_1", dry_run=True) == {"orders": 3}
    wait_for_events(client, received, 1)

    event = received[0]
    assert event["action"] == {"action_type": "function_call", "action_name": "portfolio_rebalance"}
    assert event["input"]["arguments"] == {"portfolio_id": "pf_1", "dry_run": True}
    assert event["output"]["result"] == {"orders": 3}
    assert event["output"]["duration_ms"] >= 0
    assert event["firm_id"] == "firm_test"


async def test_audit_decorator_async(client, received):
    @audit()
    async def approve_margin_extension(account_id: str):
        return "approved"

    assert await approve_margin_extension("acct_9") == "approved"
    wait_for_events(client, received, 1)
    event = received[0]
    assert event["action"]["action_name"] == "approve_margin_extension"
    assert "margin_risk" in event["risk"]["risk_flags"]  # heuristic keyword hit


def test_audit_decorator_records_exception_then_reraises(client, received):
    @audit(action_name="wire_transfer_execute")
    def explode(amount: int):
        raise ValueError("insufficient funds")

    with pytest.raises(ValueError, match="insufficient funds"):
        explode(amount=5_000_000)

    wait_for_events(client, received, 1)
    event = received[0]
    assert "exception_raised" in event["risk"]["risk_flags"]
    assert "insufficient funds" in event["output"]["error"]
    assert "traceback" in event["output"]


def test_audit_snapshot_functions(client, received):
    state = {"positions": 10}

    @audit(action_name="run_liquidation", snapshot_before=lambda: dict(state),
           snapshot_after=lambda: dict(state))
    def liquidate():
        state["positions"] = 0

    liquidate()
    wait_for_events(client, received, 1)
    event = received[0]
    assert event["input"]["state_before"] == {"positions": 10}
    assert event["output"]["state_after"] == {"positions": 0}


# ---------------------------------------------------------- context manager

def test_trace_context_manager_sync(client, received):
    with trace("investment_recommendation", action_type="decision") as t:
        t.set_input({"client": "cl_42"})
        t.set_output({"recommendation": "rebalance to 60/40"})
        t.set_reasoning("Client risk profile is moderate.")

    wait_for_events(client, received, 1)
    event = received[0]
    assert event["input"] == {"client": "cl_42"}
    assert event["reasoning_trace"] == "Client risk profile is moderate."
    assert "recommendation" in event["risk"]["risk_flags"]


async def test_trace_context_manager_async_with_exception(client, received):
    with pytest.raises(RuntimeError):
        async with trace("account_liquidation") as t:
            t.set_input({"account": "acct_1"})
            raise RuntimeError("downstream failure")

    wait_for_events(client, received, 1)
    assert "exception_raised" in received[0]["risk"]["risk_flags"]


def test_trace_risk_override_beats_heuristics(client, received):
    with trace("wire_transfer_review") as t:  # heuristics would say HIGH
        t.set_risk(risk_score=0.05, risk_flags=["manual_override"])

    wait_for_events(client, received, 1)
    risk = received[0]["risk"]
    assert risk["risk_score"] == 0.05
    assert risk["risk_tier"] == "LOW"
    assert risk["requires_supervisor_review"] is False
    assert risk["risk_flags"] == ["manual_override"]


# ----------------------------------------------------------------- session

def test_session_scoping(client, received):
    with session(session_id="sess_abc", registered_rep_id="rep_007"):
        with trace("kyc_check") as t:
            t.set_input({})
    with trace("kyc_check") as t:  # outside the session scope
        t.set_input({})

    wait_for_events(client, received, 2)
    assert received[0]["session"] == {"session_id": "sess_abc", "registered_rep_id": "rep_007"}
    assert received[1]["session"]["session_id"] == client.default_session_id


def test_unconfigured_sdk_raises_helpfully():
    trailmark.set_default_client(None)
    with pytest.raises(RuntimeError, match="trailmark.configure"):
        trace("anything")
