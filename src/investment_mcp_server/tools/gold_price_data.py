"""Gold price MCP tool implementation."""

from __future__ import annotations

from datetime import datetime
from typing import Any, Literal, Protocol

from investment_mcp_server.errors import InputError, map_exception_to_error_payload
from investment_mcp_server.gold_client import normalize_gold_asset
from investment_mcp_server.models import GoldHistoricalBar, GoldPriceSummary


Preset = Literal["1w", "1mo", "3mo", "6mo", "1y", "5y"]
DATE_FORMAT = "%Y-%m-%d"
VALID_PRESETS: set[Preset] = {"1w", "1mo", "3mo", "6mo", "1y", "5y"}


class GoldPriceClient(Protocol):
    async def get_history(
        self,
        asset: str,
        *,
        preset: str | None = None,
        start_date: str | None = None,
        end_date: str | None = None,
    ) -> list[GoldHistoricalBar]: ...


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


def _gold_price_summary(
    *,
    asset: str,
    currency: str,
    bars: list[GoldHistoricalBar],
) -> GoldPriceSummary:
    usable_bars = [bar for bar in bars if bar.open is not None and bar.close is not None]
    if not usable_bars:
        raise InputError("No gold bars with both opening and closing prices are available")

    opening_price = usable_bars[0].open
    closing_price = usable_bars[-1].close
    assert opening_price is not None
    assert closing_price is not None

    average_candidates: list[float] = []
    for bar in usable_bars:
        if bar.open is not None:
            average_candidates.append(bar.open)
        if bar.close is not None:
            average_candidates.append(bar.close)

    average_price = sum(average_candidates) / len(average_candidates)

    return GoldPriceSummary(
        asset=asset,
        currency=currency,
        opening_price=opening_price,
        closing_price=closing_price,
        average_price=average_price,
        start_date=usable_bars[0].date,
        end_date=usable_bars[-1].date,
        bar_count=len(usable_bars),
    )


async def execute_get_gold_price_data(
    gold_client: GoldPriceClient,
    *,
    asset: str = "gram-altin",
    preset: str | None = None,
    start_date: str | None = None,
    end_date: str | None = None,
) -> dict[str, Any]:
    """Fetch daily gold price data in a standard envelope."""
    try:
        normalized_preset = _validate_preset(preset)
        normalized_start_date = _validate_date(start_date, field_name="start_date")
        normalized_end_date = _validate_date(end_date, field_name="end_date")
        normalized_asset = normalize_gold_asset(asset)

        has_date_range = normalized_start_date is not None or normalized_end_date is not None
        if normalized_preset is None and not has_date_range:
            raise InputError("Provide either a preset or both start_date and end_date")
        if normalized_preset is not None and has_date_range:
            raise InputError("preset cannot be combined with start_date or end_date")
        if (normalized_start_date is None) != (normalized_end_date is None):
            raise InputError("start_date and end_date must be provided together")
        if (
            normalized_start_date is not None
            and normalized_end_date is not None
            and normalized_end_date < normalized_start_date
        ):
            raise InputError("end_date must be greater than or equal to start_date")

        bars = await gold_client.get_history(
            normalized_asset.code,
            preset=normalized_preset,
            start_date=normalized_start_date,
            end_date=normalized_end_date,
        )
        summary = _gold_price_summary(
            asset=normalized_asset.code,
            currency=normalized_asset.currency,
            bars=bars,
        )

        return _make_success_response(
            {
                "asset": normalized_asset.code,
                "source": "canlidoviz",
                "interval": "1d",
                "preset": normalized_preset,
                "start_date": normalized_start_date,
                "end_date": normalized_end_date,
                "bars": [bar.to_dict() for bar in bars],
                "bar_count": len(bars),
                "summary": summary.to_dict(),
            }
        )
    except Exception as exc:
        return _make_error_response(exc)
