"""Real (inflation-adjusted) return calculator MCP tool."""

from __future__ import annotations

from datetime import datetime, timedelta
from typing import Any, Literal, Protocol
from zoneinfo import ZoneInfo

from investment_mcp_server.errors import InputError, NoDataError, map_exception_to_error_payload
from investment_mcp_server.fund_client import normalize_fund_code
from investment_mcp_server.gold_client import normalize_gold_asset
from investment_mcp_server.inflation_client import fetch_inflation_data
from investment_mcp_server.models import FundPricePoint, GoldHistoricalBar
from investment_mcp_server.parsers import normalize_currency_pair, normalize_ticker, parse_ohlcv_bars
from investment_mcp_server.tools.turkey_inflation import TurkeyInflationPoint


MARKET_TIMEZONE = ZoneInfo("Europe/Istanbul")
DATE_FORMAT = "%Y-%m-%d"
PERIOD_FORMAT = "%m-%Y"
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


def _compute_cumulative_cpi(
    start_date: str,
    end_date: str,
    by_period: dict[str, TurkeyInflationPoint],
) -> tuple[float, list[dict[str, Any]], list[str]]:
    """Return (cumulative_inflation_fraction, cpi_records_used, missing_months).

    Compounds monthly CPI percent changes for all months from the month of
    start_date through the month of end_date (both inclusive).
    """
    start_dt = datetime.strptime(start_date, DATE_FORMAT).replace(day=1)
    end_month_dt = datetime.strptime(end_date, DATE_FORMAT).replace(day=1)

    cumulative = 1.0
    records_used: list[dict[str, Any]] = []
    missing_months: list[str] = []

    current = start_dt
    while current <= end_month_dt:
        period_key = current.strftime(PERIOD_FORMAT)
        point = by_period.get(period_key)
        if point is not None:
            cumulative *= 1 + point.monthly_percent / 100
            records_used.append(point.to_dict())
        else:
            missing_months.append(period_key)
        # advance to next month
        current = (current.replace(day=28) + timedelta(days=4)).replace(day=1)

    return cumulative - 1.0, records_used, missing_months


async def _fetch_asset_prices(
    stock_client: StockChartClient,
    gold_client: GoldHistoryClient,
    fund_client: FundHistoryClient,
    *,
    asset_type: str,
    identifier: str,
    start_date: str,
    end_date: str,
) -> dict[str, Any]:
    """Return a dict with opening_price, closing_price, opening_date, closing_date, currency, source, identifier."""
    if asset_type == "stock":
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
        return {
            "type": "stock",
            "identifier": normalized,
            "opening_price": opening_price,
            "closing_price": closing_price,
            "opening_date": bars[0].datetime_utc[:10],
            "closing_date": bars[-1].datetime_utc[:10],
            "currency": "TRY",
            "source": "yahoo_finance",
        }

    if asset_type == "currency":
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
        return {
            "type": "currency",
            "identifier": f"{base_currency}/{quote_currency}",
            "opening_price": opening_price,
            "closing_price": closing_price,
            "opening_date": bars[0].datetime_utc[:10],
            "closing_date": bars[-1].datetime_utc[:10],
            "currency": quote_currency,
            "source": "yahoo_finance",
        }

    if asset_type == "gold":
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
        return {
            "type": "gold",
            "identifier": normalized_asset.code,
            "opening_price": opening_price,
            "closing_price": closing_price,
            "opening_date": usable[0].date,
            "closing_date": usable[-1].date,
            "currency": normalized_asset.currency,
            "source": "canlidoviz",
        }

    if asset_type == "fund":
        normalized_code = normalize_fund_code(identifier)
        points = await fund_client.get_price_history(
            normalized_code,
            start_date=start_date,
            end_date=end_date,
        )
        if not points:
            raise NoDataError(f"No price data available for fund {normalized_code}")
        return {
            "type": "fund",
            "identifier": normalized_code,
            "fund_name": next((p.fund_name for p in points if p.fund_name), None),
            "opening_price": points[0].price,
            "closing_price": points[-1].price,
            "opening_date": points[0].date,
            "closing_date": points[-1].date,
            "currency": "TRY",
            "source": "tefas",
        }

    allowed = ", ".join(sorted(VALID_ASSET_TYPES))
    raise InputError(f"Unknown asset_type '{asset_type}'. Valid types: {allowed}")


