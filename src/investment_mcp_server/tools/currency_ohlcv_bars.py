"""Foreign currency OHLCV bars MCP tool implementation."""

from __future__ import annotations

from datetime import datetime, timedelta
import time
from typing import Any, Literal, Protocol
from zoneinfo import ZoneInfo

from investment_mcp_server.errors import (
    InputError,
    InvalidTimeRangeError,
    NoDataError,
    TickerNotFoundError,
    map_exception_to_error_payload,
)
from investment_mcp_server.parsers import (
    normalize_currency_pair,
    normalize_interval,
    parse_ohlcv_bars,
    parse_quote_meta,
)


DATE_INPUT_FORMAT = "%d.%m.%Y %H.%M"
MARKET_TIMEZONE = ZoneInfo("Europe/Istanbul")
INTRADAY_INTERVALS = {"1m", "2m", "5m", "15m", "30m", "60m", "90m", "1h", "4h"}
INTRADAY_MAX_AGE_SECONDS = 60 * 24 * 60 * 60
Preset = Literal["1w", "1mo", "3mo", "6mo", "1y", "5y"]
VALID_PRESETS: set[Preset] = {"1w", "1mo", "3mo", "6mo", "1y", "5y"}
PRESET_DAYS: dict[Preset, int] = {
    "1w": 7,
    "1mo": 30,
    "3mo": 90,
    "6mo": 180,
    "1y": 365,
    "5y": 1825,
}


class CurrencyChartClient(Protocol):
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


def _validate_preset(preset: str | None) -> Preset | None:
    if preset is None:
        return None
    if not isinstance(preset, str) or not preset.strip():
        raise InputError("preset must be a non-empty string")
    normalized = preset.strip().lower()
    if normalized not in VALID_PRESETS:
        allowed = ", ".join(sorted(VALID_PRESETS))
        raise InputError(f"Unsupported preset '{preset}'. Valid presets: {allowed}")
    return normalized  # type: ignore[return-value]


def _resolve_datetime_range(
    *,
    preset: Preset | None,
    start: str | None,
    end: str | None,
) -> tuple[str, str, int, int]:
    has_datetime_range = start is not None or end is not None
    if preset is None and not has_datetime_range:
        raise InputError("Provide either a preset or both start and end")
    if preset is not None and has_datetime_range:
        raise InputError("preset cannot be combined with start or end")
    if (start is None) != (end is None):
        raise InputError("start and end must be provided together")

    if preset is not None:
        end_dt = datetime.now(MARKET_TIMEZONE)
        start_dt = end_dt - timedelta(days=PRESET_DAYS[preset])
        start_text = start_dt.strftime(DATE_INPUT_FORMAT)
        end_text = end_dt.strftime(DATE_INPUT_FORMAT)
        return start_text, end_text, int(start_dt.timestamp()), int(end_dt.timestamp())

    assert start is not None
    assert end is not None
    start_ts = _parse_datetime_to_unix(start, field_name="start")
    end_ts = _parse_datetime_to_unix(end, field_name="end")
    return start.strip(), end.strip(), start_ts, end_ts


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


def _latest_close_from_raw(raw: dict[str, Any]) -> tuple[float | None, int | None]:
    try:
        bars, _ = parse_ohlcv_bars(raw, include_null_bars=True, strict_alignment=False)
    except NoDataError:
        return None, None

    for bar in reversed(bars):
        if bar.close is not None:
            return bar.close, bar.timestamp
    return None, None


async def _fetch_current_price(
    currency_client: CurrencyChartClient,
    *,
    base_currency: str,
    quote_currency: str,
    yahoo_symbol: str,
    include_prepost: bool,
) -> dict[str, Any]:
    now_ts = int(time.time())
    raw = await currency_client.fetch_chart(
        ticker=yahoo_symbol,
        period1=now_ts - 5 * 24 * 60 * 60,
        period2=now_ts,
        interval="1m",
        include_prepost=include_prepost,
    )
    _raise_if_chart_error(raw)

    quote_meta = parse_quote_meta(raw)
    fallback_price, fallback_timestamp = _latest_close_from_raw(raw)
    price = (
        quote_meta.regular_market_price
        if quote_meta.regular_market_price is not None
        else fallback_price
    )
    if price is None:
        raise NoDataError(f"No current price returned for {yahoo_symbol}")

    return {
        "pair": f"{base_currency}/{quote_currency}",
        "base_currency": base_currency,
        "quote_currency": quote_currency,
        "yahoo_symbol": yahoo_symbol,
        "source": "yahoo_finance",
        "current_price": price,
        "currency": quote_meta.currency or quote_currency,
        "timestamp": fallback_timestamp,
        "timezone": quote_meta.timezone,
        "meta": quote_meta.to_dict(),
    }


async def execute_get_currency_ohlcv_bars(
    currency_client: CurrencyChartClient,
    *,
    pair: str,
    start: str | None = None,
    end: str | None = None,
    preset: str | None = None,
    interval: str = "1d",
    include_prepost: bool = True,
    include_null_bars: bool = False,
    strict_alignment: bool = True,
    limit: int | None = None,
    current_price: bool = False,
) -> dict[str, Any]:
    """Fetch and return parsed currency OHLCV bars in a standard envelope."""
    try:
        base_currency, quote_currency, yahoo_symbol = normalize_currency_pair(pair)
        if current_price:
            data = await _fetch_current_price(
                currency_client,
                base_currency=base_currency,
                quote_currency=quote_currency,
                yahoo_symbol=yahoo_symbol,
                include_prepost=include_prepost,
            )
            return _make_success_response(data)

        normalized_preset = _validate_preset(preset)
        resolved_start, resolved_end, start_ts, end_ts = _resolve_datetime_range(
            preset=normalized_preset,
            start=start,
            end=end,
        )
        normalized_interval = normalize_interval(interval)
        _validate_inputs(
            start_ts=start_ts,
            end_ts=end_ts,
            interval=normalized_interval,
            limit=limit,
        )

        raw = await currency_client.fetch_chart(
            ticker=yahoo_symbol,
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
                "pair": f"{base_currency}/{quote_currency}",
                "base_currency": base_currency,
                "quote_currency": quote_currency,
                "yahoo_symbol": yahoo_symbol,
                "interval": normalized_interval,
                "preset": normalized_preset,
                "start": resolved_start,
                "end": resolved_end,
                "timezone": quote_meta.timezone,
                "meta": quote_meta.to_dict(),
                "bars": [bar.to_dict() for bar in bars],
                "dropped_null_bar_count": dropped_null_bar_count,
            }
        )
    except Exception as exc:
        return _make_error_response(exc)
