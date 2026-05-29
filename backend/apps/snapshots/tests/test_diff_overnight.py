import pytest

from apps.snapshots.diff import diff_sections


def test_diff_overnight_reports_moves_above_threshold():
    prev = {"overnight": {"futures": {"/ES": {"last": 5000.0}}, "vol_rates": {}, "overseas": {}}}
    curr = {"overnight": {"futures": {"/ES": {"last": 5050.0}}, "vol_rates": {}, "overseas": {}}}
    md = diff_sections(prev, curr)
    assert "/ES" in md
    assert "1.00%" in md


def test_diff_overnight_ignores_sub_threshold():
    prev = {"overnight": {"futures": {"/ES": {"last": 5000.0}}, "vol_rates": {}, "overseas": {}}}
    curr = {"overnight": {"futures": {"/ES": {"last": 5001.0}}, "vol_rates": {}, "overseas": {}}}
    md = diff_sections(prev, curr)
    assert "below 0.5%" in md


@pytest.mark.parametrize("bad", [None, [], "x", {"futures": "nope"}])
def test_diff_overnight_never_raises_on_bad_shape(bad):
    diff_sections({"overnight": bad}, {"overnight": bad})  # must not raise
