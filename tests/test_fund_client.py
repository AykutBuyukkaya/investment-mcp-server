from __future__ import annotations

import asyncio

import httpx
import pytest

from investment_mcp_server.errors import InputError
from investment_mcp_server.fund_client import DirectFundClient, normalize_fund_code


def test_normalize_fund_code_uppercases_and_validates() -> None:
    assert normalize_fund_code("aft") == "AFT"

    with pytest.raises(InputError):
        normalize_fund_code("AFT.IS")


def test_direct_fund_client_parses_tefas_history_payload() -> None:
    client = DirectFundClient()
    points = client._parse_history_payload(
        {
            "resultList": [
                {
                    "fonKodu": "AFT",
                    "fonUnvan": "AK PORTFOY TEST FONU",
                    "kategoriDerece": 1,
                    "kategoriFonSay": 10,
                    "tarih": "2026-04-22",
                    "fiyat": 0.905215,
                },
                {
                    "fonKodu": "AFT",
                    "fonUnvan": "AK PORTFOY TEST FONU",
                    "tarih": "2026-04-20",
                    "fiyat": 0.904217,
                },
            ]
        },
        expected_fund_code="AFT",
    )

    assert [point.date for point in points] == ["2026-04-20", "2026-04-22"]
    assert points[0].price == 0.904217
    assert points[1].fund_name == "AK PORTFOY TEST FONU"


def test_direct_fund_client_posts_new_tefas_period_request() -> None:
    requests: list[httpx.Request] = []

    async def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        return httpx.Response(
            200,
            json={
                "errorCode": None,
                "errorMessage": None,
                "resultList": [
                    {
                        "fonKodu": "GTA",
                        "fonUnvan": "GARANTI PORTFOY ALTIN FONU",
                        "tarih": "2026-04-20",
                        "fiyat": 1.01,
                    },
                    {
                        "fonKodu": "GTA",
                        "fonUnvan": "GARANTI PORTFOY ALTIN FONU",
                        "tarih": "2026-04-22",
                        "fiyat": 1.02,
                    },
                ],
            },
        )

    async def run() -> None:
        async with httpx.AsyncClient(
            base_url="https://www.tefas.gov.tr",
            transport=httpx.MockTransport(handler),
        ) as async_client:
            client = DirectFundClient(async_client)
            points = await client.get_price_history(
                "gta",
                start_date="2026-04-20",
                end_date="2026-04-22",
            )

        assert [point.price for point in points] == [1.01, 1.02]

    asyncio.run(run())

    assert requests[0].url.path == "/api/funds/fonFiyatBilgiGetir"
    assert requests[0].headers["content-type"] == "application/json"
    assert requests[0].read() == b'{"fonKodu":"GTA","dil":"TR","periyod":13}'
