"""OHLCV bars MCP tool implementation."""

from __future__ import annotations

from datetime import datetime
import time
from typing import Any, Protocol
from zoneinfo import ZoneInfo

from investment_mcp_server.errors import (
    InputError,
    InvalidTimeRangeError,
    NoDataError,
    TickerNotFoundError,
    map_exception_to_error_payload,
)
from investment_mcp_server.parsers import normalize_interval, normalize_ticker, parse_ohlcv_bars
from investment_mcp_server.parsers import parse_quote_meta


DATE_INPUT_FORMAT = "%d.%m.%Y %H.%M"
MARKET_TIMEZONE = ZoneInfo("Europe/Istanbul")
INTRADAY_INTERVALS = {"1m", "2m", "5m", "15m", "30m", "60m", "90m", "1h", "4h"}
INTRADAY_MAX_AGE_SECONDS = 60 * 24 * 60 * 60


class YahooChartClient(Protocol):
    async def fetch_chart(
        self,
        ticker: str,
        period1: int,
        period2: int,
        interval: str,
        include_prepost: bool | None = None,
    ) -> dict[str, Any]: ...


def _raise_if_chart_error(raw: dict[str, Any]) -> None:
    chart = raw.get("chart")
    if not isinstance(chart, dict):
        return

    chart_error = chart.get("error")
    if not isinstance(chart_error, dict):
        return

    description = str(chart_error.get("description") or "Upstream chart error")
    lowered = description.lower()
    if "not found" in lowered or "no data" in lowered or "symbol" in lowered:
        raise TickerNotFoundError(description)
    raise NoDataError(description)


def _make_success_response(data: dict[str, Any]) -> dict[str, Any]:
    return {"ok": True, "data": data, "error": None}


def _make_error_response(exc: Exception) -> dict[str, Any]:
    payload = map_exception_to_error_payload(exc)
    return {"ok": False, "data": None, "error": payload.to_dict()}


def _parse_datetime_to_unix(value: str, *, field_name: str) -> int:
    if not isinstance(value, str) or not value.strip():
        raise InputError(f"{field_name} must be a non-empty string in format dd.mm.yyyy hh.MM")

    cleaned = value.strip()
    try:
        parsed = datetime.strptime(cleaned, DATE_INPUT_FORMAT)
    except ValueError as exc:
        raise InputError(
            f"Invalid {field_name} '{value}'. Expected format: dd.mm.yyyy hh.MM"
        ) from exc

    aware = parsed.replace(tzinfo=MARKET_TIMEZONE)
    return int(aware.timestamp())


def _validate_inputs(start_ts: int, end_ts: int, interval: str, limit: int | None) -> None:
    if end_ts <= start_ts:
        raise InvalidTimeRangeError("end must be greater than start")

    if interval in INTRADAY_INTERVALS:
        now_ts = int(time.time())
        cutoff_ts = now_ts - INTRADAY_MAX_AGE_SECONDS
        if start_ts < cutoff_ts or end_ts < cutoff_ts:
            raise InvalidTimeRangeError(
                "For intraday intervals (1m..4h), start and end must be within the last 60 days"
            )

    if limit is not None and limit <= 0:
        raise InputError("limit must be greater than 0 when provided")


async def execute_get_ohlcv_bars(
    yahoo_client: YahooChartClient,
    *,
    ticker: str,
    start: str,
    end: str,
    interval: str,
    include_prepost: bool = False,
    include_null_bars: bool = False,
    strict_alignment: bool = True,
    limit: int | None = None,
) -> dict[str, Any]:
    """Fetch and return parsed OHLCV bars in a standard envelope."""
    try:
        start_ts = _parse_datetime_to_unix(start, field_name="start")
        end_ts = _parse_datetime_to_unix(end, field_name="end")
        normalized_interval = normalize_interval(interval)
        _validate_inputs(start_ts=start_ts, end_ts=end_ts, interval=normalized_interval, limit=limit)
        normalized_ticker = normalize_ticker(ticker)

        raw = await yahoo_client.fetch_chart(
            ticker=normalized_ticker,
            period1=start_ts,
            period2=end_ts,
            interval=normalized_interval,
            include_prepost=include_prepost,
        )
        _raise_if_chart_error(raw)

        bars, dropped_null_bar_count = parse_ohlcv_bars(
            raw,
            include_null_bars=include_null_bars,
            strict_alignment=strict_alignment,
        )

        if limit is not None:
            bars = bars[-limit:]

        quote_meta = parse_quote_meta(raw)
        return _make_success_response(
            {
                "normalized_ticker": normalized_ticker,
                "interval": normalized_interval,
                "timezone": quote_meta.timezone,
                "bars": [bar.to_dict() for bar in bars],
                "dropped_null_bar_count": dropped_null_bar_count,
            }
        )
    except Exception as exc:
        return _make_error_response(exc)
