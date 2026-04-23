"""Stock quote metadata MCP tool implementation."""

from __future__ import annotations

import time
from typing import Any, Protocol

from investment_mcp_server.errors import (
    InputError,
    NoDataError,
    TickerNotFoundError,
    map_exception_to_error_payload,
)
from investment_mcp_server.parsers import normalize_ticker, parse_quote_meta


class StockChartClient(Protocol):
    async def fetch_chart(
        self,
        ticker: str,
        period1: int,
        period2: int,
        interval: str,
        include_prepost: bool | None = None,
    ) -> dict[str, Any]: ...


RANGE_SECONDS_MAP: dict[str, int] = {
    "1d": 1 * 24 * 60 * 60,
    "5d": 5 * 24 * 60 * 60,
    "1mo": 30 * 24 * 60 * 60,
    "3mo": 90 * 24 * 60 * 60,
    "6mo": 180 * 24 * 60 * 60,
    "1y": 365 * 24 * 60 * 60,
    "2y": 730 * 24 * 60 * 60,
    "5y": 1825 * 24 * 60 * 60,
    "10y": 3650 * 24 * 60 * 60,
}

DEFAULT_METADATA_RANGE = "5d"
DEFAULT_METADATA_INTERVAL = "1d"


def _resolve_period(range_value: str) -> tuple[int, int]:
    period2 = int(time.time())
    normalized = range_value.strip().lower()

    if normalized == "ytd":
        now = time.gmtime(period2)
        period1 = int(time.mktime((now.tm_year, 1, 1, 0, 0, 0, 0, 1, -1)))
        return period1, period2

    duration = RANGE_SECONDS_MAP.get(normalized)
    if duration is None:
        allowed = ", ".join(sorted([*RANGE_SECONDS_MAP.keys(), "ytd"]))
        raise InputError(f"Unsupported range '{range_value}'. Allowed: {allowed}")

    period1 = period2 - duration
    return period1, period2


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


async def execute_get_stock_quote_metadata(
    stock_client: StockChartClient,
    *,
    ticker: str,
    include_prepost: bool = False,
) -> dict[str, Any]:
    """Fetch and return normalized quote metadata wrapped in a standard envelope."""
    try:
        normalized_ticker = normalize_ticker(ticker)
        period1, period2 = _resolve_period(DEFAULT_METADATA_RANGE)

        raw = await stock_client.fetch_chart(
            ticker=normalized_ticker,
            period1=period1,
            period2=period2,
            interval=DEFAULT_METADATA_INTERVAL,
            include_prepost=include_prepost,
        )
        _raise_if_chart_error(raw)

        meta = parse_quote_meta(raw)
        return _make_success_response(
            {
                "normalized_ticker": normalized_ticker,
                "meta": meta.to_dict(),
            }
        )
    except Exception as exc:
        return _make_error_response(exc)
