"""Narrow Home Assistant alert delivery adapter."""

from __future__ import annotations

from ipaddress import IPv6Address, ip_address

import httpx
from pydantic import SecretStr

from reefproof.alerting.protocol import AlertEvent


class HomeAssistantAlertAdapter:
    """POST one alert event to one environment-authorized local endpoint."""

    name = "home_assistant"

    def __init__(
        self,
        *,
        endpoint: str,
        bearer_token: str | None,
        timeout_seconds: float = 10.0,
        client: httpx.AsyncClient | None = None,
    ) -> None:
        url = httpx.URL(endpoint)
        if url.scheme not in {"http", "https"} or not url.host:
            raise ValueError("Home Assistant endpoint must be an absolute HTTP(S) URL")
        if url.username or url.password:
            raise ValueError("Home Assistant endpoint must not contain credentials")
        if url.fragment:
            raise ValueError("Home Assistant endpoint must not contain a fragment")
        try:
            address = ip_address(url.host)
        except ValueError as error:
            raise ValueError(
                "Home Assistant endpoint host must be an explicit loopback or private IP address"
            ) from error
        effective_address = (
            address.ipv4_mapped
            if isinstance(address, IPv6Address) and address.ipv4_mapped is not None
            else address
        )
        private_address = (
            effective_address.is_private
            and not effective_address.is_link_local
            and not effective_address.is_multicast
            and not effective_address.is_reserved
            and not effective_address.is_unspecified
        )
        if not effective_address.is_loopback and not private_address:
            raise ValueError("Home Assistant endpoint must use a loopback or private IP address")
        if not bearer_token:
            raise ValueError("Home Assistant bearer token must be configured")
        if timeout_seconds <= 0:
            raise ValueError("timeout_seconds must be positive")
        self._endpoint = url
        self._token = SecretStr(bearer_token) if bearer_token is not None else None
        self._timeout = timeout_seconds
        self._client = client

    def __repr__(self) -> str:
        return (
            "HomeAssistantAlertAdapter("
            f"endpoint={str(self._endpoint)!r}, "
            f"bearer_token={'configured' if self._token else 'none'})"
        )

    async def send(self, event: AlertEvent) -> None:
        headers = {"Content-Type": "application/json"}
        if self._token is not None:
            headers["Authorization"] = f"Bearer {self._token.get_secret_value()}"
        document = event.model_dump(mode="json")
        if self._client is not None:
            response = await self._client.post(
                self._endpoint,
                json=document,
                headers=headers,
                timeout=self._timeout,
                follow_redirects=False,
            )
        else:
            async with httpx.AsyncClient(
                timeout=self._timeout,
                follow_redirects=False,
            ) as client:
                response = await client.post(
                    self._endpoint,
                    json=document,
                    headers=headers,
                    follow_redirects=False,
                )
        response.raise_for_status()
