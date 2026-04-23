"""Direct Canli Doviz gold price client."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Any

import httpx

from investment_mcp_server.errors import (
    InputError,
    NoDataError,
    UpstreamHTTPStatusError,
    UpstreamUnavailableError,
)
from investment_mcp_server.models import GoldHistoricalBar


@dataclass(frozen=True, slots=True)
class GoldAssetSpec:
    code: str
    provider_item_id: int
    name: str
    currency: str


GOLD_ASSETS: dict[str, GoldAssetSpec] = {
    "gram-altin": GoldAssetSpec(
        code="gram-altin",
        provider_item_id=32,
        name="Gram Gold",
        currency="TRY",
    ),
}

GOLD_ASSET_ALIASES: dict[str, str] = {
    "gram": "gram-altin",
    "gram-gold": "gram-altin",
    "gram-altin": "gram-altin",
    "xautry": "gram-altin",
    "xau-try": "gram-altin",
}


def normalize_gold_asset(asset: str) -> GoldAssetSpec:
    """Normalize supported gold asset aliases to a provider asset spec."""
    if not isinstance(asset, str):
        raise InputError("asset must be a string")

    cleaned = asset.strip().lower()
    if not cleaned:
        raise InputError("asset cannot be empty")

    code = GOLD_ASSET_ALIASES.get(cleaned)
    if code is None:
        allowed = ", ".join(sorted(GOLD_ASSETS))
        raise InputError(f"Unsupported gold asset '{asset}'. Supported assets: {allowed}")

    return GOLD_ASSETS[code]


def _float_or_none(value: Any) -> float | None:
    if value is None:
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _parse_date(value: str | None) -> datetime | None:
    if value is None:
        return None
    return datetime.strptime(value, "%Y-%m-%d")


PERIOD_DAYS: dict[str, int] = {
    "1w": 7,
    "1mo": 30,
    "3mo": 90,
    "6mo": 180,
    "1y": 365,
    "5y": 1825,
}


class DirectGoldClient:
    """Direct async client for Canli Doviz gold history data."""

    BASE_URL = "https://a.canlidoviz.com"
    WEB_BASE_URL = "https://canlidoviz.com"
    USER_AGENT = (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
        "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
    )

    def __init__(self, async_client: httpx.AsyncClient | None = None) -> None:
        self._client = async_client

    async def close(self) -> None:
        return None

    async def get_history(
        self,
        asset: str,
        *,
        preset: str | None = None,
        start_date: str | None = None,
        end_date: str | None = None,
    ) -> list[GoldHistoricalBar]:
        spec = normalize_gold_asset(asset)
        raw = await self._fetch_history(spec, preset, start_date, end_date)
        bars = self._parse_history_payload(raw)

        if not bars:
            raise NoDataError(f"No historical gold price data returned for {spec.code}")

        return bars

    async def _fetch_history(
        self,
        spec: GoldAssetSpec,
        preset: str | None,
        start_date: str | None,
        end_date: str | None,
    ) -> dict[str, Any]:
        end_dt = _parse_date(end_date) or datetime.now()
        preset_days = PERIOD_DAYS[preset or "1mo"]
        start_dt = _parse_date(start_date) or (end_dt - timedelta(days=preset_days))

        params = {
            "period": "DAILY",
            "itemDataId": spec.provider_item_id,
            "startDate": start_dt.strftime("%Y-%m-%dT%H:%M:%S"),
            "endDate": end_dt.strftime("%Y-%m-%dT%H:%M:%S"),
        }

        if self._client is not None:
            response = await self._request_history(self._client, spec, params)
        else:
            async with self._new_client() as client:
                response = await self._request_history(client, spec, params)

        if response.status_code >= 400:
            raise UpstreamHTTPStatusError(
                status_code=response.status_code,
                message=f"Canli Doviz request failed with status {response.status_code}",
                details={"url": str(response.request.url)},
            )

        try:
            data = response.json()
        except ValueError as exc:
            raise NoDataError(
                f"Canli Doviz returned non-JSON gold price data for {spec.code}"
            ) from exc

        if not isinstance(data, dict):
            raise NoDataError(f"Canli Doviz returned unexpected data for {spec.code}")

        return data

    def _new_client(self) -> httpx.AsyncClient:
        return httpx.AsyncClient(
            base_url=self.BASE_URL,
            timeout=httpx.Timeout(timeout=15.0, connect=5.0, read=10.0),
            headers={
                "Accept": "*/*",
                "Accept-Language": "tr-TR,tr;q=0.9,en-US;q=0.8,en;q=0.7",
                "Origin": self.WEB_BASE_URL,
                "Referer": f"{self.WEB_BASE_URL}/",
                "User-Agent": self.USER_AGENT,
            },
        )

    async def _request_history(
        self,
        client: httpx.AsyncClient,
        spec: GoldAssetSpec,
        params: dict[str, Any],
    ) -> httpx.Response:
        try:
            return await client.get("/items/history", params=params)
        except httpx.RequestError as exc:
            raise UpstreamUnavailableError(
                f"Failed to fetch gold price data for {spec.code}",
                details={"source": "canlidoviz", "reason": str(exc)},
            ) from exc

    def _parse_history_payload(self, data: dict[str, Any]) -> list[GoldHistoricalBar]:
        bars: list[GoldHistoricalBar] = []
        for timestamp_text, ohlc_text in data.items():
            try:
                timestamp = int(timestamp_text)
            except (TypeError, ValueError):
                continue
            if not isinstance(ohlc_text, str):
                continue

            values = ohlc_text.split("|")
            if len(values) < 4:
                continue

            bars.append(
                GoldHistoricalBar(
                    date=datetime.fromtimestamp(timestamp).date().isoformat(),
                    open=_float_or_none(values[0]),
                    high=_float_or_none(values[1]),
                    low=_float_or_none(values[2]),
                    close=_float_or_none(values[3]),
                )
            )

        bars.sort(key=lambda bar: bar.date)
        return bars
