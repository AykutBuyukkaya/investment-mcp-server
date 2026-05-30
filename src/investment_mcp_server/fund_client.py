"""Direct TEFAS fund price client."""

from __future__ import annotations

from datetime import datetime
import re
from typing import Any

import httpx

from investment_mcp_server.errors import (
    InputError,
    NoDataError,
    UpstreamHTTPStatusError,
    UpstreamUnavailableError,
)
from investment_mcp_server.models import FundPricePoint
from investment_mcp_server.rate_limiter import RateLimiter


FUND_CODE_PATTERN = re.compile(r"^[A-Z0-9]{2,12}$")
DATE_FORMAT = "%Y-%m-%d"
TEFAS_PERIODS_BY_DAY_LIMIT: tuple[tuple[int, int], ...] = (
    (7, 13),
    (31, 1),
    (93, 3),
    (186, 6),
    (366, 12),
    (1098, 36),
    (1830, 60),
)


def normalize_fund_code(fund_code: str) -> str:
    """Normalize and validate a TEFAS fund code."""
    if not isinstance(fund_code, str):
        raise InputError("fund_code must be a string")

    cleaned = fund_code.strip().upper()
    if not cleaned:
        raise InputError("fund_code cannot be empty")

    if not FUND_CODE_PATTERN.fullmatch(cleaned):
        raise InputError("fund_code must be 2-12 uppercase letters or digits")

    return cleaned


def _parse_iso_date(value: str, *, field_name: str) -> datetime:
    if not isinstance(value, str) or not value.strip():
        raise InputError(f"{field_name} must be a non-empty string in YYYY-MM-DD format")
    try:
        return datetime.strptime(value.strip(), DATE_FORMAT)
    except ValueError as exc:
        raise InputError(f"Invalid {field_name} '{value}'. Expected format: YYYY-MM-DD") from exc


def _float_or_none(value: Any) -> float | None:
    if value in (None, ""):
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _tefas_period_for_date_range(start_dt: datetime, end_dt: datetime) -> int:
    day_count = (end_dt - start_dt).days
    for max_days, period in TEFAS_PERIODS_BY_DAY_LIMIT:
        if day_count <= max_days:
            return period
    raise InputError("TEFAS fund price date range cannot exceed 5 years")


class DirectFundClient:
    """Direct async client for TEFAS daily fund price data."""

    BASE_URL = "https://www.tefas.gov.tr"
    USER_AGENT = (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
        "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/137.0.0.0 Safari/537.36"
    )

    def __init__(
        self,
        async_client: httpx.AsyncClient | None = None,
        rate_limiter: RateLimiter | None = None,
    ) -> None:
        self._client = async_client
        self._rate_limiter = rate_limiter or RateLimiter.from_rps(2.0)

    async def close(self) -> None:
        return None

    async def get_price_history(
        self,
        fund_code: str,
        *,
        start_date: str,
        end_date: str,
    ) -> list[FundPricePoint]:
        normalized_code = normalize_fund_code(fund_code)
        raw = await self._fetch_history(normalized_code, start_date, end_date)
        points = self._parse_history_payload(raw, expected_fund_code=normalized_code)
        points = [
            point
            for point in points
            if start_date <= point.date <= end_date
        ]
        if not points:
            raise NoDataError(f"No TEFAS fund price data returned for {normalized_code}")
        return points

    async def _fetch_history(
        self,
        fund_code: str,
        start_date: str,
        end_date: str,
    ) -> dict[str, Any]:
        start_dt = _parse_iso_date(start_date, field_name="start_date")
        end_dt = _parse_iso_date(end_date, field_name="end_date")
        if end_dt < start_dt:
            raise InputError("end_date must be greater than or equal to start_date")

        request_json = {
            "fonKodu": fund_code,
            "dil": "TR",
            "periyod": _tefas_period_for_date_range(start_dt, end_dt),
        }

        if self._client is not None:
            response = await self._request_history(self._client, fund_code, request_json)
        else:
            async with self._new_client() as client:
                response = await self._request_history(client, fund_code, request_json)

        if response.status_code >= 400:
            raise UpstreamHTTPStatusError(
                status_code=response.status_code,
                message=f"TEFAS request failed with status {response.status_code}",
                details={"url": str(response.request.url)},
            )

        try:
            payload = response.json()
        except ValueError as exc:
            raise NoDataError(f"TEFAS returned non-JSON fund price data for {fund_code}") from exc

        if not isinstance(payload, dict):
            raise NoDataError(f"TEFAS returned unexpected fund price data for {fund_code}")
        if payload.get("errorCode") is not None or payload.get("errorMessage") is not None:
            raise NoDataError(
                f"TEFAS returned an error for {fund_code}",
                details={
                    "source": "tefas",
                    "error_code": payload.get("errorCode"),
                    "error_message": payload.get("errorMessage"),
                },
            )

        return payload

    def _new_client(self) -> httpx.AsyncClient:
        return httpx.AsyncClient(
            base_url=self.BASE_URL,
            timeout=httpx.Timeout(timeout=20.0, connect=5.0, read=15.0),
            headers={
                "Accept": "application/json, text/javascript, */*; q=0.01",
                "Accept-Language": "tr-TR,tr;q=0.9,en-US;q=0.8,en;q=0.7",
                "Content-Type": "application/json",
                "Origin": self.BASE_URL,
                "Referer": f"{self.BASE_URL}/FonAnaliz.aspx",
                "User-Agent": self.USER_AGENT,
                "X-Requested-With": "XMLHttpRequest",
            },
            verify=False,
        )

    async def _request_history(
        self,
        client: httpx.AsyncClient,
        fund_code: str,
        data: dict[str, str | int],
    ) -> httpx.Response:
        try:
            await self._rate_limiter.acquire()
            return await client.post("/api/funds/fonFiyatBilgiGetir", json=data)
        except httpx.RequestError as exc:
            raise UpstreamUnavailableError(
                f"Failed to fetch TEFAS fund price data for {fund_code}",
                details={"source": "tefas", "reason": str(exc)},
            ) from exc

    def _parse_history_payload(
        self,
        payload: dict[str, Any],
        *,
        expected_fund_code: str | None = None,
    ) -> list[FundPricePoint]:
        rows = payload.get("resultList")
        if not isinstance(rows, list):
            raise NoDataError("TEFAS response missing resultList array")

        points: list[FundPricePoint] = []
        for row in rows:
            if not isinstance(row, dict):
                continue
            price = _float_or_none(row.get("fiyat"))
            if price is None:
                continue

            date_value = row.get("tarih")
            if not isinstance(date_value, str):
                continue
            try:
                date_text = datetime.strptime(date_value.strip(), DATE_FORMAT).date().isoformat()
            except ValueError:
                continue

            fund_code = row.get("fonKodu")
            fund_code = str(fund_code).strip().upper() if fund_code is not None else expected_fund_code

            points.append(
                FundPricePoint(
                    date=date_text,
                    price=price,
                    fund_code=fund_code,
                    fund_name=row.get("fonUnvan"),
                )
            )

        points.sort(key=lambda point: point.date)
        return points
