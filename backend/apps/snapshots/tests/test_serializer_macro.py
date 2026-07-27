"""The macro section renders as a table with as-of dates, an explicit
publication-lag note (FRED daily series lag ~1 business day — the AI must not
read that as a broken feed), and best-effort live Treasury yields."""

from unittest.mock import patch

import apps.snapshots.services as snapshot_services
from apps.snapshots.serializer import _render_macro

_DGS2 = {"label": "2Y yield", "value": 4.37, "prev": 4.31, "change": 0.06, "date": "2026-07-23"}
_DGS10 = {"label": "10Y yield", "value": 4.71, "prev": 4.67, "change": 0.04, "date": "2026-07-23"}


def test_macro_renders_series_table_with_as_of_dates_and_lag_note():
    out = _render_macro({"series": {"DGS2": _DGS2}, "live_yields": {}})
    assert "## Macro" in out
    assert "2Y yield" in out
    assert "2026-07-23" in out
    assert "lag" in out
    assert "```json" not in out


def test_macro_renders_live_yields_block():
    out = _render_macro(
        {"series": {}, "live_yields": {"10Y": {"ticker": "$TNX", "yield_pct": 4.71}}}
    )
    assert "Live Treasury yields" in out
    assert "4.71" in out


def test_macro_legacy_flat_payload_still_renders():
    out = _render_macro({"DGS10": _DGS10})
    assert "10Y yield" in out
    assert "2026-07-23" in out


def test_macro_empty_payload():
    assert "_(empty)_" in _render_macro({})


def test_macro_fetcher_combines_fred_series_and_live_yields():
    with (
        patch.object(snapshot_services, "fred_fetch_macro", return_value={"DGS10": _DGS10}),
        patch.object(
            snapshot_services,
            "live_yields",
            return_value={"10Y": {"ticker": "$TNX", "yield_pct": 4.71}},
        ),
    ):
        out = snapshot_services._FETCHERS["macro"]()
    assert out["data"]["series"] == {"DGS10": _DGS10}
    assert out["data"]["live_yields"]["10Y"]["yield_pct"] == 4.71
