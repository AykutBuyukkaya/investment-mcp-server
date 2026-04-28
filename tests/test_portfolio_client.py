from __future__ import annotations

import asyncio

import httpx

from investment_mcp_server.portfolio_client import BackendPortfolioClient
from investment_mcp_server.settings import Settings


def test_backend_portfolio_client_fetches_portfolio_path() -> None:
    seen_paths: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen_paths.append(request.url.path)
        return httpx.Response(
            200,
            json={"currency": "TRY", "totalValue": 10.0, "assets": []},
        )

    async def run() -> dict:
        async_client = httpx.AsyncClient(
            base_url="http://portfolio-backend:8080",
            transport=httpx.MockTransport(handler),
        )
        client = BackendPortfolioClient(
            settings=Settings(portfolio_backend_base_url="http://portfolio-backend:8080"),
            async_client=async_client,
        )
        try:
            return await client.fetch_portfolio()
        finally:
            await async_client.aclose()

    payload = asyncio.run(run())

    assert seen_paths == ["/api/portfolio"]
    assert payload == {"currency": "TRY", "totalValue": 10.0, "assets": []}
