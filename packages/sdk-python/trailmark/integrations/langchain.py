"""LangChain integration.

Usage::

    from trailmark.integrations.langchain import TrailMarkCallback

    chain.invoke(inputs, config={"callbacks": [TrailMarkCallback()]})
    # or bind it: chain.with_config(callbacks=[TrailMarkCallback()])

Every chain and tool run becomes one ledger entry; LLM calls are recorded as
``llm_call`` actions. Requires the ``langchain`` extra (``pip install
trailmark-sdk[langchain]``).
"""

from __future__ import annotations

from typing import Any
from uuid import UUID

try:
    from langchain_core.callbacks import BaseCallbackHandler
except ImportError as exc:  # pragma: no cover
    raise ImportError(
        "TrailMarkCallback requires langchain-core. "
        "Install it with: pip install 'trailmark-sdk[langchain]'"
    ) from exc

from ..client import TrailMarkClient
from ..tracer import Trace


class TrailMarkCallback(BaseCallbackHandler):
    """Records chain, tool, and LLM runs to the TrailMark ledger."""

    def __init__(self, client: TrailMarkClient | None = None):
        self._client = client
        self._traces: dict[UUID, Trace] = {}

    # ------------------------------------------------------------ internals

    def _start(self, run_id: UUID, action_type: str, action_name: str, payload: Any) -> None:
        t = Trace(
            action_name,
            action_type=action_type,
            client=self._client,
            framework="langchain",
        )
        t.set_input(payload)
        self._traces[run_id] = t

    def _end(self, run_id: UUID, output: Any) -> None:
        t = self._traces.pop(run_id, None)
        if t is not None:
            t.set_output(output)
            t._finish()

    def _error(self, run_id: UUID, error: BaseException) -> None:
        t = self._traces.pop(run_id, None)
        if t is not None:
            t._finish(error)

    @staticmethod
    def _name(serialized: dict[str, Any] | None, fallback: str) -> str:
        if serialized:
            if serialized.get("name"):
                return str(serialized["name"])
            if serialized.get("id"):
                return str(serialized["id"][-1])
        return fallback

    # --------------------------------------------------------------- chains

    def on_chain_start(self, serialized, inputs, *, run_id, **kwargs) -> None:
        self._start(run_id, "chain_run", self._name(serialized, "chain"), inputs)

    def on_chain_end(self, outputs, *, run_id, **kwargs) -> None:
        self._end(run_id, outputs)

    def on_chain_error(self, error, *, run_id, **kwargs) -> None:
        self._error(run_id, error)

    # ---------------------------------------------------------------- tools

    def on_tool_start(self, serialized, input_str, *, run_id, **kwargs) -> None:
        self._start(run_id, "tool_call", self._name(serialized, "tool"), input_str)

    def on_tool_end(self, output, *, run_id, **kwargs) -> None:
        self._end(run_id, output)

    def on_tool_error(self, error, *, run_id, **kwargs) -> None:
        self._error(run_id, error)

    # ----------------------------------------------------------------- llms

    def on_llm_start(self, serialized, prompts, *, run_id, **kwargs) -> None:
        self._start(run_id, "llm_call", self._name(serialized, "llm"), {"prompts": prompts})

    def on_chat_model_start(self, serialized, messages, *, run_id, **kwargs) -> None:
        rendered = [[getattr(m, "content", str(m)) for m in batch] for batch in messages]
        self._start(run_id, "llm_call", self._name(serialized, "chat_model"), {"messages": rendered})

    def on_llm_end(self, response, *, run_id, **kwargs) -> None:
        try:
            output = {
                "generations": [
                    [getattr(g, "text", str(g)) for g in batch]
                    for batch in response.generations
                ]
            }
        except AttributeError:
            output = {"response": str(response)}
        self._end(run_id, output)

    def on_llm_error(self, error, *, run_id, **kwargs) -> None:
        self._error(run_id, error)
