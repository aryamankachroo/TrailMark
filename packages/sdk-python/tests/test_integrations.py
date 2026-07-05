"""Integration adapters: LangChain callback, OpenAI/Anthropic wrappers."""

from types import SimpleNamespace
from uuid import uuid4

import pytest

from trailmark.integrations.anthropic import audit_anthropic
from trailmark.integrations.openai import audit_openai

langchain_core = pytest.importorskip("langchain_core")
from trailmark.integrations.langchain import TrailMarkCallback  # noqa: E402


def wait_for_events(client, received, count, timeout=5.0):
    assert client.flush(timeout)
    assert len(received) == count, f"expected {count} events, got {len(received)}"


# ---------------------------------------------------------------- langchain

def test_langchain_chain_run_recorded(client, received):
    cb = TrailMarkCallback()
    run_id = uuid4()
    cb.on_chain_start({"name": "rebalance_chain"}, {"portfolio": "pf_1"}, run_id=run_id)
    cb.on_chain_end({"orders": 2}, run_id=run_id)

    wait_for_events(client, received, 1)
    event = received[0]
    assert event["action"] == {"action_type": "chain_run", "action_name": "rebalance_chain"}
    assert event["agent"]["framework"] == "langchain"
    assert event["input"] == {"portfolio": "pf_1"}
    assert event["output"] == {"orders": 2}


def test_langchain_tool_error_recorded(client, received):
    cb = TrailMarkCallback()
    run_id = uuid4()
    cb.on_tool_start({"name": "wire_transfer_tool"}, "send $1M", run_id=run_id)
    cb.on_tool_error(RuntimeError("bank API timeout"), run_id=run_id)

    wait_for_events(client, received, 1)
    event = received[0]
    assert "exception_raised" in event["risk"]["risk_flags"]
    assert "bank API timeout" in event["output"]["error"]


def test_langchain_llm_run_recorded(client, received):
    cb = TrailMarkCallback()
    run_id = uuid4()
    cb.on_llm_start({"name": "gpt-4o"}, ["Summarize the portfolio."], run_id=run_id)
    generation = SimpleNamespace(text="The portfolio is balanced.")
    cb.on_llm_end(SimpleNamespace(generations=[[generation]]), run_id=run_id)

    wait_for_events(client, received, 1)
    event = received[0]
    assert event["action"]["action_type"] == "llm_call"
    assert event["output"]["generations"] == [["The portfolio is balanced."]]


def test_langchain_real_runnable_end_to_end(client, received):
    """Drive an actual langchain-core runnable with the callback attached."""
    from langchain_core.runnables import RunnableLambda

    chain = RunnableLambda(lambda x: {"total": x["a"] + x["b"]}, name="adder_chain")
    result = chain.invoke({"a": 2, "b": 3}, config={"callbacks": [TrailMarkCallback()]})
    assert result == {"total": 5}

    client.flush(5.0)
    assert len(received) >= 1
    event = received[0]
    assert event["action"]["action_name"] == "adder_chain"
    assert event["output"] == {"total": 5}


# ------------------------------------------------------------------ openai

def test_openai_wrapper_sync(client, received):
    fake_response = SimpleNamespace(
        model="gpt-4o",
        choices=[SimpleNamespace(message=SimpleNamespace(content="Hello"), finish_reason="stop")],
        usage=None,
    )
    fake = SimpleNamespace(
        chat=SimpleNamespace(
            completions=SimpleNamespace(create=lambda **kw: fake_response)
        ),
        api_key="sk-secret",
    )

    wrapped = audit_openai(fake)
    resp = wrapped.chat.completions.create(model="gpt-4o", messages=[{"role": "user", "content": "hi"}])
    assert resp is fake_response
    assert wrapped.api_key == "sk-secret"  # non-audited attrs pass through

    wait_for_events(client, received, 1)
    event = received[0]
    assert event["action"] == {"action_type": "llm_call", "action_name": "chat.completions.create"}
    assert event["agent"]["framework"] == "openai"
    assert event["output"]["choices"][0]["content"] == "Hello"


async def test_openai_wrapper_async(client, received):
    async def acreate(**kw):
        return SimpleNamespace(
            model="gpt-4o",
            choices=[SimpleNamespace(message=SimpleNamespace(content="async hi"), finish_reason="stop")],
            usage=None,
        )

    fake = SimpleNamespace(chat=SimpleNamespace(completions=SimpleNamespace(create=acreate)))
    resp = await audit_openai(fake).chat.completions.create(model="gpt-4o", messages=[])
    assert resp.choices[0].message.content == "async hi"
    wait_for_events(client, received, 1)


# --------------------------------------------------------------- anthropic

def test_anthropic_wrapper_sync(client, received):
    fake_response = SimpleNamespace(
        model="claude-sonnet-5",
        content=[SimpleNamespace(text="Bonjour")],
        stop_reason="end_turn",
        usage=None,
    )
    fake = SimpleNamespace(messages=SimpleNamespace(create=lambda **kw: fake_response))

    resp = audit_anthropic(fake).messages.create(model="claude-sonnet-5", max_tokens=100)
    assert resp is fake_response

    wait_for_events(client, received, 1)
    event = received[0]
    assert event["action"]["action_name"] == "messages.create"
    assert event["agent"]["framework"] == "anthropic"
    assert event["output"]["content"] == ["Bonjour"]
    assert event["input"]["model"] == "claude-sonnet-5"


def test_anthropic_wrapper_records_api_errors(client, received):
    def failing_create(**kw):
        raise ConnectionError("anthropic API unreachable")

    fake = SimpleNamespace(messages=SimpleNamespace(create=failing_create))
    with pytest.raises(ConnectionError):
        audit_anthropic(fake).messages.create(model="claude-sonnet-5")

    wait_for_events(client, received, 1)
    assert "exception_raised" in received[0]["risk"]["risk_flags"]
