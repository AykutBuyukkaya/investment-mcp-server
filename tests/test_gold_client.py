from __future__ import annotations

import pytest

from investment_mcp_server.errors import InputError
from investment_mcp_server.gold_client import DirectGoldClient, normalize_gold_asset


def test_normalize_gold_asset_accepts_supported_aliases() -> None:
    assert normalize_gold_asset("gram").code == "gram-altin"
    assert normalize_gold_asset("xautry").code == "gram-altin"


def test_normalize_gold_asset_rejects_removed_assets() -> None:
    with pytest.raises(InputError):
        normalize_gold_asset("ons")


def test_direct_gold_client_parses_canlidoviz_history_payload() -> None:
    client = DirectGoldClient()
    bars = client._parse_history_payload(
        {
            "1776902400": "6200.0|6250.0|6190.0|6240.0",
            "not-a-timestamp": "ignored",
            "1776988800": "6240.0|6300.0|6230.0|6290.0",
        }
    )

    assert len(bars) == 2
    assert bars[0].close == 6240.0
    assert bars[1].high == 6300.0
