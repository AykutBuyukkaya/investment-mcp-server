"""Async wrapper around the yfinance library for stock fundamentals (PE, EPS, ...)."""

from __future__ import annotations

import asyncio
from typing import Any

import yfinance as yf

from investment_mcp_server.errors import (
    NoDataError,
    RateLimitedError,
    TickerNotFoundError,
    UpstreamUnavailableError,
)
from investment_mcp_server.models import StockFundamentals
from investment_mcp_server.rate_limiter import RateLimiter


class YFinanceFundamentalsClient:
    """Fetches fundamentals (PE, EPS, market cap, ...) via the yfinance library.

    yfinance performs blocking network I/O under the hood, so each lookup runs in a
    worker thread via ``asyncio.to_thread`` to avoid blocking the event loop.
    """

    def __init__(self, rate_limiter: RateLimiter | None = None) -> None:
        self._rate_limiter = rate_limiter or RateLimiter.from_rps(2.0)

    async def close(self) -> None:
        return None

    async def get_fundamentals(self, symbol: str) -> StockFundamentals:
        await self._rate_limiter.acquire()
        try:
            info = await asyncio.to_thread(self._fetch_info, symbol)
        except Exception as exc:
            message = str(exc)
            if "429" in message or "rate limit" in message.lower() or "too many requests" in message.lower():
                raise RateLimitedError(
                    f"Yahoo Finance rate limited fundamentals request for {symbol}",
                    details={"source": "yfinance", "reason": message},
                ) from exc
            raise UpstreamUnavailableError(
                f"Failed to fetch fundamentals for {symbol} via yfinance",
                details={"source": "yfinance", "reason": message},
            ) from exc

        if not info or not isinstance(info, dict):
            raise NoDataError(f"No fundamentals data returned for {symbol}")

        has_identity = bool(info.get("symbol")) or info.get("regularMarketPrice") is not None
        if not has_identity:
            raise TickerNotFoundError(f"No fundamentals data found for symbol {symbol}")

        return StockFundamentals(
            symbol=info.get("symbol"),
            short_name=info.get("shortName") or info.get("longName"),
            currency=info.get("currency"),
            exchange=info.get("exchange") or info.get("fullExchangeName"),
            sector=info.get("sector"),
            industry=info.get("industry"),
            regular_market_price=info.get("regularMarketPrice") or info.get("currentPrice"),
            market_cap=info.get("marketCap"),
            trailing_pe=info.get("trailingPE"),
            forward_pe=info.get("forwardPE"),
            trailing_eps=info.get("trailingEps"),
            forward_eps=info.get("forwardEps"),
            price_to_book=info.get("priceToBook"),
            book_value=info.get("bookValue"),
            dividend_yield=info.get("dividendYield"),
            beta=info.get("beta"),
            fifty_two_week_high=info.get("fiftyTwoWeekHigh"),
            fifty_two_week_low=info.get("fiftyTwoWeekLow"),
            return_on_equity=info.get("returnOnEquity"),
            profit_margins=info.get("profitMargins"),
        )

    @staticmethod
    def _fetch_info(symbol: str) -> dict[str, Any]:
        return yf.Ticker(symbol).info
