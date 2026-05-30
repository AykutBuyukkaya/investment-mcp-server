"""TCMB Turkey CPI inflation data client."""

from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import datetime, timedelta

import httpx

from investment_mcp_server.errors import NoDataError, UpstreamHTTPStatusError, UpstreamUnavailableError

TCMB_URL = (
    "https://www.tcmb.gov.tr/wps/wcm/connect/TR/TCMB+TR/Main+Menu"
    "/Istatistikler/Enflasyon+Verileri/Tuketici+Fiyatlari"
)

_TD_RE = re.compile(r"<td[^>]*>(.*?)</td>", re.DOTALL)
_PERIOD_RE = re.compile(r"^\d{2}-\d{4}$")

_CACHE_TTL = timedelta(hours=1)


@dataclass
class _CacheEntry:
    records: list[tuple[str, float, float]]
    fetched_at: datetime


_cache: _CacheEntry | None = None


def _parse_inflation_html(html: str) -> list[tuple[str, float, float]]:
    """Return list of (period, annual_pct, monthly_pct) parsed from TCMB table HTML."""
    cells = [m.group(1).strip() for m in _TD_RE.finditer(html)]
    records: list[tuple[str, float, float]] = []
    for i in range(0, len(cells) - 2, 3):
        period = cells[i]
        if not _PERIOD_RE.match(period):
            continue
        try:
            annual = float(cells[i + 1])
            monthly = float(cells[i + 2])
        except ValueError:
            continue
        records.append((period, annual, monthly))
    return records


async def fetch_inflation_data() -> list[tuple[str, float, float]]:
    """Fetch Turkey CPI inflation data from TCMB, with a 1-hour in-process cache."""
    global _cache

    now = datetime.now()
    if _cache is not None and (now - _cache.fetched_at) < _CACHE_TTL:
        return _cache.records

    try:
        async with httpx.AsyncClient(
            timeout=httpx.Timeout(15.0, connect=5.0),
            follow_redirects=True,
        ) as client:
            response = await client.get(TCMB_URL)
    except httpx.RequestError as exc:
        raise UpstreamUnavailableError(
            "Failed to fetch Turkey inflation data from TCMB",
            details={"source": "tcmb", "reason": str(exc)},
        ) from exc

    if response.status_code >= 400:
        raise UpstreamHTTPStatusError(
            status_code=response.status_code,
            message=f"TCMB returned HTTP {response.status_code}",
            details={"url": str(response.url)},
        )

    records = _parse_inflation_html(response.text)
    if not records:
        raise NoDataError("No inflation data could be parsed from the TCMB page")

    _cache = _CacheEntry(records=records, fetched_at=now)
    return records
