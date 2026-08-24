from __future__ import annotations

import asyncio
from typing import Any

from investment_mcp_server.errors import TickerNotFoundError
from investment_mcp_server.models import StockFundamentals
from investment_mcp_server.tools.screen_bist_stocks import execute_screen_bist_stocks


def _chart_payload(*, open_price: float, close_price: float) -> dict[str, Any]:
    return {
        "chart": {
            "result": [
                {
                    "meta": {"currency": "TRY", "symbol": "X"},
                    "timestamp": [1_700_000_000, 1_700_100_000],
                    "indicators": {
                        "quote": [
                            {
                                "open": [open_price, open_price],
                                "high": [open_price, close_price],
                                "low": [open_price, close_price],
                                "close": [open_price, close_price],
                                "volume": [1000, 1200],
                            }
                        ]
                    },
                }
            ],
            "error": None,
        }
    }


class FakeStockClient:
    def __init__(self, prices: dict[str, tuple[float, float]]):
        self._prices = prices
        self.calls: list[str] = []

    async def fetch_chart(
        self,
        ticker: str,
        period1: int,
        period2: int,
        interval: str,
        include_prepost: bool | None = None,
    ) -> dict[str, Any]:
        self.calls.append(ticker)
        if ticker not in self._prices:
            return {"chart": {"result": None, "error": {"description": "No data found"}}}
        open_price, close_price = self._prices[ticker]
        return _chart_payload(open_price=open_price, close_price=close_price)


class FakeFundamentalsClient:
    def __init__(self, fundamentals: dict[str, StockFundamentals], errors: dict[str, Exception] | None = None):
        self._fundamentals = fundamentals
        self._errors = errors or {}
        self.calls: list[str] = []

    async def get_fundamentals(self, symbol: str) -> StockFundamentals:
        self.calls.append(symbol)
        if symbol in self._errors:
            raise self._errors[symbol]
        return self._fundamentals[symbol]


def _fund(symbol: str, *, trailing_pe: float | None, forward_pe: float | None = None) -> StockFundamentals:
    return StockFundamentals(
        symbol=symbol,
        short_name=symbol,
        currency="TRY",
        trailing_pe=trailing_pe,
        forward_pe=forward_pe if forward_pe is not None else trailing_pe,
        trailing_eps=1.0,
        forward_eps=1.1,
    )


def test_screen_ranks_highest_return_and_lowest_pe_first() -> None:
    stock_client = FakeStockClient(
        {
            "AAA.IS": (100.0, 120.0),  # +20% return
            "BBB.IS": (100.0, 130.0),  # +30% return
            "CCC.IS": (100.0, 105.0),  # +5% return
        }
    )
    fundamentals_client = FakeFundamentalsClient(
        {
            "AAA.IS": _fund("AAA.IS", trailing_pe=5.0),
            "BBB.IS": _fund("BBB.IS", trailing_pe=15.0),
            "CCC.IS": _fund("CCC.IS", trailing_pe=3.0),
        }
    )

    result = asyncio.run(
        execute_screen_bist_stocks(
            stock_client,
            fundamentals_client,
            tickers=["aaa", "bbb", "ccc"],
            preset="1mo",
        )
    )

    assert result["ok"] is True
    assert result["data"]["universe_source"] == "custom"
    assert result["data"]["screened_count"] == 3
    tickers_in_order = [r["ticker"] for r in result["data"]["results"]]
    assert tickers_in_order[0] == "AAA.IS"  # best blend: high return (2nd) + lowest-ish PE (2nd)
    assert result["data"]["excluded_count"] == 0


def test_screen_sort_by_pe_only() -> None:
    stock_client = FakeStockClient(
        {
            "AAA.IS": (100.0, 120.0),
            "BBB.IS": (100.0, 130.0),
        }
    )
    fundamentals_client = FakeFundamentalsClient(
        {
            "AAA.IS": _fund("AAA.IS", trailing_pe=5.0),
            "BBB.IS": _fund("BBB.IS", trailing_pe=2.0),
        }
    )

    result = asyncio.run(
        execute_screen_bist_stocks(
            stock_client,
            fundamentals_client,
            tickers=["AAA", "BBB"],
            preset="1mo",
            sort_by="pe",
        )
    )

    assert result["ok"] is True
    assert [r["ticker"] for r in result["data"]["results"]] == ["BBB.IS", "AAA.IS"]


