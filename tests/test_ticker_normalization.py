from __future__ import annotations

import pytest

from investment_mcp_server.errors import InvalidTickerError
from investment_mcp_server.parsers import normalize_currency_pair, normalize_ticker


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("THYAO", "THYAO.IS"),
        ("thyao", "THYAO.IS"),
        ("thyao.is", "THYAO.IS"),
        (" THYAO.IS ", "THYAO.IS"),
        ("XU100", "XU100.IS"),
    ],
)
def test_normalize_ticker_valid_values(raw: str, expected: str) -> None:
    assert normalize_ticker(raw) == expected


@pytest.mark.parametrize(
    "raw",
    [
        "",
        "   ",
        ".IS",
        "THYAO.US",
        "THYAO-IS",
        "THYAO/IS",
        "TOO-LONG-TICKER",
        "THYAO?",
        "GARAN İS",
    ],
)
def test_normalize_ticker_invalid_values(raw: str) -> None:
    with pytest.raises(InvalidTickerError):
        normalize_ticker(raw)


def test_normalize_ticker_rejects_non_string() -> None:
    with pytest.raises(InvalidTickerError):
        normalize_ticker(123)  # type: ignore[arg-type]


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("USD/TRY", ("USD", "TRY", "TRY=X")),
        ("usdtry", ("USD", "TRY", "TRY=X")),
        (" EUR/TRY ", ("EUR", "TRY", "EURTRY=X")),
        ("EURTRY", ("EUR", "TRY", "EURTRY=X")),
        ("TRY=X", ("USD", "TRY", "TRY=X")),
        ("EURTRY=X", ("EUR", "TRY", "EURTRY=X")),
        ("GBP-USD", ("GBP", "USD", "GBPUSD=X")),
    ],
)
def test_normalize_currency_pair_valid_values(raw: str, expected: tuple[str, str, str]) -> None:
    assert normalize_currency_pair(raw) == expected


@pytest.mark.parametrize(
    "raw",
    [
        "",
        "   ",
        "USD",
        "USD/USD",
        "US/TRY",
        "USDT/TRY",
        "USD.TRY",
        "USDTRY.IS",
        "123TRY",
        "GARAN İS",
    ],
)
def test_normalize_currency_pair_invalid_values(raw: str) -> None:
    with pytest.raises(InvalidTickerError):
        normalize_currency_pair(raw)


def test_normalize_currency_pair_rejects_non_string() -> None:
    with pytest.raises(InvalidTickerError):
        normalize_currency_pair(123)  # type: ignore[arg-type]
