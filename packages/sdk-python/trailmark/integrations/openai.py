"""OpenAI client wrapper.

Usage::

    from openai import OpenAI
    from trailmark.integrations.openai import audit_openai

    client = audit_openai(OpenAI())
    client.chat.completions.create(...)   # recorded to the ledger

Duck-typed: wraps any object exposing ``chat.completions.create`` (sync or
async), so it works across openai-python versions without pinning it as a
dependency.
"""

from __future__ import annotations

import inspect
from typing import Any

from ..client import TrailMarkClient, _jsonable
from ..tracer import Trace


def _summarize_completion(response: Any) -> Any:
    try:
        return {
            "model": getattr(response, "model", None),
            "choices": [
                {
                    "content": getattr(getattr(c, "message", None), "content", None),
                    "finish_reason": getattr(c, "finish_reason", None),
                }
                for c in response.choices
            ],
            "usage": _jsonable(getattr(response, "usage", None)),
        }
    except AttributeError:
        return _jsonable(response)


class _AuditedCreate:
    def __init__(self, create: Any, client: TrailMarkClient | None):
        self._create = create
        self._client = client

    def __call__(self, *args: Any, **kwargs: Any) -> Any:
        trace = Trace("chat.completions.create", action_type="llm_call",
                      client=self._client, framework="openai")
        trace.set_input({k: _jsonable(v) for k, v in kwargs.items()})

        if inspect.iscoroutinefunction(self._create):
            async def run():
                async with trace:
                    response = await self._create(*args, **kwargs)
                    trace.set_output(_summarize_completion(response))
                    return response
            return run()

        with trace:
            response = self._create(*args, **kwargs)
            trace.set_output(_summarize_completion(response))
            return response


class _Proxy:
    """Attribute-forwarding proxy that swaps in the audited create()."""

    def __init__(self, target: Any, path: str, client: TrailMarkClient | None):
        self._target = target
        self._path = path
        self._client = client

    def __getattr__(self, name: str) -> Any:
        value = getattr(self._target, name)
        path = f"{self._path}.{name}" if self._path else name
        if path == "chat.completions.create":
            return _AuditedCreate(value, self._client)
        if path in ("chat", "chat.completions"):
            return _Proxy(value, path, self._client)
        return value


def audit_openai(openai_client: Any, client: TrailMarkClient | None = None) -> Any:
    """Wrap an OpenAI (or AsyncOpenAI) client so every chat completion is
    recorded to the TrailMark ledger."""
    return _Proxy(openai_client, "", client)
