"""Parsing helpers for Yahoo Finance chart responses."""

from __future__ import annotations

import re
from typing import Any

from investment_mcp_server.errors import (
    DataAlignmentError,
    InvalidIntervalError,
    InvalidTickerError,
    NoDataError,
)
from investment_mcp_server.models import Candle, MarketSessionInfo, QuoteMeta, SessionPeriod


TICKER_BASE_PATTERN = re.compile(r"^[A-Z0-9]{1,10}$")
CURRENCY_CODE_PATTERN = re.compile(r"^[A-Z]{3}$")
CURRENCY_PAIR_PATTERN = re.compile(r"^([A-Z]{3})/?([A-Z]{3})$")
CURRENCY_YAHOO_SYMBOL_PATTERN = re.compile(r"^([A-Z]{3}|[A-Z]{6})=X$")
VALID_INTERVALS = (
    "1m",
    "2m",
    "5m",
    "15m",
    "30m",
    "60m",
    "90m",
    "1h",
    "4h",
    "1d",
    "5d",
    "1wk",
    "1mo",
    "3mo",
)
VALID_INTERVAL_SET = set(VALID_INTERVALS)


def normalize_ticker(ticker: str) -> str:
    """Normalize a BIST ticker and enforce `.IS` suffix."""
    if not isinstance(ticker, str):
        raise InvalidTickerError("Ticker must be a string")

    cleaned = ticker.strip().upper()
    if not cleaned:
        raise InvalidTickerError("Ticker cannot be empty")

    if cleaned.endswith(".IS"):
        base = cleaned[:-3]
    else:
        if "." in cleaned:
            raise InvalidTickerError("Only BIST tickers with optional '.IS' suffix are supported")
        base = cleaned

    if not base:
        raise InvalidTickerError("Ticker base symbol cannot be empty")

    if not TICKER_BASE_PATTERN.fullmatch(base):
        raise InvalidTickerError(
            "Ticker must contain only alphanumeric characters and be 1-10 chars long"
        )

    return f"{base}.IS"


def normalize_currency_pair(pair: str) -> tuple[str, str, str]:
    """Normalize a currency pair and return (base, quote, Yahoo chart symbol)."""
    if not isinstance(pair, str):
        raise InvalidTickerError("Currency pair must be a string")

    cleaned = pair.strip().upper().replace("-", "/")
    if not cleaned:
        raise InvalidTickerError("Currency pair cannot be empty")

    yahoo_match = CURRENCY_YAHOO_SYMBOL_PATTERN.fullmatch(cleaned)
    if yahoo_match:
        symbol_base = yahoo_match.group(1)
        if len(symbol_base) == 3:
            base_currency = "USD"
            quote_currency = symbol_base
        else:
            base_currency = symbol_base[:3]
            quote_currency = symbol_base[3:]
        if base_currency == quote_currency:
            raise InvalidTickerError("Currency pair base and quote must differ")
        return base_currency, quote_currency, cleaned

    pair_match = CURRENCY_PAIR_PATTERN.fullmatch(cleaned)
    if pair_match is None:
        raise InvalidTickerError(
            "Currency pair must be like USD/TRY, USDTRY, or a Yahoo symbol like TRY=X"
        )

    base_currency = pair_match.group(1)
    quote_currency = pair_match.group(2)
    if not CURRENCY_CODE_PATTERN.fullmatch(base_currency) or not CURRENCY_CODE_PATTERN.fullmatch(
        quote_currency
    ):
        raise InvalidTickerError("Currency codes must be 3 uppercase ASCII letters")
    if base_currency == quote_currency:
        raise InvalidTickerError("Currency pair base and quote must differ")

    yahoo_symbol = (
        f"{quote_currency}=X" if base_currency == "USD" else f"{base_currency}{quote_currency}=X"
    )
    return base_currency, quote_currency, yahoo_symbol


def normalize_interval(interval: str) -> str:
    """Normalize and validate Yahoo chart interval values."""
    if not isinstance(interval, str):
        raise InvalidIntervalError("interval must be a string")

    cleaned = interval.strip().lower()
    if not cleaned:
        raise InvalidIntervalError("interval must be a non-empty string")

    if cleaned not in VALID_INTERVAL_SET:
        allowed = ", ".join(VALID_INTERVALS)
        raise InvalidIntervalError(
            f"Unsupported interval '{interval}'. Valid intervals: [{allowed}]"
        )

    return cleaned


def _extract_result_payload(raw: dict[str, Any]) -> dict[str, Any]:
    chart = raw.get("chart")
    if not isinstance(chart, dict):
        raise NoDataError("Missing 'chart' object in Yahoo response")

    result = chart.get("result")
    if not isinstance(result, list) or not result or not isinstance(result[0], dict):
        raise NoDataError("Yahoo response does not include chart.result[0]")

    return result[0]


