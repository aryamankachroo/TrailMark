"""TrailMark SDK — immutable, compliance-grade audit trails for AI agents.

Quick start::

    import trailmark

    trailmark.configure(
        api_key="tmk_...",
        firm_id="firm_acme",
        agent_id="agent_rebalancer",
        framework="langchain",
        policy_version_id="polv_2026_q2_007",
        policy_version_hash="sha256:...",
    )

    @trailmark.audit(action_name="portfolio_rebalance")
    async def rebalance(portfolio_id: str): ...

    async with trailmark.trace("investment_recommendation") as t:
        t.set_input({"client": client_id})
        result = await agent.run()
        t.set_output(result)
"""

from .client import TrailMarkClient, TrailMarkConfig
from .risk import RiskConfig
from .tracer import (
    Trace,
    audit,
    get_default_client,
    session,
    set_default_client,
    trace,
)

__version__ = "0.1.0"

__all__ = [
    "audit",
    "trace",
    "session",
    "configure",
    "flush",
    "Trace",
    "TrailMarkClient",
    "TrailMarkConfig",
    "RiskConfig",
    "get_default_client",
    "set_default_client",
]


def configure(**kwargs) -> TrailMarkClient:
    """Create the process-wide default client. Accepts every TrailMarkConfig
    field as a keyword argument; returns the client for direct use."""
    client = TrailMarkClient(TrailMarkConfig(**kwargs))
    set_default_client(client)
    return client


def flush(timeout: float = 10.0) -> bool:
    """Block until all pending audit events are delivered (best effort)."""
    return get_default_client().flush(timeout)
