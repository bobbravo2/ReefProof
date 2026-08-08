from __future__ import annotations

import asyncio
import json
from datetime import datetime

import httpx
import pytest

from reefproof.alerting import AlertEvent
from reefproof.alerting.home_assistant import HomeAssistantAlertAdapter
from reefproof.invariants import Severity

NOW = datetime.fromisoformat("2026-07-25T23:00:00-04:00")
HASH = f"sha256:{'f' * 64}"


def _event() -> AlertEvent:
    return AlertEvent(
        source="ReefProof",
        title="HYDROS reliability invariant violated",
        severity=Severity.CRITICAL,
        invariant_id="RP-CIRC-001",
        summary="Both returns share one power domain.",
        first_seen=NOW,
        configuration_hash=HASH,
        policy_hash=HASH,
        affected_entities=("Return A", "Return B", "MAIN-6"),
        recommended_action="Restore independent return-pump power domains.",
        reefproof_url="http://reefproof.local/findings/RP-CIRC-001",
        recovery=False,
    )


def test_home_assistant_adapter_posts_exact_event_to_fixed_endpoint() -> None:
    requests: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        return httpx.Response(202, request=request)

    client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    adapter = HomeAssistantAlertAdapter(
        endpoint="http://192.168.10.20:8123/api/webhook/reefproof",
        bearer_token="test-token",
        client=client,
    )

    asyncio.run(adapter.send(_event()))
    asyncio.run(client.aclose())

    assert len(requests) == 1
    request = requests[0]
    assert str(request.url) == "http://192.168.10.20:8123/api/webhook/reefproof"
    assert request.method == "POST"
    assert request.headers["authorization"] == "Bearer test-token"
    document = json.loads(request.content)
    assert document["invariant_id"] == "RP-CIRC-001"
    assert document["affected_entities"] == ["Return A", "Return B", "MAIN-6"]


def test_home_assistant_adapter_raises_classified_http_failure() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(503, request=request)

    client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    adapter = HomeAssistantAlertAdapter(
        endpoint="http://127.0.0.1:8123/api/webhook/reefproof",
        bearer_token="test-token",
        client=client,
    )

    with pytest.raises(httpx.HTTPStatusError):
        asyncio.run(adapter.send(_event()))
    asyncio.run(client.aclose())


def test_adapter_representation_does_not_expose_token() -> None:
    adapter = HomeAssistantAlertAdapter(
        endpoint="https://10.0.0.20:8123/api/webhook/reefproof",
        bearer_token="do-not-log-me",
    )

    assert "do-not-log-me" not in repr(adapter)


@pytest.mark.parametrize(
    "endpoint",
    (
        "https://example.com/api/webhook/reefproof",
        "http://home-assistant.local/api/webhook/reefproof",
        "http://169.254.169.254/latest/meta-data",
        "http://[::ffff:169.254.169.254]/latest/meta-data",
        "http://[::ffff:8.8.8.8]/collect",
        "http://0.0.0.0:8123/api/webhook/reefproof",
        "http://224.0.0.1:8123/api/webhook/reefproof",
        "http://user:password@127.0.0.1:8123/api/webhook/reefproof",
        "http://127.0.0.1:8123/api/webhook/reefproof#fragment",
    ),
)
def test_adapter_rejects_unapproved_destination_before_request(endpoint: str) -> None:
    request_count = 0

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal request_count
        request_count += 1
        return httpx.Response(202, request=request)

    client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    with pytest.raises(ValueError):
        HomeAssistantAlertAdapter(
            endpoint=endpoint,
            bearer_token="must-not-leave",
            client=client,
        )
    asyncio.run(client.aclose())

    assert request_count == 0


def test_adapter_requires_environment_authorized_bearer_token() -> None:
    with pytest.raises(ValueError, match="bearer token"):
        HomeAssistantAlertAdapter(
            endpoint="http://127.0.0.1:8123/api/webhook/reefproof",
            bearer_token=None,
        )


def test_adapter_does_not_follow_redirects() -> None:
    requests: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        return httpx.Response(
            302,
            headers={"Location": "https://example.com/collect"},
            request=request,
        )

    client = httpx.AsyncClient(
        transport=httpx.MockTransport(handler),
        follow_redirects=True,
    )
    adapter = HomeAssistantAlertAdapter(
        endpoint="http://127.0.0.1:8123/api/webhook/reefproof",
        bearer_token="test-token",
        client=client,
    )

    with pytest.raises(httpx.HTTPStatusError):
        asyncio.run(adapter.send(_event()))
    asyncio.run(client.aclose())

    assert len(requests) == 1
    assert requests[0].url.host == "127.0.0.1"
