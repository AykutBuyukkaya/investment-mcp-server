from __future__ import annotations

import asyncio

import pytest

from investment_mcp_server import fundamentals_client as fundamentals_client_module
from investment_mcp_server.errors import (
    NoDataError,
    RateLimitedError,
    TickerNotFoundError,
    UpstreamUnavailableError,
)
from investment_mcp_server.fundamentals_client import YFinanceFundamentalsClient


class FakeTicker:
    def __init__(self, info: dict | None = None, error: Exception | None = None):
        self._info = info
        self._error = error

    @property
    def info(self) -> dict:
        if self._error is not None:
            raise self._error
        assert self._info is not None
        return self._info


def _patch_ticker(monkeypatch: pytest.MonkeyPatch, ticker: FakeTicker) -> None:
    monkeypatch.setattr(fundamentals_client_module.yf, "Ticker", lambda symbol: ticker)


def test_get_fundamentals_success(monkeypatch: pytest.MonkeyPatch) -> None:
    _patch_ticker(
        monkeypatch,
        FakeTicker(
            {
                "symbol": "THYAO.IS",
                "shortName": "TURK HAVA YOLLARI",
                "currency": "TRY",
                "exchange": "IST",
                "sector": "Industrials",
                "industry": "Airlines",
                "regularMarketPrice": 315.5,
                "marketCap": 450000000000,
                "trailingPE": 4.2,
                "forwardPE": 3.9,
                "trailingEps": 75.1,
                "forwardEps": 80.9,
                "priceToBook": 1.1,
                "bookValue": 286.8,
                "dividendYield": 0.02,
                "beta": 1.3,
                "fiftyTwoWeekHigh": 355.0,
                "fiftyTwoWeekLow": 210.0,
                "returnOnEquity": 0.28,
                "profitMargins": 0.12,
            }
        ),
    )

    client = YFinanceFundamentalsClient()
    result = asyncio.run(client.get_fundamentals("THYAO.IS"))

    assert result.symbol == "THYAO.IS"
    assert result.trailing_pe == 4.2
    assert result.forward_pe == 3.9
    assert result.trailing_eps == 75.1
    assert result.forward_eps == 80.9
    assert result.currency == "TRY"


def test_get_fundamentals_missing_ticker_raises_not_found(monkeypatch: pytest.MonkeyPatch) -> None:
    _patch_ticker(monkeypatch, FakeTicker({"trailingPegRatio": None}))

    client = YFinanceFundamentalsClient()
    with pytest.raises(TickerNotFoundError):
        asyncio.run(client.get_fundamentals("BADTICKER.IS"))


def test_get_fundamentals_empty_info_raises_no_data(monkeypatch: pytest.MonkeyPatch) -> None:
    _patch_ticker(monkeypatch, FakeTicker({}))

    client = YFinanceFundamentalsClient()
    with pytest.raises(NoDataError):
        asyncio.run(client.get_fundamentals("EMPTY.IS"))


def test_get_fundamentals_rate_limited_error(monkeypatch: pytest.MonkeyPatch) -> None:
    _patch_ticker(monkeypatch, FakeTicker(error=RuntimeError("HTTP Error 429: Too Many Requests")))

    client = YFinanceFundamentalsClient()
    with pytest.raises(RateLimitedError):
        asyncio.run(client.get_fundamentals("THYAO.IS"))


def test_get_fundamentals_generic_error_raises_upstream_unavailable(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _patch_ticker(monkeypatch, FakeTicker(error=RuntimeError("connection reset")))

    client = YFinanceFundamentalsClient()
    with pytest.raises(UpstreamUnavailableError):
        asyncio.run(client.get_fundamentals("THYAO.IS"))
