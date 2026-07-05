import json

import httpx
import pytest

from trailmark import TrailMarkClient, TrailMarkConfig, set_default_client


@pytest.fixture
def received() -> list[dict]:
    """Events successfully 'delivered' to the mock API, in arrival order."""
    return []


def make_config(tmp_path, **overrides) -> TrailMarkConfig:
    defaults = dict(
        api_key="tmk_test_key",
        firm_id="firm_test",
        api_url="http://mock",
        agent_id="agent_test",
        framework="pytest",
        spool_dir=tmp_path / "spool",
        backoff_base=0.01,  # fast retries in tests
    )
    defaults.update(overrides)
    return TrailMarkConfig(**defaults)


@pytest.fixture
def client(tmp_path, received):
    """Client wired to an in-memory API that records every ingested event."""

    def handler(request: httpx.Request) -> httpx.Response:
        received.append(json.loads(request.content))
        return httpx.Response(201, json={"ledger_id": "entry_TEST", "entry_hash": "sha256:0"})

    c = TrailMarkClient(make_config(tmp_path), transport=httpx.MockTransport(handler))
    set_default_client(c)
    yield c
    set_default_client(None)
    c.close(timeout=2.0)
