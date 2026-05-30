"""Turkey consumer price inflation MCP tool implementation."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Any

from investment_mcp_server.errors import InputError, map_exception_to_error_payload
from investment_mcp_server.inflation_client import fetch_inflation_data

PERIOD_FORMAT = "%m-%Y"
ALT_PERIOD_FORMAT = "%Y-%m"


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


def _normalize_period(value: str | None, *, field_name: str) -> str | None:
    if value is None:
        return None
    if not isinstance(value, str) or not value.strip():
        raise InputError(f"{field_name} must be a non-empty period string")

    cleaned = value.strip()
    for date_format in (PERIOD_FORMAT, ALT_PERIOD_FORMAT):
        try:
            return datetime.strptime(cleaned, date_format).strftime(PERIOD_FORMAT)
        except ValueError:
            continue

    raise InputError(
        f"Invalid {field_name} '{value}'. Expected format: MM-YYYY or YYYY-MM"
    )


def _validate_limit(limit: int | None) -> int | None:
    if limit is None:
        return None
    if not isinstance(limit, int) or limit <= 0:
        raise InputError("limit must be a positive integer when set")
    return limit


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


def _period_or_error(
    period: str,
    by_period: dict[str, TurkeyInflationPoint],
    meta: dict[str, Any],
) -> TurkeyInflationPoint:
    point = by_period.get(period)
    if point is None:
        raise InputError(
            f"No Turkey inflation data is available for period '{period}'",
            details=meta,
        )
    return point


async def execute_get_turkey_inflation(
    *,
    period: str | None = None,
    start_period: str | None = None,
    end_period: str | None = None,
    limit: int | None = None,
) -> dict[str, Any]:
    """Return Turkey CPI inflation data in a standard envelope."""
    try:
        normalized_period = _normalize_period(period, field_name="period")
        normalized_start_period = _normalize_period(start_period, field_name="start_period")
        normalized_end_period = _normalize_period(end_period, field_name="end_period")
        normalized_limit = _validate_limit(limit)

        has_range = normalized_start_period is not None or normalized_end_period is not None
        if normalized_period is not None and has_range:
            raise InputError("period cannot be combined with start_period or end_period")
        if (normalized_start_period is None) != (normalized_end_period is None):
            raise InputError("start_period and end_period must be provided together")

        raw = await fetch_inflation_data()
        points = _build_points(raw)
        sorted_points = sorted(points, key=lambda p: p.sort_key)
        by_period = {p.period: p for p in points}
        earliest = sorted_points[0]
        latest = sorted_points[-1]
        meta = _dataset_metadata(earliest, latest)

        if normalized_period is not None:
            point = _period_or_error(normalized_period, by_period, meta)
            return _make_success_response(
                {
                    **meta,
                    "period": point.period,
                    "annual_percent": point.annual_percent,
                    "monthly_percent": point.monthly_percent,
                    "records": [point.to_dict()],
                    "record_count": 1,
                }
            )

        if has_range:
            assert normalized_start_period is not None
            assert normalized_end_period is not None
            start_point = _period_or_error(normalized_start_period, by_period, meta)
            end_point = _period_or_error(normalized_end_period, by_period, meta)
            if end_point.sort_key < start_point.sort_key:
                raise InputError("end_period must be greater than or equal to start_period")

            records = [
                p for p in sorted_points
                if start_point.sort_key <= p.sort_key <= end_point.sort_key
            ]
            if normalized_limit is not None:
                records = records[-normalized_limit:]

            return _make_success_response(
                {
                    **meta,
                    "start_period": normalized_start_period,
                    "end_period": normalized_end_period,
                    "records": [p.to_dict() for p in records],
                    "record_count": len(records),
                }
            )

        if normalized_limit is not None:
            records = sorted_points[-normalized_limit:]
        else:
            records = [latest]

        latest_record = records[-1]
        return _make_success_response(
            {
                **meta,
                "period": latest_record.period,
                "annual_percent": latest_record.annual_percent,
                "monthly_percent": latest_record.monthly_percent,
                "records": [p.to_dict() for p in records],
                "record_count": len(records),
            }
        )
    except Exception as exc:
        return _make_error_response(exc)
