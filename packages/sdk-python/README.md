# trailmark-sdk

Immutable, compliance-grade audit trails for AI agents in financial services.
Every traced action becomes a hash-chained, Ed25519-signed, WORM-stored ledger
entry satisfying SEC Rule 17a-4, FINRA Rule 3110, and SEC Rule 206(4)-7.

```bash
pip install trailmark-sdk            # + [langchain] for the LangChain callback
```

## Configure once

```python
import trailmark

trailmark.configure(
    api_key="tmk_...",
    firm_id="firm_acme",
    agent_id="agent_rebalancer",
    framework="langchain",
    policy_version_id="polv_2026_q2_007",
    policy_version_hash="sha256:...",
)
```

## Three ways to record

```python
# 1 — decorator (sync or async)
@trailmark.audit(action_name="portfolio_rebalance")
async def rebalance(portfolio_id: str): ...

# 2 — context manager (sync or async)
async with trailmark.trace("investment_recommendation") as t:
    t.set_input({"client": client_id})
    result = await agent.run()
    t.set_output(result)

# 3 — LangChain callback
from trailmark.integrations.langchain import TrailMarkCallback
chain.invoke(inputs, config={"callbacks": [TrailMarkCallback()]})
```

OpenAI / Anthropic clients can be wrapped directly:

```python
from trailmark.integrations.anthropic import audit_anthropic
client = audit_anthropic(Anthropic())   # every messages.create is recorded
```

## Delivery guarantees

- `submit` never blocks the agent — events queue to a background worker.
- Failed deliveries retry with backoff, then spool to disk
  (`~/.trailmark/spool`) and replay on next start. **No event is ever lost.**
- Call `trailmark.flush()` before process exit to drain synchronously
  (an `atexit` hook also drains and spools as a backstop).
