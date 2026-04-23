from __future__ import annotations

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
            "data": [
                {
                    "TARIH": "1776816000000",
                    "FONKODU": "AFT",
                    "FONUNVAN": "AK PORTFOY TEST FONU",
                    "FIYAT": 0.905215,
                    "TEDPAYSAYISI": 27978981651.0,
                    "KISISAYISI": 143815.0,
                    "PORTFOYBUYUKLUK": 25326993827.57,
                    "BORSABULTENFIYAT": "-",
                },
                {
                    "TARIH": "1776643200000",
                    "FONKODU": "AFT",
                    "FONUNVAN": "AK PORTFOY TEST FONU",
                    "FIYAT": 0.904217,
                },
            ]
        },
        expected_fund_code="AFT",
    )

    assert [point.date for point in points] == ["2026-04-20", "2026-04-22"]
    assert points[0].price == 0.904217
    assert points[1].investor_count == 143815
    assert points[1].exchange_bulletin_price is None
