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


FUND_CODE_PATTERN = re.compile(r"^[A-Z0-9]{2,12}$")
DATE_FORMAT = "%Y-%m-%d"
TEFAS_DATE_FORMAT = "%d.%m.%Y"


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


def _int_or_none(value: Any) -> int | None:
    if value in (None, ""):
        return None
    try:
        return int(float(value))
    except (TypeError, ValueError):
        return None


class DirectFundClient:
    """Direct async client for TEFAS daily fund price data."""

    BASE_URL = "https://www.tefas.gov.tr"
    USER_AGENT = (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
        "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/137.0.0.0 Safari/537.36"
    )

    def __init__(self, async_client: httpx.AsyncClient | None = None) -> None:
        self._client = async_client

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

        data = {
            "fontip": "YAT",
            "fonkod": fund_code,
            "bastarih": start_dt.strftime(TEFAS_DATE_FORMAT),
            "bittarih": end_dt.strftime(TEFAS_DATE_FORMAT),
        }

        if self._client is not None:
            response = await self._request_history(self._client, fund_code, data)
        else:
            async with self._new_client() as client:
                response = await self._request_history(client, fund_code, data)

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

        return payload

    def _new_client(self) -> httpx.AsyncClient:
        return httpx.AsyncClient(
            base_url=self.BASE_URL,
            timeout=httpx.Timeout(timeout=20.0, connect=5.0, read=15.0),
            headers={
                "Accept": "application/json, text/javascript, */*; q=0.01",
                "Accept-Language": "tr-TR,tr;q=0.9,en-US;q=0.8,en;q=0.7",
                "Content-Type": "application/x-www-form-urlencoded; charset=UTF-8",
                "Origin": self.BASE_URL,
                "Referer": f"{self.BASE_URL}/TarihselVeriler.aspx",
                "User-Agent": self.USER_AGENT,
                "X-Requested-With": "XMLHttpRequest",
            },
            verify=False,
        )

    async def _request_history(
        self,
        client: httpx.AsyncClient,
        fund_code: str,
        data: dict[str, str],
    ) -> httpx.Response:
        try:
            return await client.post("/api/DB/BindHistoryInfo", data=data)
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
        rows = payload.get("data")
        if not isinstance(rows, list):
            raise NoDataError("TEFAS response missing data array")

        points: list[FundPricePoint] = []
        for row in rows:
            if not isinstance(row, dict):
                continue
            price = _float_or_none(row.get("FIYAT"))
            if price is None:
                continue

            timestamp = _int_or_none(row.get("TARIH"))
            if timestamp is None:
                continue
            date_text = datetime.fromtimestamp(timestamp / 1000).date().isoformat()

            fund_code = row.get("FONKODU")
            fund_code = str(fund_code).strip().upper() if fund_code is not None else expected_fund_code

            points.append(
                FundPricePoint(
                    date=date_text,
                    price=price,
                    fund_code=fund_code,
                    fund_name=row.get("FONUNVAN"),
                    outstanding_shares=_float_or_none(row.get("TEDPAYSAYISI")),
                    investor_count=_int_or_none(row.get("KISISAYISI")),
                    portfolio_size=_float_or_none(row.get("PORTFOYBUYUKLUK")),
                    exchange_bulletin_price=_float_or_none(row.get("BORSABULTENFIYAT")),
                )
            )

        points.sort(key=lambda point: point.date)
        return points
