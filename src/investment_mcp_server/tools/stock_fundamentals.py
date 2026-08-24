"""Stock fundamentals (PE, EPS, ...) MCP tool implementation."""

from __future__ import annotations

from typing import Any, Protocol

from investment_mcp_server.errors import map_exception_to_error_payload
from investment_mcp_server.models import StockFundamentals
from investment_mcp_server.parsers import normalize_ticker


class FundamentalsClient(Protocol):
    async def get_fundamentals(self, symbol: str) -> StockFundamentals: ...


def _make_success_response(data: dict[str, Any]) -> dict[str, Any]:
    return {"ok": True, "data": data, "error": None}


def _make_error_response(exc: Exception) -> dict[str, Any]:
    payload = map_exception_to_error_payload(exc)
    return {"ok": False, "data": None, "error": payload.to_dict()}


async def execute_get_stock_fundamentals(
    fundamentals_client: FundamentalsClient,
    *,
    ticker: str,
) -> dict[str, Any]:
    """Fetch PE, EPS, and other fundamental metrics for a BIST equity via yfinance."""
    try:
        normalized_ticker = normalize_ticker(ticker)
        fundamentals = await fundamentals_client.get_fundamentals(normalized_ticker)

        return _make_success_response(
            {
                "normalized_ticker": normalized_ticker,
                "source": "yfinance",
                "fundamentals": fundamentals.to_dict(),
            }
        )
    except Exception as exc:
        return _make_error_response(exc)
