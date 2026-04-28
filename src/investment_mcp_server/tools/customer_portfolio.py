"""Customer portfolio MCP tool implementation."""

from __future__ import annotations

from typing import Any, Protocol

from investment_mcp_server.errors import NoDataError, map_exception_to_error_payload


class PortfolioClient(Protocol):
    async def fetch_portfolio(self) -> dict[str, Any]: ...


def _make_success_response(data: dict[str, Any]) -> dict[str, Any]:
    return {"ok": True, "data": data, "error": None}


def _make_error_response(exc: Exception) -> dict[str, Any]:
    payload = map_exception_to_error_payload(exc)
    return {"ok": False, "data": None, "error": payload.to_dict()}


def _validate_portfolio_payload(payload: dict[str, Any]) -> dict[str, Any]:
    assets = payload.get("assets")
    if not isinstance(assets, list):
        raise NoDataError("Portfolio response missing assets array")

    currency = payload.get("currency")
    if not isinstance(currency, str) or not currency.strip():
        raise NoDataError("Portfolio response missing currency")

    total_value = payload.get("totalValue")
    if not isinstance(total_value, int | float):
        raise NoDataError("Portfolio response missing numeric totalValue")

    for index, asset in enumerate(assets):
        if not isinstance(asset, dict):
            raise NoDataError(
                "Portfolio response contains an invalid asset",
                details={"asset_index": index},
            )

    return payload


async def execute_get_customer_portfolio(
    portfolio_client: PortfolioClient,
) -> dict[str, Any]:
    """Fetch the customer's portfolio from the backend in a standard envelope."""
    try:
        payload = await portfolio_client.fetch_portfolio()
        return _make_success_response(_validate_portfolio_payload(payload))
    except Exception as exc:
        return _make_error_response(exc)
