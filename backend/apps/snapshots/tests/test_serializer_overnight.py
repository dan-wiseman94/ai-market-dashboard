from apps.snapshots.serializer import (
    _render_overnight,
    _render_quotes,
)


def test_render_overnight_groups_present_only():
    md = _render_overnight(
        {
            "futures": {"/ES": {"last": 5000.0, "gap_pct": 0.5, "prior_close": 4975.0}},
            "vol_rates": {},
            "overseas": {},
        }
    )
    assert "## Overnight board" in md
    assert "Index futures" in md
    assert "/ES" in md
    assert "Vol & rates" not in md  # empty group omitted


def test_render_overnight_empty():
    md = _render_overnight({"futures": {}, "vol_rates": {}, "overseas": {}})
    assert "no overnight quotes" in md


def test_render_quotes_adds_gap_columns_when_present():
    md = _render_quotes(
        {"SPY": {"last": 100.0, "pct_change": 0.5, "gap_pct": 2.04, "prior_close": 98.0}}
    )
    assert "Gap%" in md
    assert "PrevClose" in md


def test_render_quotes_no_gap_columns_by_default():
    md = _render_quotes({"SPY": {"last": 100.0, "pct_change": 0.5}})
    assert "Gap%" not in md