def parse_quote_meta(raw: dict[str, Any]) -> QuoteMeta:
    result_payload = _extract_result_payload(raw)
    meta = result_payload.get("meta")
    if not isinstance(meta, dict):
        raise NoDataError("Yahoo response missing result[0].meta")

    return QuoteMeta(
        currency=meta.get("currency"),
        symbol=meta.get("symbol"),
        exchange_name=meta.get("exchangeName"),
        regular_market_price=meta.get("regularMarketPrice"),
        fifty_two_week_high=meta.get("fiftyTwoWeekHigh"),
        fifty_two_week_low=meta.get("fiftyTwoWeekLow"),
        regular_market_volume=meta.get("regularMarketVolume"),
        previous_close=meta.get("previousClose"),
        timezone=meta.get("timezone"),
        data_granularity=meta.get("dataGranularity"),
    )


def parse_ohlcv_bars(
    raw: dict[str, Any],
    *,
    include_null_bars: bool = False,
    strict_alignment: bool = True,
) -> tuple[list[Candle], int]:
    result_payload = _extract_result_payload(raw)

    timestamps = result_payload.get("timestamp")
    if not isinstance(timestamps, list) or not timestamps:
        raise NoDataError("Yahoo response missing non-empty timestamp array")

    indicators = result_payload.get("indicators")
    if not isinstance(indicators, dict):
        raise NoDataError("Yahoo response missing indicators object")

    quote_list = indicators.get("quote")
    if not isinstance(quote_list, list) or not quote_list or not isinstance(quote_list[0], dict):
        raise NoDataError("Yahoo response missing indicators.quote[0]")

    quote = quote_list[0]
    open_series = quote.get("open")
    high_series = quote.get("high")
    low_series = quote.get("low")
    close_series = quote.get("close")
    volume_series = quote.get("volume")

    required_series = {
        "timestamp": timestamps,
        "open": open_series,
        "high": high_series,
        "low": low_series,
        "close": close_series,
        "volume": volume_series,
    }

    if any(not isinstance(series, list) for series in required_series.values()):
        raise NoDataError("One or more OHLCV arrays are missing in indicators.quote[0]")

    lengths = {name: len(series) for name, series in required_series.items()}
    min_len = min(lengths.values())
    max_len = max(lengths.values())
    if min_len == 0:
        raise NoDataError("Yahoo response contains empty OHLCV/timestamp arrays")

    if strict_alignment and min_len != max_len:
        raise DataAlignmentError(
            "OHLCV arrays are not aligned with timestamp array",
            details={"lengths": lengths},
        )

    bars: list[Candle] = []
    dropped_null_bar_count = 0
    for idx in range(min_len):
        candle = Candle(
            timestamp=timestamps[idx],
            open=open_series[idx],
            high=high_series[idx],
            low=low_series[idx],
            close=close_series[idx],
            volume=volume_series[idx],
        )

        has_null_value = any(
            value is None
            for value in (
                candle.open,
                candle.high,
                candle.low,
                candle.close,
                candle.volume,
            )
        )
        if has_null_value and not include_null_bars:
            dropped_null_bar_count += 1
            continue

        bars.append(candle)

    return bars, dropped_null_bar_count


def _parse_session_period(raw_period: Any) -> SessionPeriod | None:
    if not isinstance(raw_period, dict):
        return None
    return SessionPeriod(
        timezone=raw_period.get("timezone"),
        start=raw_period.get("start"),
        end=raw_period.get("end"),
        gmtoffset=raw_period.get("gmtoffset"),
    )


def parse_market_session_info(raw: dict[str, Any]) -> MarketSessionInfo:
    result_payload = _extract_result_payload(raw)
    meta = result_payload.get("meta")
    if not isinstance(meta, dict):
        raise NoDataError("Yahoo response missing result[0].meta")

    current_raw = meta.get("currentTradingPeriod")
    current_raw = current_raw if isinstance(current_raw, dict) else {}
    current = {
        "pre": _parse_session_period(current_raw.get("pre")),
        "regular": _parse_session_period(current_raw.get("regular")),
        "post": _parse_session_period(current_raw.get("post")),
    }

    trading_periods_raw = meta.get("tradingPeriods")
    trading_periods: list[list[SessionPeriod]] | None = None
    if isinstance(trading_periods_raw, list):
        trading_periods = []
        if trading_periods_raw and all(isinstance(item, dict) for item in trading_periods_raw):
            parsed_day = [
                parsed
                for parsed in (_parse_session_period(item) for item in trading_periods_raw)
                if parsed is not None
            ]
            trading_periods.append(parsed_day)
        else:
            for day in trading_periods_raw:
                if not isinstance(day, list):
                    continue
                parsed_day = [
                    parsed
                    for parsed in (_parse_session_period(item) for item in day)
                    if parsed is not None
                ]
                trading_periods.append(parsed_day)

    return MarketSessionInfo(
        timezone=meta.get("timezone"),
        current_trading_period=current,
        trading_periods=trading_periods,
    )
