"""Async stock data provider client with retry, timeout, and rate-limit handling."""

from __future__ import annotations

import asyncio
import random
from typing import Any

import httpx

from investment_mcp_server.errors import UpstreamHTTPStatusError
from investment_mcp_server.rate_limiter import RateLimiter
from investment_mcp_server.settings import Settings


RETRYABLE_STATUS_CODES = {429, 500, 502, 503, 504}


class YahooStockClient:
    """Lifecycle-friendly async client for Yahoo Finance stock chart API requests."""

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
            self._settings.yf_rate_limit_rps
        )

    async def __aenter__(self) -> "YahooStockClient":
        await self.start()
        return self

    async def __aexit__(self, exc_type: object, exc: object, tb: object) -> None:
        await self.close()

    async def start(self) -> None:
        if self._client is None:
            self._client = httpx.AsyncClient(
                base_url=self._settings.yf_base_url,
                timeout=httpx.Timeout(
                    timeout=self._settings.yf_timeout_total_seconds,
                    connect=self._settings.yf_timeout_connect_seconds,
                    read=self._settings.yf_timeout_read_seconds,
                ),
                headers={"User-Agent": self._settings.yf_user_agent},
            )

    async def close(self) -> None:
        if self._owned_client and self._client is not None:
            await self._client.aclose()
            self._client = None

    async def fetch_chart(
        self,
        ticker: str,
        period1: int,
        period2: int,
        interval: str,
        include_prepost: bool | None = None,
    ) -> dict[str, Any]:
        """Fetch chart data from Yahoo Finance and return parsed JSON."""
        await self.start()
        assert self._client is not None

        include_prepost_value = (
            include_prepost
            if include_prepost is not None
            else self._settings.yf_default_include_prepost
        )

        params = {
            "period1": period1,
            "period2": period2,
            "interval": interval,
            "includePrePost": str(include_prepost_value).lower(),
            "source": "cosaic",
        }
        path = f"/v8/finance/chart/{ticker}"

        attempts = self._settings.yf_max_retries + 1
        last_exception: Exception | None = None

        for attempt in range(1, attempts + 1):
            try:
                await self._rate_limiter.acquire()
                response = await self._client.get(path, params=params)
                if response.status_code >= 400:
                    if response.status_code in RETRYABLE_STATUS_CODES and attempt < attempts:
                        await self._sleep_backoff(attempt)
                        continue
                    raise UpstreamHTTPStatusError(
                        status_code=response.status_code,
                        message=f"Yahoo request failed with status {response.status_code}",
                        details={"url": str(response.request.url)},
                    )

                return response.json()

            except (httpx.TimeoutException, httpx.RequestError) as exc:
                last_exception = exc
                if attempt >= attempts:
                    raise
                await self._sleep_backoff(attempt)

        if last_exception is not None:
            raise last_exception

        raise RuntimeError("Unexpected retry state in YahooStockClient.fetch_chart")

    async def _sleep_backoff(self, attempt: int) -> None:
        base = self._settings.yf_retry_backoff_base
        raw_delay = base * (2 ** (attempt - 1))
        jitter = random.uniform(0, base)
        await asyncio.sleep(raw_delay + jitter)