def test_screen_excludes_negative_pe_and_max_pe_filter() -> None:
    stock_client = FakeStockClient(
        {
            "AAA.IS": (100.0, 120.0),
            "BBB.IS": (100.0, 130.0),
            "CCC.IS": (100.0, 110.0),
        }
    )
    fundamentals_client = FakeFundamentalsClient(
        {
            "AAA.IS": _fund("AAA.IS", trailing_pe=-6.5),  # loss-making, excluded
            "BBB.IS": _fund("BBB.IS", trailing_pe=50.0),  # excluded by max_pe
            "CCC.IS": _fund("CCC.IS", trailing_pe=8.0),
        }
    )

    result = asyncio.run(
        execute_screen_bist_stocks(
            stock_client,
            fundamentals_client,
            tickers=["AAA", "BBB", "CCC"],
            preset="1mo",
            max_pe=20.0,
        )
    )

    assert result["ok"] is True
    assert [r["ticker"] for r in result["data"]["results"]] == ["CCC.IS"]
    assert result["data"]["excluded_count"] == 2
    reasons = {e["ticker"]: e["reason"] for e in result["data"]["excluded"]}
    assert "AAA.IS" in reasons
    assert "BBB.IS" in reasons


def test_screen_isolates_per_ticker_failures() -> None:
    stock_client = FakeStockClient({"AAA.IS": (100.0, 120.0)})  # BBB.IS missing -> NoData
    fundamentals_client = FakeFundamentalsClient(
        {"AAA.IS": _fund("AAA.IS", trailing_pe=5.0)},
        errors={"BBB.IS": TickerNotFoundError("no fundamentals")},
    )

    result = asyncio.run(
        execute_screen_bist_stocks(
            stock_client,
            fundamentals_client,
            tickers=["AAA", "BBB"],
            preset="1mo",
        )
    )

    assert result["ok"] is True
    assert result["data"]["result_count"] == 1
    assert result["data"]["results"][0]["ticker"] == "AAA.IS"
    assert result["data"]["excluded_count"] == 1
    assert result["data"]["excluded"][0]["ticker"] == "BBB.IS"


def test_screen_uses_financials_sector_default_when_no_tickers_given() -> None:
    from investment_mcp_server.bist_sectors import BIST_FINANCIALS_TICKERS

    stock_client = FakeStockClient({})
    fundamentals_client = FakeFundamentalsClient({}, errors={})

    result = asyncio.run(
        execute_screen_bist_stocks(
            stock_client,
            fundamentals_client,
            preset="1mo",
        )
    )

    assert result["ok"] is True
    assert result["data"]["universe_source"] == "sector_preset"
    assert result["data"]["sector"] == "financials"
    assert result["data"]["screened_count"] == len(BIST_FINANCIALS_TICKERS)


def test_screen_supports_non_financials_sector_presets() -> None:
    from investment_mcp_server.bist_sectors import BIST_SECTOR_TICKERS

    stock_client = FakeStockClient({})
    fundamentals_client = FakeFundamentalsClient({}, errors={})

    for sector_name in ("industrials", "technology", "energy_utilities", "real_estate"):
        result = asyncio.run(
            execute_screen_bist_stocks(
                stock_client,
                fundamentals_client,
                sector=sector_name,
                preset="1mo",
            )
        )
        assert result["ok"] is True
        assert result["data"]["sector"] == sector_name
        assert result["data"]["screened_count"] == len(BIST_SECTOR_TICKERS[sector_name])


def test_screen_rejects_unsupported_sector() -> None:
    stock_client = FakeStockClient({})
    fundamentals_client = FakeFundamentalsClient({})

    result = asyncio.run(
        execute_screen_bist_stocks(
            stock_client,
            fundamentals_client,
            sector="energy",
        )
    )

    assert result["ok"] is False
    assert result["error"]["code"] == "INVALID_INPUT"


def test_screen_rejects_too_many_tickers() -> None:
    stock_client = FakeStockClient({})
    fundamentals_client = FakeFundamentalsClient({})

    result = asyncio.run(
        execute_screen_bist_stocks(
            stock_client,
            fundamentals_client,
            tickers=[f"T{i}" for i in range(60)],
        )
    )

    assert result["ok"] is False
    assert result["error"]["code"] == "INVALID_INPUT"


def test_screen_rejects_invalid_sort_by() -> None:
    stock_client = FakeStockClient({})
    fundamentals_client = FakeFundamentalsClient({})

    result = asyncio.run(
        execute_screen_bist_stocks(
            stock_client,
            fundamentals_client,
            tickers=["AAA"],
            sort_by="bogus",
        )
    )

    assert result["ok"] is False
    assert result["error"]["code"] == "INVALID_INPUT"
