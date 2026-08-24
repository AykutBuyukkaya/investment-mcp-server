"""BIST stock screener MCP tool: rank stocks by price return and PE ratio."""

from __future__ import annotations

import asyncio
from datetime import datetime, timedelta
from typing import Any, Literal, Protocol
from zoneinfo import ZoneInfo

from investment_mcp_server.bist_sectors import resolve_sector_tickers
from investment_mcp_server.errors import InputError, NoDataError, map_exception_to_error_payload
from investment_mcp_server.models import StockFundamentals
from investment_mcp_server.parsers import normalize_ticker, parse_ohlcv_bars
from investment_mcp_server.tools.stock_fundamentals import FundamentalsClient


MARKET_TIMEZONE = ZoneInfo("Europe/Istanbul")
DATE_FORMAT = "%Y-%m-%d"
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
DEFAULT_PRESET: Preset = "1mo"
VALID_PE_METRICS = {"trailing", "forward"}
VALID_SORT_BY = {"composite", "return", "pe"}
MAX_TICKERS = 50


class StockChartClient(Protocol):
    async def fetch_chart(
        self,
        ticker: str,
        period1: int,
        period2: int,
        interval: str,
        include_prepost: bool | None = None,
    ) -> dict[str, Any]: ...


def _make_success_response(data: dict[str, Any]) -> dict[str, Any]:
    return {"ok": True, "data": data, "error": None}


def _make_error_response(exc: Exception) -> dict[str, Any]:
    payload = map_exception_to_error_payload(exc)
    return {"ok": False, "data": None, "error": payload.to_dict()}


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


def _validate_date(value: str | None, *, field_name: str) -> str | None:
    if value is None:
        return None
    if not isinstance(value, str) or not value.strip():
        raise InputError(f"{field_name} must be a non-empty string in YYYY-MM-DD format")
    cleaned = value.strip()
    try:
        datetime.strptime(cleaned, DATE_FORMAT)
    except ValueError as exc:
        raise InputError(f"Invalid {field_name} '{value}'. Expected format: YYYY-MM-DD") from exc
    return cleaned


def _resolve_date_range(
    *,
    preset: Preset | None,
    start_date: str | None,
    end_date: str | None,
) -> tuple[str, str, int]:
    if preset is not None:
        end_dt = datetime.now(MARKET_TIMEZONE)
        start_dt = end_dt - timedelta(days=PRESET_DAYS[preset])
        return start_dt.strftime(DATE_FORMAT), end_dt.strftime(DATE_FORMAT), PRESET_DAYS[preset]

    assert start_date is not None
    assert end_date is not None
    if end_date < start_date:
        raise InputError("end_date must be greater than or equal to start_date")
    days = max(
        (datetime.strptime(end_date, DATE_FORMAT) - datetime.strptime(start_date, DATE_FORMAT)).days, 1
    )
    return start_date, end_date, days


def _validate_tickers(tickers: list[Any]) -> list[str]:
    if not isinstance(tickers, list) or not all(isinstance(t, str) for t in tickers):
        raise InputError("tickers must be a list of strings")
    deduped = list(dict.fromkeys(t.strip() for t in tickers if isinstance(t, str) and t.strip()))
    if not deduped:
        raise InputError("tickers cannot be empty")
    if len(deduped) > MAX_TICKERS:
        raise InputError(f"Too many tickers. Maximum allowed is {MAX_TICKERS}")
    return deduped


async def _fetch_price_return(
    stock_client: StockChartClient,
    ticker: str,
    *,
    start_date: str,
    end_date: str,
) -> dict[str, Any]:
    start_dt = datetime.strptime(start_date, DATE_FORMAT).replace(tzinfo=MARKET_TIMEZONE)
    end_dt = datetime.strptime(end_date, DATE_FORMAT).replace(
        hour=23, minute=59, second=59, tzinfo=MARKET_TIMEZONE
    )
    raw = await stock_client.fetch_chart(
        ticker=ticker,
        period1=int(start_dt.timestamp()),
        period2=int(end_dt.timestamp()),
        interval="1d",
        include_prepost=False,
    )
    bars, _ = parse_ohlcv_bars(raw, include_null_bars=False, strict_alignment=False)
    if not bars:
        raise NoDataError(f"No price data available for {ticker}")

    opening_price = bars[0].open if bars[0].open is not None else bars[0].close
    closing_price = bars[-1].close if bars[-1].close is not None else bars[-1].open
    if opening_price is None or closing_price is None or opening_price <= 0:
        raise NoDataError(f"Insufficient price data for {ticker}")

    total_return_percent = ((closing_price - opening_price) / opening_price) * 100
    return {
        "opening_price": opening_price,
        "closing_price": closing_price,
        "opening_date": bars[0].datetime_utc[:10],
        "closing_date": bars[-1].datetime_utc[:10],
        "total_return_percent": total_return_percent,
    }


