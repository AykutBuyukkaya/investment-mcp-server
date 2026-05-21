"""Multi-asset return comparison MCP tool."""

from __future__ import annotations

import asyncio
from datetime import datetime, timedelta
from typing import Any, Literal, Protocol
from zoneinfo import ZoneInfo

from investment_mcp_server.errors import InputError, NoDataError, map_exception_to_error_payload
from investment_mcp_server.fund_client import normalize_fund_code
from investment_mcp_server.gold_client import normalize_gold_asset
from investment_mcp_server.models import FundPricePoint, GoldHistoricalBar
from investment_mcp_server.parsers import normalize_currency_pair, normalize_ticker, parse_ohlcv_bars


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
VALID_ASSET_TYPES = {"stock", "currency", "gold", "fund"}
MAX_ASSETS = 10


class StockChartClient(Protocol):
    async def fetch_chart(
        self,
        ticker: str,
        period1: int,
        period2: int,
        interval: str,
        include_prepost: bool | None = None,
    ) -> dict[str, Any]: ...


class GoldHistoryClient(Protocol):
    async def get_history(
        self,
        asset: str,
        *,
        preset: str | None = None,
        start_date: str | None = None,
        end_date: str | None = None,
    ) -> list[GoldHistoricalBar]: ...


class FundHistoryClient(Protocol):
    async def get_price_history(
        self,
        fund_code: str,
        *,
        start_date: str,
        end_date: str,
    ) -> list[FundPricePoint]: ...


def _make_success_response(data: dict[str, Any]) -> dict[str, Any]:
    return {"ok": True, "data": data, "error": None}


def _make_error_response(exc: Exception) -> dict[str, Any]:
    payload = map_exception_to_error_payload(exc)
    return {"ok": False, "data": None, "error": payload.to_dict()}


def _validate_preset(preset: str | None) -> Preset | None:
    if preset is None:
        return None
    normalized = preset.strip().lower()
    if normalized not in VALID_PRESETS:
        allowed = ", ".join(sorted(VALID_PRESETS))
        raise InputError(f"Unsupported preset '{preset}'. Valid presets: {allowed}")
    return normalized  # type: ignore[return-value]


def _validate_date(value: str | None, *, field_name: str) -> str | None:
    if value is None:
        return None
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
    """Return (start_date_str, end_date_str, period_days)."""
    has_date_range = start_date is not None or end_date is not None
    if preset is None and not has_date_range:
        raise InputError("Provide either a preset or both start_date and end_date")
    if preset is not None and has_date_range:
        raise InputError("preset cannot be combined with start_date or end_date")
    if (start_date is None) != (end_date is None):
        raise InputError("start_date and end_date must be provided together")

    if preset is not None:
        end_dt = datetime.now(MARKET_TIMEZONE)
        start_dt = end_dt - timedelta(days=PRESET_DAYS[preset])
        return start_dt.strftime(DATE_FORMAT), end_dt.strftime(DATE_FORMAT), PRESET_DAYS[preset]

    assert start_date is not None
    assert end_date is not None
    if end_date < start_date:
        raise InputError("end_date must be greater than or equal to start_date")
    days = max((datetime.strptime(end_date, DATE_FORMAT) - datetime.strptime(start_date, DATE_FORMAT)).days, 1)
    return start_date, end_date, days


def _compute_return(
    *,
    opening_price: float,
    closing_price: float,
    days: int,
) -> tuple[float | None, float | None]:
    if opening_price <= 0:
        return None, None
    total_return = ((closing_price - opening_price) / opening_price) * 100
    annualized: float | None = None
    if days > 0 and closing_price > 0:
        annualized = ((closing_price / opening_price) ** (365 / days) - 1) * 100
    return total_return, annualized


async def _fetch_stock_return(
    stock_client: StockChartClient,
    *,
    identifier: str,
    start_date: str,
    end_date: str,
    days: int,
) -> dict[str, Any]:
    normalized = normalize_ticker(identifier)
    start_dt = datetime.strptime(start_date, DATE_FORMAT).replace(tzinfo=MARKET_TIMEZONE)
    end_dt = datetime.strptime(end_date, DATE_FORMAT).replace(
        hour=23, minute=59, second=59, tzinfo=MARKET_TIMEZONE
    )
    raw = await stock_client.fetch_chart(
        ticker=normalized,
        period1=int(start_dt.timestamp()),
        period2=int(end_dt.timestamp()),
        interval="1d",
        include_prepost=False,
    )
    bars, _ = parse_ohlcv_bars(raw, include_null_bars=False, strict_alignment=False)
    if not bars:
        raise NoDataError(f"No price data available for {normalized}")
    opening_price = bars[0].open if bars[0].open is not None else bars[0].close
    closing_price = bars[-1].close if bars[-1].close is not None else bars[-1].open
    if opening_price is None or closing_price is None:
        raise NoDataError(f"Insufficient price data for {normalized}")
    total_ret, ann_ret = _compute_return(opening_price=opening_price, closing_price=closing_price, days=days)
    return {
        "type": "stock",
        "identifier": normalized,
        "opening_price": opening_price,
        "closing_price": closing_price,
        "opening_date": bars[0].datetime_utc[:10],
        "closing_date": bars[-1].datetime_utc[:10],
        "total_return_percent": total_ret,
        "annualized_return_percent": ann_ret,
        "currency": "TRY",
        "source": "yahoo_finance",
        "error": None,
    }


