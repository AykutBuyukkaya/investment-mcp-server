from __future__ import annotations

import asyncio

from investment_mcp_server.tools.stock_quote_metadata import execute_get_stock_quote_metadata


class FakeStockClient:
    def __init__(self, payload: dict):
        self.payload = payload
        self.calls: list[dict] = []

    async def fetch_chart(
        self,
        ticker: str,
        period1: int,
        period2: int,
        interval: str,
        include_prepost: bool | None = None,
    ) -> dict:
        self.calls.append(
            {
                "ticker": ticker,
                "period1": period1,
                "period2": period2,
                "interval": interval,
                "include_prepost": include_prepost,
            }
        )
        return self.payload


def _success_payload() -> dict:
    return {
        "chart": {
            "result": [
                {
                    "meta": {
                        "currency": "TRY",
                        "symbol": "THYAO.IS",
                        "exchangeName": "IST",
                        "regularMarketPrice": 315.5,
                        "fiftyTwoWeekHigh": 355.0,
                        "fiftyTwoWeekLow": 210.0,
                        "regularMarketVolume": 123456,
                        "previousClose": 312.1,
                        "timezone": "Europe/Istanbul",
                        "dataGranularity": "1d",
                    }
                }
            ],
            "error": None,
        }
    }


def test_execute_get_stock_quote_metadata_success() -> None:
    client = FakeStockClient(_success_payload())

    result = asyncio.run(
        execute_get_stock_quote_metadata(
            client,
            ticker="thyao",
            include_prepost=False,
        )
    )

    assert result["ok"] is True
    assert result["error"] is None
    assert result["data"]["normalized_ticker"] == "THYAO.IS"
    assert result["data"]["meta"]["symbol"] == "THYAO.IS"
    assert client.calls[0]["interval"] == "1d"


def test_execute_get_stock_quote_metadata_current_price_success() -> None:
    client = FakeStockClient(_success_payload())

    result = asyncio.run(
        execute_get_stock_quote_metadata(
            client,
            ticker="thyao",
            include_prepost=False,
            current_price=True,
        )
    )

    assert result["ok"] is True
    assert result["data"]["normalized_ticker"] == "THYAO.IS"
    assert result["data"]["source"] == "yahoo_finance"
    assert result["data"]["current_price"] == 315.5
    assert result["data"]["currency"] == "TRY"
    assert result["data"]["meta"]["symbol"] == "THYAO.IS"


def test_execute_get_stock_quote_metadata_invalid_ticker() -> None:
    client = FakeStockClient(_success_payload())

    result = asyncio.run(
        execute_get_stock_quote_metadata(
            client,
            ticker="THYAO.US",
            include_prepost=False,
        )
    )

    assert result["ok"] is False
    assert result["data"] is None
    assert result["error"]["code"] == "INVALID_TICKER"
