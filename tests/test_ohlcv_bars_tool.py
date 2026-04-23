from __future__ import annotations

import asyncio
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

from investment_mcp_server.tools.ohlcv_bars import execute_get_ohlcv_bars


IST = ZoneInfo("Europe/Istanbul")


def _fmt_ist(dt: datetime) -> str:
    return dt.astimezone(IST).strftime("%d.%m.%Y %H.%M")


class FakeYahooClient:
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


def _payload_with_bars() -> dict:
    return {
        "chart": {
            "result": [
                {
                    "meta": {
                        "timezone": "Europe/Istanbul",
                        "symbol": "THYAO.IS",
                    },
                    "timestamp": [1700000000, 1700003600, 1700007200],
                    "indicators": {
                        "quote": [
                            {
                                "open": [100.0, None, 102.0],
                                "high": [101.0, 102.0, 103.0],
                                "low": [99.0, 100.0, 101.0],
                                "close": [100.5, 101.5, 102.5],
                                "volume": [1000, 1100, 1200],
                            }
                        ]
                    },
                }
            ],
            "error": None,
        }
    }


def test_execute_get_ohlcv_bars_success_and_limit() -> None:
    client = FakeYahooClient(_payload_with_bars())
    now = datetime.now(IST)
    start = _fmt_ist(now - timedelta(days=2))
    end = _fmt_ist(now - timedelta(days=1, hours=20))

    result = asyncio.run(
        execute_get_ohlcv_bars(
            client,
            ticker="thyao",
            start=start,
            end=end,
            interval="1h",
            include_prepost=False,
            include_null_bars=False,
            strict_alignment=True,
            limit=1,
        )
    )

    assert result["ok"] is True
    assert result["error"] is None
    assert result["data"]["normalized_ticker"] == "THYAO.IS"
    assert result["data"]["interval"] == "1h"
    assert result["data"]["timezone"] == "Europe/Istanbul"
    assert len(result["data"]["bars"]) == 1
    assert result["data"]["bars"][0]["timestamp"] == 1700007200
    assert result["data"]["dropped_null_bar_count"] == 1
    assert client.calls[0]["ticker"] == "THYAO.IS"
    assert client.calls[0]["period2"] - client.calls[0]["period1"] == 4 * 60 * 60


def test_execute_get_ohlcv_bars_invalid_time_range() -> None:
    client = FakeYahooClient(_payload_with_bars())

    result = asyncio.run(
        execute_get_ohlcv_bars(
            client,
            ticker="THYAO",
            start="15.11.2023 10.00",
            end="15.11.2023 10.00",
            interval="1h",
        )
    )

    assert result["ok"] is False
    assert result["error"]["code"] == "INVALID_TIME_RANGE"


def test_execute_get_ohlcv_bars_include_null_bars() -> None:
    client = FakeYahooClient(_payload_with_bars())
    now = datetime.now(IST)
    start = _fmt_ist(now - timedelta(days=2))
    end = _fmt_ist(now - timedelta(days=1, hours=20))

    result = asyncio.run(
        execute_get_ohlcv_bars(
            client,
            ticker="THYAO",
            start=start,
            end=end,
            interval="1h",
            include_null_bars=True,
        )
    )

    assert result["ok"] is True
    assert len(result["data"]["bars"]) == 3
    assert result["data"]["dropped_null_bar_count"] == 0


def test_execute_get_ohlcv_bars_invalid_interval() -> None:
    client = FakeYahooClient(_payload_with_bars())

    result = asyncio.run(
        execute_get_ohlcv_bars(
            client,
            ticker="THYAO",
            start="14.11.2023 23.13",
            end="15.11.2023 02.00",
            interval="1WEEK",
        )
    )

    assert result["ok"] is False
    assert result["error"]["code"] == "INVALID_INTERVAL"


def test_execute_get_ohlcv_bars_daily_interval_not_limited_to_60_days() -> None:
    client = FakeYahooClient(_payload_with_bars())
    now = datetime.now(IST)
    start = _fmt_ist(now - timedelta(days=120))
    end = _fmt_ist(now - timedelta(days=100))

    result = asyncio.run(
        execute_get_ohlcv_bars(
            client,
            ticker="THYAO",
            start=start,
            end=end,
            interval="1d",
        )
    )

    assert result["ok"] is True
