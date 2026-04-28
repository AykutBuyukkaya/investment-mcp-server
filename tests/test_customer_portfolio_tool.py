from __future__ import annotations

import asyncio

from investment_mcp_server.tools.customer_portfolio import execute_get_customer_portfolio


def _portfolio_payload() -> dict:
    return {
        "currency": "TRY",
        "totalValue": 408588.7224,
        "assets": [
            {
                "id": 1,
                "assetType": "FUND",
                "assetDetail": "GTA",
                "purchaseDate": "01.01.2026",
                "normalizedAsset": "GTA",
                "amount": 13,
                "unitPrice": 1.62072,
                "marketValue": 21.0694,
                "currency": "TRY",
                "priceSource": "tefas",
                "pricedAt": "2026-04-28",
            }
        ],
    }


class FakePortfolioClient:
    def __init__(self, payload: dict) -> None:
        self.payload = payload
        self.call_count = 0

    async def fetch_portfolio(self) -> dict:
        self.call_count += 1
        return self.payload


def test_execute_get_customer_portfolio_success() -> None:
    client = FakePortfolioClient(_portfolio_payload())

    result = asyncio.run(execute_get_customer_portfolio(client))

    assert result["ok"] is True
    assert result["error"] is None
    assert result["data"]["currency"] == "TRY"
    assert result["data"]["totalValue"] == 408588.7224
    assert result["data"]["assets"][0]["normalizedAsset"] == "GTA"
    assert client.call_count == 1


def test_execute_get_customer_portfolio_rejects_malformed_payload() -> None:
    client = FakePortfolioClient({"currency": "TRY", "totalValue": 1})

    result = asyncio.run(execute_get_customer_portfolio(client))

    assert result["ok"] is False
    assert result["data"] is None
    assert result["error"]["code"] == "NO_DATA"
