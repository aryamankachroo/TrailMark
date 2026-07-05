"""Anthropic client wrapper.

Usage::

    from anthropic import Anthropic
    from trailmark.integrations.anthropic import audit_anthropic

    client = audit_anthropic(Anthropic())
    client.messages.create(model="claude-sonnet-5", ...)   # recorded

Duck-typed: wraps any object exposing ``messages.create`` (sync or async),
so it works across anthropic-python versions without pinning it.
"""

from __future__ import annotations

import inspect
from typing import Any

from ..client import TrailMarkClient, _jsonable
from ..tracer import Trace


def _summarize_message(response: Any) -> Any:
    try:
        return {
            "model": getattr(response, "model", None),
            "content": [
                getattr(block, "text", _jsonable(block)) for block in response.content
            ],
            "stop_reason": getattr(response, "stop_reason", None),
            "usage": _jsonable(getattr(response, "usage", None)),
        }
    except AttributeError:
        return _jsonable(response)


class _AuditedCreate:
    def __init__(self, create: Any, client: TrailMarkClient | None):
        self._create = create
        self._client = client

    def __call__(self, *args: Any, **kwargs: Any) -> Any:
        trace = Trace("messages.create", action_type="llm_call",
                      client=self._client, framework="anthropic")
        trace.set_input({k: _jsonable(v) for k, v in kwargs.items()})

        if inspect.iscoroutinefunction(self._create):
            async def run():
                async with trace:
                    response = await self._create(*args, **kwargs)
                    trace.set_output(_summarize_message(response))
                    return response
            return run()

        with trace:
            response = self._create(*args, **kwargs)
            trace.set_output(_summarize_message(response))
            return response


class _Proxy:
    def __init__(self, target: Any, path: str, client: TrailMarkClient | None):
        self._target = target
        self._path = path
        self._client = client

    def __getattr__(self, name: str) -> Any:
        value = getattr(self._target, name)
        path = f"{self._path}.{name}" if self._path else name
        if path == "messages.create":
            return _AuditedCreate(value, self._client)
        if path == "messages":
            return _Proxy(value, path, self._client)
        return value


def audit_anthropic(anthropic_client: Any, client: TrailMarkClient | None = None) -> Any:
    """Wrap an Anthropic (or AsyncAnthropic) client so every message call is
    recorded to the TrailMark ledger."""
    return _Proxy(anthropic_client, "", client)
