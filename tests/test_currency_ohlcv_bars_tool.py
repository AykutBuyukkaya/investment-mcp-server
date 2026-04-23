from __future__ import annotations

import asyncio
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

from investment_mcp_server.tools.currency_ohlcv_bars import execute_get_currency_ohlcv_bars


IST = ZoneInfo("Europe/Istanbul")


def _fmt_ist(dt: datetime) -> str:
    return dt.astimezone(IST).strftime("%d.%m.%Y %H.%M")


class FakeCurrencyClient:
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


def _payload_with_bars(symbol: str = "TRY=X") -> dict:
    return {
        "chart": {
            "result": [
                {
                    "meta": {
                        "currency": "TRY",
                        "symbol": symbol,
                        "exchangeName": "CCY",
                        "regularMarketPrice": 40.755,
                        "previousClose": 40.701,
                        "timezone": "Europe/London",
                        "dataGranularity": "1m",
                    },
                    "timestamp": [1776772800, 1776772860, 1776772920],
                    "indicators": {
                        "quote": [
                            {
                                "open": [40.701, None, 40.703],
                                "high": [40.702, 40.704, 40.706],
                                "low": [40.700, 40.701, 40.702],
                                "close": [40.7015, 40.703, 40.705],
                                "volume": [0, 0, 0],
                            }
                        ]
                    },
                }
            ],
            "error": None,
        }
    }


def test_execute_get_currency_ohlcv_bars_usd_try_success_and_limit() -> None:
    client = FakeCurrencyClient(_payload_with_bars())
    now = datetime.now(IST)
    start = _fmt_ist(now - timedelta(days=2))
    end = _fmt_ist(now - timedelta(days=1, hours=20))

    result = asyncio.run(
        execute_get_currency_ohlcv_bars(
            client,
            pair="USD/TRY",
            start=start,
            end=end,
            interval="1m",
            include_prepost=True,
            include_null_bars=False,
            strict_alignment=True,
            limit=1,
        )
    )

    assert result["ok"] is True
    assert result["error"] is None
    assert result["data"]["pair"] == "USD/TRY"
    assert result["data"]["base_currency"] == "USD"
    assert result["data"]["quote_currency"] == "TRY"
    assert result["data"]["yahoo_symbol"] == "TRY=X"
    assert result["data"]["interval"] == "1m"
    assert result["data"]["timezone"] == "Europe/London"
    assert result["data"]["meta"]["symbol"] == "TRY=X"
    assert len(result["data"]["bars"]) == 1
    assert result["data"]["bars"][0]["timestamp"] == 1776772920
    assert result["data"]["dropped_null_bar_count"] == 1
    assert client.calls[0]["ticker"] == "TRY=X"
    assert client.calls[0]["include_prepost"] is True
    assert client.calls[0]["period2"] - client.calls[0]["period1"] == 4 * 60 * 60


def test_execute_get_currency_ohlcv_bars_eur_try_preset_success() -> None:
    client = FakeCurrencyClient(_payload_with_bars(symbol="EURTRY=X"))

    result = asyncio.run(
        execute_get_currency_ohlcv_bars(
            client,
            pair="EURTRY",
            preset="1w",
            interval="1d",
        )
    )

    assert result["ok"] is True
    assert result["data"]["pair"] == "EUR/TRY"
    assert result["data"]["yahoo_symbol"] == "EURTRY=X"
    assert result["data"]["preset"] == "1w"
    assert result["data"]["interval"] == "1d"
    assert client.calls[0]["ticker"] == "EURTRY=X"
    assert client.calls[0]["include_prepost"] is True
    assert 6 * 24 * 60 * 60 <= client.calls[0]["period2"] - client.calls[0]["period1"]
    assert client.calls[0]["period2"] - client.calls[0]["period1"] <= 8 * 24 * 60 * 60


def test_execute_get_currency_ohlcv_bars_current_price_ignores_range_inputs() -> None:
    client = FakeCurrencyClient(_payload_with_bars())

    result = asyncio.run(
        execute_get_currency_ohlcv_bars(
            client,
            pair="USD/TRY",
            preset="not-used",
            start="15.11.2023 10.00",
            end="15.11.2023 09.00",
            interval="not-used",
            current_price=True,
        )
    )

    assert result["ok"] is True
    assert result["data"]["pair"] == "USD/TRY"
    assert result["data"]["yahoo_symbol"] == "TRY=X"
    assert result["data"]["source"] == "yahoo_finance"
    assert result["data"]["current_price"] == 40.755
    assert result["data"]["currency"] == "TRY"
    assert client.calls[0]["ticker"] == "TRY=X"
    assert client.calls[0]["interval"] == "1m"
    assert client.calls[0]["include_prepost"] is True


def test_execute_get_currency_ohlcv_bars_invalid_pair() -> None:
    client = FakeCurrencyClient(_payload_with_bars())

    result = asyncio.run(
        execute_get_currency_ohlcv_bars(
            client,
            pair="USD/USD",
            preset="1w",
            interval="1d",
        )
    )

    assert result["ok"] is False
    assert result["data"] is None
    assert result["error"]["code"] == "INVALID_TICKER"
    assert client.calls == []


def test_execute_get_currency_ohlcv_bars_rejects_missing_range() -> None:
    client = FakeCurrencyClient(_payload_with_bars())

    result = asyncio.run(
        execute_get_currency_ohlcv_bars(
            client,
            pair="USD/TRY",
            interval="1d",
        )
    )

    assert result["ok"] is False
    assert result["error"]["code"] == "INVALID_INPUT"
    assert client.calls == []