async def execute_get_real_returns(
    stock_client: StockChartClient,
    gold_client: GoldHistoryClient,
    fund_client: FundHistoryClient,
    *,
    asset_type: str,
    identifier: str,
    preset: str | None = None,
    start_date: str | None = None,
    end_date: str | None = None,
) -> dict[str, Any]:
    """Return inflation-adjusted (real) return for a single asset in a standard envelope."""
    try:
        normalized_asset_type = asset_type.strip().lower()
        if normalized_asset_type not in VALID_ASSET_TYPES:
            allowed = ", ".join(sorted(VALID_ASSET_TYPES))
            raise InputError(f"Unknown asset_type '{asset_type}'. Valid types: {allowed}")

        normalized_preset = _validate_preset(preset)
        normalized_start = _validate_date(start_date, field_name="start_date")
        normalized_end = _validate_date(end_date, field_name="end_date")
        resolved_start, resolved_end, days = _resolve_date_range(
            preset=normalized_preset,
            start_date=normalized_start,
            end_date=normalized_end,
        )

        raw_cpi = await fetch_inflation_data()
        cpi_points = [
            TurkeyInflationPoint(period=p, annual_percent=a, monthly_percent=m)
            for p, a, m in raw_cpi
        ]
        by_period = {pt.period: pt for pt in cpi_points}
        sorted_cpi = sorted(cpi_points, key=lambda pt: pt.sort_key)

        asset_data = await _fetch_asset_prices(
            stock_client,
            gold_client,
            fund_client,
            asset_type=normalized_asset_type,
            identifier=identifier.strip(),
            start_date=resolved_start,
            end_date=resolved_end,
        )

        opening_price: float = asset_data["opening_price"]
        closing_price: float = asset_data["closing_price"]

        if opening_price <= 0:
            raise NoDataError("Opening price must be positive to compute returns")

        nominal_fraction = (closing_price - opening_price) / opening_price
        nominal_return_percent = nominal_fraction * 100

        cumulative_inflation, cpi_records, missing_months = _compute_cumulative_cpi(
            resolved_start, resolved_end, by_period
        )
        cumulative_inflation_percent = cumulative_inflation * 100

        # Fisher equation: real return = (1 + nominal) / (1 + inflation) - 1
        real_fraction = (1 + nominal_fraction) / (1 + cumulative_inflation) - 1
        real_return_percent = real_fraction * 100

        nominal_annualized: float | None = None
        real_annualized: float | None = None
        if days > 0 and closing_price > 0:
            nominal_annualized = ((closing_price / opening_price) ** (365 / days) - 1) * 100
            if (1 + real_fraction) > 0:
                real_annualized = ((1 + real_fraction) ** (365 / days) - 1) * 100

        beat_inflation = real_return_percent > 0 if cpi_records else None

        return _make_success_response(
            {
                "asset_type": asset_data["type"],
                "identifier": asset_data["identifier"],
                **({k: v for k, v in {"fund_name": asset_data.get("fund_name")}.items() if v is not None}),
                "source": asset_data["source"],
                "currency": asset_data["currency"],
                "preset": normalized_preset,
                "start_date": resolved_start,
                "end_date": resolved_end,
                "period_days": days,
                "opening_price": opening_price,
                "closing_price": closing_price,
                "opening_date": asset_data["opening_date"],
                "closing_date": asset_data["closing_date"],
                "nominal_return_percent": round(nominal_return_percent, 4),
                "annualized_nominal_return_percent": round(nominal_annualized, 4) if nominal_annualized is not None else None,
                "cumulative_inflation_percent": round(cumulative_inflation_percent, 4),
                "real_return_percent": round(real_return_percent, 4),
                "annualized_real_return_percent": round(real_annualized, 4) if real_annualized is not None else None,
                "beat_inflation": beat_inflation,
                "cpi_methodology": "monthly_compounding",
                "cpi_dataset": {
                    "source": "tcmb_live",
                    "country": "Turkey",
                    "indicator": "Fiyat Endeksi (Tuketici Fiyatlari)",
                    "index_base": "2025=100",
                    "frequency": "monthly",
                    "earliest_available_period": sorted_cpi[0].period if sorted_cpi else None,
                    "latest_available_period": sorted_cpi[-1].period if sorted_cpi else None,
                },
                "cpi_record_count": len(cpi_records),
                "cpi_missing_months": missing_months,
                "cpi_records": cpi_records,
            }
        )
    except Exception as exc:
        return _make_error_response(exc)
