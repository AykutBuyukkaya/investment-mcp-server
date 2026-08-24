from __future__ import annotations

import asyncio

from investment_mcp_server.models import StockFundamentals
from investment_mcp_server.tools.stock_fundamentals import execute_get_stock_fundamentals


class FakeFundamentalsClient:
    def __init__(self, fundamentals: StockFundamentals | None = None, error: Exception | None = None):
        self.fundamentals = fundamentals
        self.error = error
        self.calls: list[str] = []

    async def get_fundamentals(self, symbol: str) -> StockFundamentals:
        self.calls.append(symbol)
        if self.error is not None:
            raise self.error
        assert self.fundamentals is not None
        return self.fundamentals


def _sample_fundamentals() -> StockFundamentals:
    return StockFundamentals(
        symbol="THYAO.IS",
        short_name="TURK HAVA YOLLARI",
        currency="TRY",
        exchange="IST",
        trailing_pe=4.2,
        forward_pe=3.9,
        trailing_eps=75.1,
        forward_eps=80.9,
    )


def test_execute_get_stock_fundamentals_success() -> None:
    client = FakeFundamentalsClient(fundamentals=_sample_fundamentals())

    result = asyncio.run(execute_get_stock_fundamentals(client, ticker="thyao"))

    assert result["ok"] is True
    assert result["error"] is None
    assert result["data"]["normalized_ticker"] == "THYAO.IS"
    assert result["data"]["source"] == "yfinance"
    assert result["data"]["fundamentals"]["trailingPE"] == 4.2
    assert result["data"]["fundamentals"]["trailingEps"] == 75.1
    assert client.calls == ["THYAO.IS"]


def test_execute_get_stock_fundamentals_invalid_ticker() -> None:
    client = FakeFundamentalsClient(fundamentals=_sample_fundamentals())

    result = asyncio.run(execute_get_stock_fundamentals(client, ticker="THYAO.US"))

    assert result["ok"] is False
    assert result["data"] is None
    assert result["error"]["code"] == "INVALID_TICKER"
    assert client.calls == []


def test_execute_get_stock_fundamentals_propagates_client_error() -> None:
    from investment_mcp_server.errors import TickerNotFoundError

    client = FakeFundamentalsClient(error=TickerNotFoundError("No fundamentals data found"))

    result = asyncio.run(execute_get_stock_fundamentals(client, ticker="NOPE"))

    assert result["ok"] is False
    assert result["error"]["code"] == "TICKER_NOT_FOUND"
