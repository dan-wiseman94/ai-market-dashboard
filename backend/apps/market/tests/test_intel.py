from __future__ import annotations

from unittest.mock import patch

from apps.market.services.intel import sector_rotation


@patch("apps.market.services.intel.fetch_quotes")
def test_sector_rotation_ranks_desc_with_sector_names(mock_fq):
    mock_fq.return_value = {
        "XLK": {"last": 1, "pct_change": 1.8},
        "XLF": {"last": 1, "pct_change": 0.9},
        "XLE": {"last": 1, "pct_change": -1.2},
    }
    out = sector_rotation()
    assert [r["etf"] for r in out["ranked"]] == ["XLK", "XLF", "XLE"]
    assert out["ranked"][0] == {"etf": "XLK", "sector": "Technology", "pct": 1.8}
    assert out["ranked"][-1]["pct"] == -1.2


@patch("apps.market.services.intel.fetch_quotes")
def test_sector_rotation_drops_none_pct_and_empty_is_none(mock_fq):
    mock_fq.return_value = {"XLK": {"pct_change": None}, "XLF": {}}
    assert sector_rotation() is None
