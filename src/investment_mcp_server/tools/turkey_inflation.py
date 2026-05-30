"""Turkey consumer price inflation MCP tool implementation."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Any, Literal

from investment_mcp_server.errors import InputError, map_exception_to_error_payload
from investment_mcp_server.inflation_client import fetch_inflation_data

PERIOD_FORMAT = "%m-%Y"
DATE_FORMAT = "%Y-%m-%d"

Preset = Literal["1w", "1mo", "3mo", "6mo", "1y", "5y"]
VALID_PRESETS: set[Preset] = {"1w", "1mo", "3mo", "6mo", "1y", "5y"}
PRESET_MONTHS: dict[str, int] = {
    "1w": 1,
    "1mo": 1,
    "3mo": 3,
    "6mo": 6,
    "1y": 12,
    "5y": 60,
}


@dataclass(frozen=True, slots=True)
class TurkeyInflationPoint:
    period: str
    annual_percent: float
    monthly_percent: float

    @property
    def year(self) -> int:
        return int(self.period[3:])

    @property
    def month(self) -> int:
        return int(self.period[:2])

    @property
    def sort_key(self) -> tuple[int, int]:
        return self.year, self.month

    def to_dict(self) -> dict[str, Any]:
        return {
            "period": self.period,
            "year": self.year,
            "month": self.month,
            "annual_percent": self.annual_percent,
            "monthly_percent": self.monthly_percent,
        }


def _make_success_response(data: dict[str, Any]) -> dict[str, Any]:
    return {"ok": True, "data": data, "error": None}


def _make_error_response(exc: Exception) -> dict[str, Any]:
    payload = map_exception_to_error_payload(exc)
    return {"ok": False, "data": None, "error": payload.to_dict()}


def _build_points(raw: list[tuple[str, float, float]]) -> list[TurkeyInflationPoint]:
    return [
        TurkeyInflationPoint(period=period, annual_percent=annual, monthly_percent=monthly)
        for period, annual, monthly in raw
    ]


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


def _validate_limit(limit: int | None) -> int | None:
    if limit is None:
        return None
    if not isinstance(limit, int) or limit <= 0:
        raise InputError("limit must be a positive integer when set")
    return limit


def _date_to_sort_key(date_str: str) -> tuple[int, int]:
    dt = datetime.strptime(date_str, DATE_FORMAT)
    return dt.year, dt.month


def _dataset_metadata(earliest: TurkeyInflationPoint, latest: TurkeyInflationPoint) -> dict[str, Any]:
    return {
        "source": "tcmb_live",
        "source_url": (
            "https://www.tcmb.gov.tr/wps/wcm/connect/TR/TCMB+TR/Main+Menu"
            "/Istatistikler/Enflasyon+Verileri/Tuketici+Fiyatlari"
        ),
        "country": "Turkey",
        "indicator": "Fiyat Endeksi (Tuketici Fiyatlari)",
        "index_base": "2025=100",
        "frequency": "monthly",
        "earliest_period": earliest.period,
        "latest_period": latest.period,
    }


async def execute_get_turkey_inflation(
    *,
    current: bool = False,
    preset: str | None = None,
    start_date: str | None = None,
    end_date: str | None = None,
    limit: int | None = None,
) -> dict[str, Any]:
    """Return Turkey CPI inflation data in a standard envelope."""
    try:
        raw = await fetch_inflation_data()
        points = _build_points(raw)
        sorted_points = sorted(points, key=lambda p: p.sort_key)
        by_period = {p.period: p for p in points}
        earliest = sorted_points[0]
        latest = sorted_points[-1]
        meta = _dataset_metadata(earliest, latest)

        if current:
            return _make_success_response(
                {
                    **meta,
                    "current": True,
                    "preset": None,
                    "start_date": None,
                    "end_date": None,
                    "period": latest.period,
                    "annual_percent": latest.annual_percent,
                    "monthly_percent": latest.monthly_percent,
                    "records": [latest.to_dict()],
                    "record_count": 1,
                }
            )

        normalized_preset = _validate_preset(preset)
        normalized_start = _validate_date(start_date, field_name="start_date")
        normalized_end = _validate_date(end_date, field_name="end_date")
        normalized_limit = _validate_limit(limit)

        has_date_range = normalized_start is not None or normalized_end is not None
        if normalized_preset is not None and has_date_range:
            raise InputError("preset cannot be combined with start_date or end_date")
        if (normalized_start is None) != (normalized_end is None):
            raise InputError("start_date and end_date must be provided together")
        if normalized_start is not None and normalized_end is not None:
            if normalized_end < normalized_start:
                raise InputError("end_date must be greater than or equal to start_date")

        if normalized_preset is not None:
            n_months = PRESET_MONTHS[normalized_preset]
            cutoff_dt = datetime.now() - timedelta(days=n_months * 30)
            cutoff_key = (cutoff_dt.year, cutoff_dt.month)
            records = [p for p in sorted_points if p.sort_key >= cutoff_key]
            if normalized_limit is not None:
                records = records[-normalized_limit:]
            last = records[-1] if records else latest
            return _make_success_response(
                {
                    **meta,
                    "current": False,
                    "preset": normalized_preset,
                    "start_date": None,
                    "end_date": None,
                    "period": last.period,
                    "annual_percent": last.annual_percent,
                    "monthly_percent": last.monthly_percent,
                    "records": [p.to_dict() for p in records],
                    "record_count": len(records),
                }
            )

        if has_date_range:
            assert normalized_start is not None
            assert normalized_end is not None
            start_key = _date_to_sort_key(normalized_start)
            end_key = _date_to_sort_key(normalized_end)
            records = [p for p in sorted_points if start_key <= p.sort_key <= end_key]
            if normalized_limit is not None:
                records = records[-normalized_limit:]
            last = records[-1] if records else latest
            return _make_success_response(
                {
                    **meta,
                    "current": False,
                    "preset": None,
                    "start_date": normalized_start,
                    "end_date": normalized_end,
                    "period": last.period,
                    "annual_percent": last.annual_percent,
                    "monthly_percent": last.monthly_percent,
                    "records": [p.to_dict() for p in records],
                    "record_count": len(records),
                }
            )

        # No arguments: return latest
        if normalized_limit is not None:
            records = sorted_points[-normalized_limit:]
        else:
            records = [latest]
        last = records[-1]
        return _make_success_response(
            {
                **meta,
                "current": False,
                "preset": None,
                "start_date": None,
                "end_date": None,
                "period": last.period,
                "annual_percent": last.annual_percent,
                "monthly_percent": last.monthly_percent,
                "records": [p.to_dict() for p in records],
                "record_count": len(records),
            }
        )
    except Exception as exc:
        return _make_error_response(exc)
