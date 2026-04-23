from __future__ import annotations

import asyncio

import pytest

from investment_mcp_server.models import FundPricePoint
from investment_mcp_server.tools.fund_price_data import execute_get_fund_price_data


class FakeFundClient:
    def __init__(self) -> None:
        self.calls: list[dict] = []

    async def get_price_history(
        self,
        fund_code: str,
        *,
        start_date: str,
        end_date: str,
    ) -> list[FundPricePoint]:
        self.calls.append(
            {
                "fund_code": fund_code,
                "start_date": start_date,
                "end_date": end_date,
            }
        )
        return [
            FundPricePoint(date="2026-04-20", price=0.9, fund_code="AFT", fund_name="AFT Fund"),
            FundPricePoint(date="2026-04-21", price=0.93, fund_code="AFT", fund_name="AFT Fund"),
            FundPricePoint(date="2026-04-22", price=0.99, fund_code="AFT", fund_name="AFT Fund"),
        ]


def test_execute_get_fund_price_data_success() -> None:
    client = FakeFundClient()

    result = asyncio.run(
        execute_get_fund_price_data(
            client,
            fund_code="aft",
            start_date="2026-04-20",
            end_date="2026-04-22",
        )
    )

    assert result["ok"] is True
    assert result["error"] is None
    assert result["data"]["fund_code"] == "AFT"
    assert result["data"]["source"] == "tefas"
    assert result["data"]["interval"] == "1d"
    assert result["data"]["price_count"] == 3
    assert result["data"]["summary"]["opening_price"] == 0.9
    assert result["data"]["summary"]["closing_price"] == 0.99
    assert result["data"]["summary"]["average_price"] == pytest.approx(0.94)
    assert result["data"]["summary"]["total_return_percent"] == pytest.approx(10.0)
    assert client.calls[0] == {
        "fund_code": "AFT",
        "start_date": "2026-04-20",
        "end_date": "2026-04-22",
    }


def test_execute_get_fund_price_data_preset_success() -> None:
    client = FakeFundClient()

    result = asyncio.run(
        execute_get_fund_price_data(
            client,
            fund_code="aft",
            preset="1mo",
        )
    )

    assert result["ok"] is True
    assert result["data"]["preset"] == "1mo"
    assert result["data"]["start_date"] == client.calls[0]["start_date"]
    assert result["data"]["end_date"] == client.calls[0]["end_date"]
    assert client.calls[0]["fund_code"] == "AFT"


def test_execute_get_fund_price_data_rejects_bad_code() -> None:
    client = FakeFundClient()

    result = asyncio.run(
        execute_get_fund_price_data(
            client,
            fund_code="AFT.IS",
            start_date="2026-04-20",
            end_date="2026-04-22",
        )
    )

    assert result["ok"] is False
    assert result["error"]["code"] == "INVALID_INPUT"
    assert client.calls == []


def test_execute_get_fund_price_data_rejects_missing_range() -> None:
    client = FakeFundClient()

    result = asyncio.run(
        execute_get_fund_price_data(
            client,
            fund_code="AFT",
        )
    )

    assert result["ok"] is False
    assert result["error"]["code"] == "INVALID_INPUT"
    assert client.calls == []


def test_execute_get_fund_price_data_rejects_preset_with_date_range() -> None:
    client = FakeFundClient()

    result = asyncio.run(
        execute_get_fund_price_data(
            client,
            fund_code="AFT",
            preset="1w",
            start_date="2026-04-20",
            end_date="2026-04-22",
        )
    )

    assert result["ok"] is False
    assert result["error"]["code"] == "INVALID_INPUT"
    assert client.calls == []


def test_execute_get_fund_price_data_rejects_bad_date_range() -> None:
    client = FakeFundClient()

    result = asyncio.run(
        execute_get_fund_price_data(
            client,
            fund_code="AFT",
            start_date="2026-04-22",
            end_date="2026-04-20",
        )
    )

    assert result["ok"] is False
    assert result["error"]["code"] == "INVALID_INPUT"
    assert client.calls == []