async def _screen_one(
    stock_client: StockChartClient,
    fundamentals_client: FundamentalsClient,
    *,
    ticker: str,
    start_date: str,
    end_date: str,
    pe_metric: str,
) -> dict[str, Any]:
    try:
        normalized = normalize_ticker(ticker)
    except Exception as exc:
        return {"ticker": ticker, "error": map_exception_to_error_payload(exc).to_dict()}

    return_result, fundamentals_result = await asyncio.gather(
        _fetch_price_return(stock_client, normalized, start_date=start_date, end_date=end_date),
        fundamentals_client.get_fundamentals(normalized),
        return_exceptions=True,
    )

    entry: dict[str, Any] = {"ticker": normalized}

    if isinstance(return_result, BaseException):
        entry["total_return_percent"] = None
        entry["return_error"] = map_exception_to_error_payload(return_result).to_dict()
    else:
        entry.update(return_result)

    if isinstance(fundamentals_result, BaseException):
        entry["pe"] = None
        entry["fundamentals_error"] = map_exception_to_error_payload(fundamentals_result).to_dict()
    else:
        assert isinstance(fundamentals_result, StockFundamentals)
        pe_value = (
            fundamentals_result.trailing_pe if pe_metric == "trailing" else fundamentals_result.forward_pe
        )
        entry["pe"] = pe_value
        entry["pe_metric"] = pe_metric
        entry["trailing_pe"] = fundamentals_result.trailing_pe
        entry["forward_pe"] = fundamentals_result.forward_pe
        entry["trailing_eps"] = fundamentals_result.trailing_eps
        entry["forward_eps"] = fundamentals_result.forward_eps
        entry["short_name"] = fundamentals_result.short_name
        entry["currency"] = fundamentals_result.currency
        entry["market_cap"] = fundamentals_result.market_cap

    return entry


