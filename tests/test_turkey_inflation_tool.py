from __future__ import annotations

import asyncio

from investment_mcp_server.tools.turkey_inflation import execute_get_turkey_inflation


def test_execute_get_turkey_inflation_latest_by_default() -> None:
    result = asyncio.run(execute_get_turkey_inflation())

    assert result["ok"] is True
    assert result["error"] is None
    assert result["data"]["source"] == "tcmb_live"
    assert result["data"]["index_base"] == "2025=100"
    assert result["data"]["record_count"] == 1
    assert result["data"]["current"] is False
    assert isinstance(result["data"]["annual_percent"], float)
    assert isinstance(result["data"]["monthly_percent"], float)
    assert isinstance(result["data"]["period"], str)


def test_execute_get_turkey_inflation_current_flag() -> None:
    result = asyncio.run(execute_get_turkey_inflation(current=True))

    assert result["ok"] is True
    assert result["data"]["current"] is True
    assert result["data"]["record_count"] == 1
    assert isinstance(result["data"]["annual_percent"], float)
    assert isinstance(result["data"]["period"], str)


def test_execute_get_turkey_inflation_preset_1y() -> None:
    result = asyncio.run(execute_get_turkey_inflation(preset="1y"))

    assert result["ok"] is True
    assert result["data"]["preset"] == "1y"
    assert result["data"]["record_count"] >= 1
    records = result["data"]["records"]
    # records are in ascending order
    assert records[0]["year"] <= records[-1]["year"] or (
        records[0]["year"] == records[-1]["year"]
        and records[0]["month"] <= records[-1]["month"]
    )


def test_execute_get_turkey_inflation_preset_1mo() -> None:
    result = asyncio.run(execute_get_turkey_inflation(preset="1mo"))

    assert result["ok"] is True
    assert result["data"]["preset"] == "1mo"
    assert result["data"]["record_count"] >= 1


def test_execute_get_turkey_inflation_date_range() -> None:
    result = asyncio.run(
        execute_get_turkey_inflation(start_date="2025-11-01", end_date="2026-02-28")
    )

    assert result["ok"] is True
    assert result["data"]["record_count"] == 4
    assert [record["period"] for record in result["data"]["records"]] == [
        "11-2025",
        "12-2025",
        "01-2026",
        "02-2026",
    ]


def test_execute_get_turkey_inflation_limit_returns_latest_records() -> None:
    result = asyncio.run(execute_get_turkey_inflation(limit=3))

    assert result["ok"] is True
    assert result["data"]["record_count"] == 3
    records = result["data"]["records"]
    assert len(records) == 3
    assert records[0]["year"] <= records[1]["year"] or (
        records[0]["year"] == records[1]["year"] and records[0]["month"] < records[1]["month"]
    )


def test_execute_get_turkey_inflation_rejects_invalid_preset() -> None:
    result = asyncio.run(execute_get_turkey_inflation(preset="2mo"))

    assert result["ok"] is False
    assert result["error"]["code"] == "INVALID_INPUT"


def test_execute_get_turkey_inflation_rejects_preset_with_date_range() -> None:
    result = asyncio.run(
        execute_get_turkey_inflation(
            preset="1y",
            start_date="2025-01-01",
            end_date="2026-01-01",
        )
    )

    assert result["ok"] is False
    assert result["error"]["code"] == "INVALID_INPUT"


def test_execute_get_turkey_inflation_rejects_partial_date_range() -> None:
    result = asyncio.run(execute_get_turkey_inflation(start_date="2025-01-01"))

    assert result["ok"] is False
    assert result["error"]["code"] == "INVALID_INPUT"