async def _fetch_currency_return(
    stock_client: StockChartClient,
    *,
    identifier: str,
    start_date: str,
    end_date: str,
    days: int,
) -> dict[str, Any]:
    base_currency, quote_currency, yahoo_symbol = normalize_currency_pair(identifier)
    start_dt = datetime.strptime(start_date, DATE_FORMAT).replace(tzinfo=MARKET_TIMEZONE)
    end_dt = datetime.strptime(end_date, DATE_FORMAT).replace(
        hour=23, minute=59, second=59, tzinfo=MARKET_TIMEZONE
    )
    raw = await stock_client.fetch_chart(
        ticker=yahoo_symbol,
        period1=int(start_dt.timestamp()),
        period2=int(end_dt.timestamp()),
        interval="1d",
        include_prepost=True,
    )
    bars, _ = parse_ohlcv_bars(raw, include_null_bars=False, strict_alignment=False)
    if not bars:
        raise NoDataError(f"No price data available for {yahoo_symbol}")
    opening_price = bars[0].open if bars[0].open is not None else bars[0].close
    closing_price = bars[-1].close if bars[-1].close is not None else bars[-1].open
    if opening_price is None or closing_price is None:
        raise NoDataError(f"Insufficient price data for {yahoo_symbol}")
    total_ret, ann_ret = _compute_return(opening_price=opening_price, closing_price=closing_price, days=days)
    return {
        "type": "currency",
        "identifier": f"{base_currency}/{quote_currency}",
        "yahoo_symbol": yahoo_symbol,
        "opening_price": opening_price,
        "closing_price": closing_price,
        "opening_date": bars[0].datetime_utc[:10],
        "closing_date": bars[-1].datetime_utc[:10],
        "total_return_percent": total_ret,
        "annualized_return_percent": ann_ret,
        "currency": quote_currency,
        "source": "yahoo_finance",
        "error": None,
    }


async def _fetch_gold_return(
    gold_client: GoldHistoryClient,
    *,
    identifier: str,
    start_date: str,
    end_date: str,
    days: int,
) -> dict[str, Any]:
    normalized_asset = normalize_gold_asset(identifier)
    bars = await gold_client.get_history(
        normalized_asset.code,
        start_date=start_date,
        end_date=end_date,
    )
    usable = [b for b in bars if b.open is not None or b.close is not None]
    if not usable:
        raise NoDataError(f"No price data available for {normalized_asset.code}")
    opening_price = usable[0].open if usable[0].open is not None else usable[0].close
    closing_price = usable[-1].close if usable[-1].close is not None else usable[-1].open
    if opening_price is None or closing_price is None:
        raise NoDataError(f"Insufficient price data for {normalized_asset.code}")
    total_ret, ann_ret = _compute_return(opening_price=opening_price, closing_price=closing_price, days=days)
    return {
        "type": "gold",
        "identifier": normalized_asset.code,
        "opening_price": opening_price,
        "closing_price": closing_price,
        "opening_date": usable[0].date,
        "closing_date": usable[-1].date,
        "total_return_percent": total_ret,
        "annualized_return_percent": ann_ret,
        "currency": normalized_asset.currency,
        "source": "canlidoviz",
        "error": None,
    }


async def _fetch_fund_return(
    fund_client: FundHistoryClient,
    *,
    identifier: str,
    start_date: str,
    end_date: str,
    days: int,
) -> dict[str, Any]:
    normalized_code = normalize_fund_code(identifier)
    points = await fund_client.get_price_history(
        normalized_code,
        start_date=start_date,
        end_date=end_date,
    )
    if not points:
        raise NoDataError(f"No price data available for fund {normalized_code}")
    opening_price = points[0].price
    closing_price = points[-1].price
    total_ret, ann_ret = _compute_return(opening_price=opening_price, closing_price=closing_price, days=days)
    return {
        "type": "fund",
        "identifier": normalized_code,
        "fund_name": next((p.fund_name for p in points if p.fund_name), None),
        "opening_price": opening_price,
        "closing_price": closing_price,
        "opening_date": points[0].date,
        "closing_date": points[-1].date,
        "total_return_percent": total_ret,
        "annualized_return_percent": ann_ret,
        "currency": "TRY",
        "source": "tefas",
        "error": None,
    }


