from __future__ import annotations

import asyncio

from investment_mcp_server.models import GoldHistoricalBar
from investment_mcp_server.tools.gold_price_data import execute_get_gold_price_data


class FakeGoldClient:
    def __init__(self) -> None:
        self.calls: list[dict] = []

    async def get_history(
        self,
        asset: str,
        *,
        preset: str | None = None,
        start_date: str | None = None,
        end_date: str | None = None,
    ) -> list[GoldHistoricalBar]:
        self.calls.append(
            {
                "method": "get_history",
                "asset": asset,
                "preset": preset,
                "start_date": start_date,
                "end_date": end_date,
            }
        )
        return [
            GoldHistoricalBar(
                date="2026-04-20",
                open=6200.0,
                high=6250.0,
                low=6190.0,
                close=6240.0,
            ),
            GoldHistoricalBar(
                date="2026-04-21",
                open=6240.0,
                high=6300.0,
                low=6230.0,
                close=6290.0,
            ),
            GoldHistoricalBar(
                date="2026-04-22",
                open=6290.0,
                high=6340.0,
                low=6280.0,
                close=6320.0,
            ),
        ]


def test_execute_get_gold_price_data_preset_success() -> None:
    client = FakeGoldClient()

    result = asyncio.run(execute_get_gold_price_data(client, asset="xautry", preset="1w"))

    assert result["ok"] is True
    assert result["error"] is None
    assert result["data"]["source"] == "canlidoviz"
    assert result["data"]["interval"] == "1d"
    assert result["data"]["preset"] == "1w"
    assert result["data"]["start_date"] is None
    assert result["data"]["end_date"] is None
    assert result["data"]["summary"]["opening_price"] == 6200.0
    assert result["data"]["summary"]["closing_price"] == 6320.0
    assert result["data"]["summary"]["average_price"] == 6263.333333333333
    assert client.calls[0]["method"] == "get_history"
    assert client.calls[0]["asset"] == "gram-altin"
    assert client.calls[0]["preset"] == "1w"


def test_execute_get_gold_price_data_date_range_success() -> None:
    client = FakeGoldClient()

    result = asyncio.run(
        execute_get_gold_price_data(
            client,
            asset="gram",
            start_date="2026-04-20",
            end_date="2026-04-22",
        )
    )

    assert result["ok"] is True
    assert result["data"]["preset"] is None
    assert result["data"]["start_date"] == "2026-04-20"
    assert result["data"]["end_date"] == "2026-04-22"
    assert result["data"]["bar_count"] == 3
    assert result["data"]["bars"][0]["date"] == "2026-04-20"
    assert result["data"]["summary"]["opening_price"] == 6200.0
    assert result["data"]["summary"]["closing_price"] == 6320.0
    assert result["data"]["summary"]["average_price"] == 6263.333333333333
    assert client.calls[0]["asset"] == "gram-altin"
    assert client.calls[0]["preset"] is None
    assert client.calls[0]["start_date"] == "2026-04-20"
    assert client.calls[0]["end_date"] == "2026-04-22"


def test_execute_get_gold_price_data_current_price_ignores_range_inputs() -> None:
    client = FakeGoldClient()

    result = asyncio.run(
        execute_get_gold_price_data(
            client,
            asset="xautry",
            preset="not-used",
            start_date="2026-04-22",
            end_date="2026-04-20",
            current_price=True,
        )
    )

    assert result["ok"] is True
    assert result["data"]["asset"] == "gram-altin"
    assert result["data"]["source"] == "canlidoviz"
    assert result["data"]["current_price"] == 6320.0
    assert result["data"]["currency"] == "TRY"
    assert result["data"]["date"] == "2026-04-22"
    assert client.calls[0]["asset"] == "gram-altin"
    assert client.calls[0]["preset"] == "1w"
    assert client.calls[0]["start_date"] is None
    assert client.calls[0]["end_date"] is None


def test_execute_get_gold_price_data_rejects_removed_assets() -> None:
    client = FakeGoldClient()

    result = asyncio.run(
        execute_get_gold_price_data(
            client,
            asset="ons",
            preset="1mo",
        )
    )

    assert result["ok"] is False
    assert result["error"]["code"] == "INVALID_INPUT"
    assert client.calls == []


def test_execute_get_gold_price_data_rejects_partial_date_range() -> None:
    client = FakeGoldClient()

    result = asyncio.run(
        execute_get_gold_price_data(
            client,
            start_date="2026-04-01",
            end_date=None,
        )
    )

    assert result["ok"] is False
    assert result["error"]["code"] == "INVALID_INPUT"


def test_execute_get_gold_price_data_rejects_invalid_preset() -> None:
    client = FakeGoldClient()

    result = asyncio.run(
        execute_get_gold_price_data(
            client,
            preset="2w",
        )
    )

    assert result["ok"] is False
    assert result["error"]["code"] == "INVALID_INPUT"


def test_execute_get_gold_price_data_requires_preset_or_date_range() -> None:
    client = FakeGoldClient()

    result = asyncio.run(execute_get_gold_price_data(client))

    assert result["ok"] is False
    assert result["error"]["code"] == "INVALID_INPUT"
    assert client.calls == []


def test_execute_get_gold_price_data_rejects_preset_with_date_range() -> None:
    client = FakeGoldClient()

    result = asyncio.run(
        execute_get_gold_price_data(
            client,
            preset="1mo",
            start_date="2026-04-01",
            end_date="2026-04-22",
        )
    )

    assert result["ok"] is False
    assert result["error"]["code"] == "INVALID_INPUT"
    assert client.calls == []
