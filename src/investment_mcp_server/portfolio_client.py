"""Async client for the local portfolio backend service."""

from __future__ import annotations

from typing import Any

import httpx

from investment_mcp_server.errors import (
    NoDataError,
    UpstreamHTTPStatusError,
    UpstreamUnavailableError,
)
from investment_mcp_server.rate_limiter import RateLimiter
from investment_mcp_server.settings import Settings


class BackendPortfolioClient:
    """Lifecycle-friendly async client for the customer portfolio backend."""

    def __init__(
        self,
        settings: Settings | None = None,
        async_client: httpx.AsyncClient | None = None,
        rate_limiter: RateLimiter | None = None,
    ) -> None:
        self._settings = settings or Settings()
        self._owned_client = async_client is None
        self._client = async_client
        self._rate_limiter = rate_limiter or RateLimiter.from_rps(
            self._settings.portfolio_rate_limit_rps
        )

    async def __aenter__(self) -> "BackendPortfolioClient":
        await self.start()
        return self

    async def __aexit__(self, exc_type: object, exc: object, tb: object) -> None:
        await self.close()

    async def start(self) -> None:
        if self._client is None:
            self._client = httpx.AsyncClient(
                base_url=self._settings.portfolio_backend_base_url,
                timeout=httpx.Timeout(timeout=self._settings.portfolio_backend_timeout_seconds),
                headers={"User-Agent": "investment-mcp-server/0.1.0"},
            )

    async def close(self) -> None:
        if self._owned_client and self._client is not None:
            await self._client.aclose()
            self._client = None

    async def fetch_portfolio(self) -> dict[str, Any]:
        """Fetch the customer's portfolio payload from the backend."""
        await self.start()
        assert self._client is not None

        try:
            await self._rate_limiter.acquire()
            response = await self._client.get("/api/portfolio")
        except httpx.RequestError as exc:
            raise UpstreamUnavailableError(
                "Failed to fetch customer portfolio",
                details={"source": "portfolio_backend", "reason": str(exc)},
            ) from exc

        if response.status_code >= 400:
            raise UpstreamHTTPStatusError(
                status_code=response.status_code,
                message=f"Portfolio backend request failed with status {response.status_code}",
                details={"url": str(response.request.url)},
            )

        try:
            payload = response.json()
        except ValueError as exc:
            raise NoDataError("Portfolio backend returned non-JSON data") from exc

        if not isinstance(payload, dict):
            raise NoDataError("Portfolio backend returned unexpected portfolio data")

        return payload