async def _fetch_asset(
    *,
    asset_spec: dict[str, Any],
    stock_client: StockChartClient,
    gold_client: GoldHistoryClient,
    fund_client: FundHistoryClient,
    start_date: str,
    end_date: str,
    days: int,
) -> dict[str, Any]:
    asset_type = str(asset_spec.get("type") or "").strip().lower()
    identifier = str(asset_spec.get("identifier") or "").strip()

    if asset_type not in VALID_ASSET_TYPES:
        allowed = ", ".join(sorted(VALID_ASSET_TYPES))
        return {
            "type": asset_type or "(missing)",
            "identifier": identifier or "(missing)",
            "error": {
                "code": "INVALID_INPUT",
                "message": f"Unknown asset type '{asset_type}'. Valid types: {allowed}",
                "retryable": False,
            },
        }
    if not identifier:
        return {
            "type": asset_type,
            "identifier": "(missing)",
            "error": {
                "code": "INVALID_INPUT",
                "message": "Asset identifier cannot be empty",
                "retryable": False,
            },
        }

    try:
        if asset_type == "stock":
            return await _fetch_stock_return(
                stock_client, identifier=identifier, start_date=start_date, end_date=end_date, days=days
            )
        if asset_type == "currency":
            return await _fetch_currency_return(
                stock_client, identifier=identifier, start_date=start_date, end_date=end_date, days=days
            )
        if asset_type == "gold":
            return await _fetch_gold_return(
                gold_client, identifier=identifier, start_date=start_date, end_date=end_date, days=days
            )
        return await _fetch_fund_return(
            fund_client, identifier=identifier, start_date=start_date, end_date=end_date, days=days
        )
    except Exception as exc:
        payload = map_exception_to_error_payload(exc)
        return {
            "type": asset_type,
            "identifier": identifier,
            "error": payload.to_dict(),
        }


def _validate_asset_specs(specs: list[Any]) -> list[dict[str, Any]]:
    if not isinstance(specs, list) or not specs:
        raise InputError("assets must be a non-empty list of asset specs")
    if len(specs) > MAX_ASSETS:
        raise InputError(f"Too many assets. Maximum allowed is {MAX_ASSETS}")
    for i, spec in enumerate(specs):
        if not isinstance(spec, dict):
            raise InputError(
                "Each asset spec must be a dict with 'type' and 'identifier' keys",
                details={"index": i},
            )
    return list(specs)


async def execute_compare_asset_returns(
    stock_client: StockChartClient,
    gold_client: GoldHistoryClient,
    fund_client: FundHistoryClient,
    *,
    assets: list[Any],
    preset: str | None = None,
    start_date: str | None = None,
    end_date: str | None = None,
) -> dict[str, Any]:
    """Compare nominal returns across multiple assets over a shared period."""
    try:
        validated_specs = _validate_asset_specs(assets)
        normalized_preset = _validate_preset(preset)
        normalized_start = _validate_date(start_date, field_name="start_date")
        normalized_end = _validate_date(end_date, field_name="end_date")
        resolved_start, resolved_end, days = _resolve_date_range(
            preset=normalized_preset,
            start_date=normalized_start,
            end_date=normalized_end,
        )

        tasks = [
            _fetch_asset(
                asset_spec=spec,
                stock_client=stock_client,
                gold_client=gold_client,
                fund_client=fund_client,
                start_date=resolved_start,
                end_date=resolved_end,
                days=days,
            )
            for spec in validated_specs
        ]
        results: list[dict[str, Any]] = list(await asyncio.gather(*tasks))

        def _sort_key(entry: dict[str, Any]) -> float:
            ret = entry.get("total_return_percent")
            return ret if isinstance(ret, (int, float)) else float("-inf")

        ranked = sorted(results, key=_sort_key, reverse=True)

        return _make_success_response(
            {
                "preset": normalized_preset,
                "start_date": resolved_start,
                "end_date": resolved_end,
                "period_days": days,
                "asset_count": len(results),
                "assets": results,
                "ranked_by_return": ranked,
            }
        )
    except Exception as exc:
        return _make_error_response(exc)
