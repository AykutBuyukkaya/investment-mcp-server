"""Fund price MCP tool implementation."""

from __future__ import annotations

from datetime import datetime, timedelta
from typing import Any, Literal, Protocol
from zoneinfo import ZoneInfo

from investment_mcp_server.errors import InputError, map_exception_to_error_payload
from investment_mcp_server.fund_client import DATE_FORMAT, normalize_fund_code
from investment_mcp_server.models import FundPricePoint, FundPriceSummary

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
MARKET_TIMEZONE = ZoneInfo("Europe/Istanbul")


class FundPriceClient(Protocol):
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
) -> tuple[str, str]:
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
        return start_dt.strftime(DATE_FORMAT), end_dt.strftime(DATE_FORMAT)

    assert start_date is not None
    assert end_date is not None
    if end_date < start_date:
        raise InputError("end_date must be greater than or equal to start_date")
    return start_date, end_date


def _fund_price_summary(
    *,
    fund_code: str,
    points: list[FundPricePoint],
    start_date: str,
    end_date: str,
) -> FundPriceSummary:
    if not points:
        raise InputError("No fund price points are available")

    opening_price = points[0].price
    closing_price = points[-1].price
    average_price = sum(point.price for point in points) / len(points)

    total_return_percent: float | None = None
    annualized_return_percent: float | None = None
    if opening_price > 0:
        total_return_percent = ((closing_price - opening_price) / opening_price) * 100

        start_dt = datetime.strptime(start_date, DATE_FORMAT)
        end_dt = datetime.strptime(end_date, DATE_FORMAT)
        days = (end_dt - start_dt).days
        if days > 0 and closing_price > 0:
            annualized_return_percent = ((closing_price / opening_price) ** (365 / days) - 1) * 100

    fund_name = next((point.fund_name for point in points if point.fund_name), None)

    return FundPriceSummary(
        fund_code=fund_code,
        fund_name=fund_name,
        opening_price=opening_price,
        closing_price=closing_price,
        average_price=average_price,
        total_return_percent=total_return_percent,
        annualized_return_percent=annualized_return_percent,
        start_date=points[0].date,
        end_date=points[-1].date,
        point_count=len(points),
    )


def _latest_fund_price(
    *,
    fund_code: str,
    points: list[FundPricePoint],
) -> dict[str, Any]:
    if not points:
        raise InputError("No fund price points are available")

    latest = points[-1]
    return {
        "fund_code": fund_code,
        "fund_name": latest.fund_name,
        "source": "tefas",
        "current_price": latest.price,
        "currency": "TRY",
        "date": latest.date,
    }


async def execute_get_fund_price_data(
    fund_client: FundPriceClient,
    *,
    fund_code: str,
    preset: str | None = None,
    start_date: str | None = None,
    end_date: str | None = None,
    current_price: bool = False,
) -> dict[str, Any]:
    """Fetch daily TEFAS fund price data in a standard envelope."""
    try:
        normalized_fund_code = normalize_fund_code(fund_code)
        if current_price:
            end_dt = datetime.now(MARKET_TIMEZONE)
            start_dt = end_dt - timedelta(days=14)
            points = await fund_client.get_price_history(
                normalized_fund_code,
                start_date=start_dt.strftime(DATE_FORMAT),
                end_date=end_dt.strftime(DATE_FORMAT),
            )
            return _make_success_response(
                _latest_fund_price(fund_code=normalized_fund_code, points=points)
            )

        normalized_preset = _validate_preset(preset)
        normalized_start_date = _validate_date(start_date, field_name="start_date")
        normalized_end_date = _validate_date(end_date, field_name="end_date")
        resolved_start_date, resolved_end_date = _resolve_date_range(
            preset=normalized_preset,
            start_date=normalized_start_date,
            end_date=normalized_end_date,
        )

        points = await fund_client.get_price_history(
            normalized_fund_code,
            start_date=resolved_start_date,
            end_date=resolved_end_date,
        )
        summary = _fund_price_summary(
            fund_code=normalized_fund_code,
            points=points,
            start_date=resolved_start_date,
            end_date=resolved_end_date,
        )

        return _make_success_response(
            {
                "fund_code": normalized_fund_code,
                "source": "tefas",
                "interval": "1d",
                "preset": normalized_preset,
                "start_date": resolved_start_date,
                "end_date": resolved_end_date,
                "prices": [point.to_dict() for point in points],
                "price_count": len(points),
                "summary": summary.to_dict(),
            }
        )
    except Exception as exc:
        return _make_error_response(exc)