def _partition_entries(
    entries: list[dict[str, Any]],
    *,
    pe_metric: str,
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    usable: list[dict[str, Any]] = []
    excluded: list[dict[str, Any]] = []

    for entry in entries:
        if entry.get("error"):
            excluded.append({"ticker": entry["ticker"], "reason": entry["error"].get("message", "fetch failed")})
            continue
        if entry.get("return_error"):
            excluded.append(
                {"ticker": entry["ticker"], "reason": entry["return_error"].get("message", "no price data")}
            )
            continue
        if entry.get("fundamentals_error"):
            excluded.append(
                {
                    "ticker": entry["ticker"],
                    "reason": entry["fundamentals_error"].get("message", "no fundamentals data"),
                }
            )
            continue

        pe_value = entry.get("pe")
        if pe_value is None or pe_value <= 0:
            excluded.append(
                {
                    "ticker": entry["ticker"],
                    "reason": f"no valid {pe_metric} PE (loss-making or unavailable)",
                }
            )
            continue

        if entry.get("total_return_percent") is None:
            excluded.append({"ticker": entry["ticker"], "reason": "no return data"})
            continue

        usable.append(entry)

    return usable, excluded


def _rank_entries(usable: list[dict[str, Any]], *, sort_by: str) -> list[dict[str, Any]]:
    if not usable:
        return []

    by_return_desc = sorted(usable, key=lambda e: e["total_return_percent"], reverse=True)
    for idx, entry in enumerate(by_return_desc, start=1):
        entry["return_rank"] = idx

    by_pe_asc = sorted(usable, key=lambda e: e["pe"])
    for idx, entry in enumerate(by_pe_asc, start=1):
        entry["pe_rank"] = idx

    for entry in usable:
        entry["composite_rank_score"] = entry["return_rank"] + entry["pe_rank"]

    if sort_by == "return":
        return sorted(usable, key=lambda e: e["total_return_percent"], reverse=True)
    if sort_by == "pe":
        return sorted(usable, key=lambda e: e["pe"])
    return sorted(usable, key=lambda e: e["composite_rank_score"])


async def execute_screen_bist_stocks(
    stock_client: StockChartClient,
    fundamentals_client: FundamentalsClient,
    *,
    tickers: list[str] | None = None,
    sector: str = "financials",
    preset: str | None = None,
    start_date: str | None = None,
    end_date: str | None = None,
    pe_metric: str = "trailing",
    max_pe: float | None = None,
    min_return_percent: float | None = None,
    sort_by: str = "composite",
    limit: int = 10,
) -> dict[str, Any]:
    """Screen BIST stocks by price return and PE ratio, ranked highest-return/lowest-PE first."""
    try:
        if tickers:
            candidate_tickers = _validate_tickers(tickers)
            universe_source = "custom"
            universe_label: str | None = None
        else:
            candidate_tickers = list(resolve_sector_tickers(sector))
            universe_source = "sector_preset"
            universe_label = sector.strip().lower()

        if pe_metric not in VALID_PE_METRICS:
            allowed = ", ".join(sorted(VALID_PE_METRICS))
            raise InputError(f"pe_metric must be one of: {allowed}")
        if sort_by not in VALID_SORT_BY:
            allowed = ", ".join(sorted(VALID_SORT_BY))
            raise InputError(f"sort_by must be one of: {allowed}")
        if not isinstance(limit, int) or isinstance(limit, bool) or limit <= 0:
            raise InputError("limit must be a positive integer")
        if max_pe is not None and max_pe <= 0:
            raise InputError("max_pe must be greater than 0")

        normalized_preset = _validate_preset(preset)
        normalized_start = _validate_date(start_date, field_name="start_date")
        normalized_end = _validate_date(end_date, field_name="end_date")
        has_date_range = normalized_start is not None or normalized_end is not None
        if normalized_preset is not None and has_date_range:
            raise InputError("preset cannot be combined with start_date or end_date")
        if (normalized_start is None) != (normalized_end is None):
            raise InputError("start_date and end_date must be provided together")
        if normalized_preset is None and not has_date_range:
            normalized_preset = DEFAULT_PRESET

        resolved_start, resolved_end, days = _resolve_date_range(
            preset=normalized_preset, start_date=normalized_start, end_date=normalized_end
        )

        tasks = [
            _screen_one(
                stock_client,
                fundamentals_client,
                ticker=ticker,
                start_date=resolved_start,
                end_date=resolved_end,
                pe_metric=pe_metric,
            )
            for ticker in candidate_tickers
        ]
        entries = list(await asyncio.gather(*tasks))

        usable, excluded = _partition_entries(entries, pe_metric=pe_metric)

        if max_pe is not None:
            below_max_pe = [e for e in usable if e["pe"] <= max_pe]
            for e in usable:
                if e["pe"] > max_pe:
                    excluded.append({"ticker": e["ticker"], "reason": f"PE {e['pe']} exceeds max_pe {max_pe}"})
            usable = below_max_pe

        if min_return_percent is not None:
            above_min_return = [e for e in usable if e["total_return_percent"] >= min_return_percent]
            for e in usable:
                if e["total_return_percent"] < min_return_percent:
                    excluded.append(
                        {
                            "ticker": e["ticker"],
                            "reason": (
                                f"return {e['total_return_percent']:.2f}% below "
                                f"min_return_percent {min_return_percent}"
                            ),
                        }
                    )
            usable = above_min_return

        ranked = _rank_entries(usable, sort_by=sort_by)
        results = ranked[:limit]

        return _make_success_response(
            {
                "universe_source": universe_source,
                "sector": universe_label,
                "screened_tickers": candidate_tickers,
                "screened_count": len(candidate_tickers),
                "preset": normalized_preset,
                "start_date": resolved_start,
                "end_date": resolved_end,
                "period_days": days,
                "pe_metric": pe_metric,
                "sort_by": sort_by,
                "max_pe": max_pe,
                "min_return_percent": min_return_percent,
                "result_count": len(results),
                "results": results,
                "excluded_count": len(excluded),
                "excluded": excluded,
            }
        )
    except Exception as exc:
        return _make_error_response(exc)
