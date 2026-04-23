from __future__ import annotations

import pytest

from investment_mcp_server.errors import DataAlignmentError, InvalidIntervalError, NoDataError
from investment_mcp_server.parsers import (
    normalize_interval,
    parse_market_session_info,
    parse_ohlcv_bars,
    parse_quote_meta,
)


def _base_payload() -> dict:
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
                        "currentTradingPeriod": {
                            "pre": {
                                "timezone": "Europe/Istanbul",
                                "start": 1700000000,
                                "end": 1700003600,
                                "gmtoffset": 10800,
                            },
                            "regular": {
                                "timezone": "Europe/Istanbul",
                                "start": 1700003600,
                                "end": 1700020000,
                                "gmtoffset": 10800,
                            },
                            "post": {
                                "timezone": "Europe/Istanbul",
                                "start": 1700020000,
                                "end": 1700023600,
                                "gmtoffset": 10800,
                            },
                        },
                        "tradingPeriods": [
                            [
                                {
                                    "timezone": "Europe/Istanbul",
                                    "start": 1700003600,
                                    "end": 1700020000,
                                    "gmtoffset": 10800,
                                }
                            ]
                        ],
                    },
                    "timestamp": [1700003600, 1700090000, 1700176400],
                    "indicators": {
                        "quote": [
                            {
                                "open": [100.0, None, 102.0],
                                "high": [101.0, 102.0, 103.0],
                                "low": [99.0, 100.5, 101.5],
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


def test_parse_quote_meta_success() -> None:
    meta = parse_quote_meta(_base_payload())
    payload = meta.to_dict()

    assert payload["symbol"] == "THYAO.IS"
    assert payload["currency"] == "TRY"
    assert payload["exchangeName"] == "IST"


def test_parse_ohlcv_strict_alignment_raises() -> None:
    raw = _base_payload()
    raw["chart"]["result"][0]["indicators"]["quote"][0]["close"] = [100.0, 101.0]

    with pytest.raises(DataAlignmentError):
        parse_ohlcv_bars(raw, strict_alignment=True)


def test_parse_ohlcv_null_filtering() -> None:
    bars, dropped = parse_ohlcv_bars(
        _base_payload(),
        include_null_bars=False,
        strict_alignment=True,
    )

    assert len(bars) == 2
    assert dropped == 1
    assert bars[0].timestamp == 1700003600
    assert bars[1].timestamp == 1700176400


def test_parse_market_session_info_extracts_boundaries() -> None:
    session_info = parse_market_session_info(_base_payload())
    payload = session_info.to_dict()

    assert payload["timezone"] == "Europe/Istanbul"
    assert payload["currentTradingPeriod"]["regular"]["start"] == 1700003600
    assert payload["tradingPeriods"][0][0]["end"] == 1700020000


def test_parse_empty_result_raises_no_data() -> None:
    raw = {"chart": {"result": [], "error": None}}

    with pytest.raises(NoDataError):
        parse_quote_meta(raw)


def test_normalize_interval_canonical_values() -> None:
    assert normalize_interval("1wk") == "1wk"
    assert normalize_interval(" 1WK ") == "1wk"


def test_normalize_interval_invalid_value() -> None:
    with pytest.raises(InvalidIntervalError):
        normalize_interval("10m")

    with pytest.raises(InvalidIntervalError):
        normalize_interval("1w")
