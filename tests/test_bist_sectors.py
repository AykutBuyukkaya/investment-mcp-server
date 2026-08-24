from __future__ import annotations

import pytest

from investment_mcp_server.bist_sectors import BIST_SECTOR_TICKERS, resolve_sector_tickers
from investment_mcp_server.errors import InputError


def test_resolve_sector_tickers_accepts_case_insensitive_known_sectors() -> None:
    assert resolve_sector_tickers("Financials") == BIST_SECTOR_TICKERS["financials"]
    assert resolve_sector_tickers(" industrials ") == BIST_SECTOR_TICKERS["industrials"]


def test_resolve_sector_tickers_rejects_unknown_sector() -> None:
    with pytest.raises(InputError):
        resolve_sector_tickers("agriculture")


def test_all_sector_ticker_lists_are_non_empty_and_unique() -> None:
    for sector, tickers in BIST_SECTOR_TICKERS.items():
        assert tickers, f"{sector} must have at least one ticker"
        assert len(tickers) == len(set(tickers)), f"{sector} has duplicate tickers"
