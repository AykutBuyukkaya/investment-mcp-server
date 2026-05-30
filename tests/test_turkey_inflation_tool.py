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
    assert isinstance(result["data"]["annual_percent"], float)
    assert isinstance(result["data"]["monthly_percent"], float)
    assert isinstance(result["data"]["period"], str)


def test_execute_get_turkey_inflation_period_accepts_year_month() -> None:
    result = asyncio.run(execute_get_turkey_inflation(period="2025-12"))

    assert result["ok"] is True
    assert result["data"]["period"] == "12-2025"
    assert result["data"]["annual_percent"] == 30.89
    assert result["data"]["monthly_percent"] == 0.89
    assert result["data"]["records"][0]["year"] == 2025
    assert result["data"]["records"][0]["month"] == 12


def test_execute_get_turkey_inflation_range_success() -> None:
    result = asyncio.run(
        execute_get_turkey_inflation(start_period="11-2025", end_period="02-2026")
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
    # The 3 most recent periods should be returned in ascending order
    records = result["data"]["records"]
    assert len(records) == 3
    assert records[0]["year"] <= records[1]["year"] or (
        records[0]["year"] == records[1]["year"] and records[0]["month"] < records[1]["month"]
    )


def test_execute_get_turkey_inflation_rejects_unknown_period() -> None:
    result = asyncio.run(execute_get_turkey_inflation(period="12-2004"))

    assert result["ok"] is False
    assert result["data"] is None
    assert result["error"]["code"] == "INVALID_INPUT"


def test_execute_get_turkey_inflation_rejects_period_with_range() -> None:
    result = asyncio.run(
        execute_get_turkey_inflation(
            period="04-2026",
            start_period="01-2026",
            end_period="04-2026",
        )
    )

    assert result["ok"] is False
    assert result["error"]["code"] == "INVALID_INPUT"
