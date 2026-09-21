"""Capture options are client input — the composer's timeframe/bar-count selects
post straight through to the fetchers, so the view validates them.

The failure mode being pinned: an unsupported value used to reach ``fetch_ohlc``
inside the capture task, where it failed one section of an already-created
snapshot — a snapshot that looks captured but has no price path, and no 4xx to
tell the user why.
"""

from unittest.mock import patch

import pytest

from apps.market.services.ohlc import MAX_BARS, MIN_BARS, SUPPORTED_TIMEFRAMES
from apps.profiles.models import TradingProfile
from apps.snapshots.models import Snapshot


def _post(api, profile, **extra):
    with patch("apps.snapshots.views.capture_task.delay") as task:
        task.return_value.id = "task-1"
        resp = api.post(
            "/api/snapshots/",
            {"profile_id": profile.id, "includes": ["ohlc"], **extra},
            format="json",
        )
    return resp, task


@pytest.fixture
def profile(db):
    return TradingProfile.objects.create(name="P", style="x")


@pytest.mark.parametrize("timeframe", SUPPORTED_TIMEFRAMES)
def test_every_supported_timeframe_is_accepted(api, profile, timeframe):
    resp, task = _post(api, profile, ohlc_timeframe=timeframe, ohlc_bars=60)
    assert resp.status_code == 202
    assert task.call_args.kwargs["ohlc_timeframe"] == timeframe


@pytest.mark.parametrize("timeframe", ["2m", "4h", "1w", "1M", "daily", "1"])
def test_unsupported_timeframe_is_a_clean_400(api, profile, timeframe):
    resp, task = _post(api, profile, ohlc_timeframe=timeframe)
    assert resp.status_code == 400
    assert resp.json()["code"] == "invalid_timeframe"
    task.assert_not_called()
    # Rejected before the row exists — no orphan pending snapshot.
    assert not Snapshot.objects.exists()


@pytest.mark.parametrize("bars", [MIN_BARS, 60, 252, MAX_BARS])
def test_bar_counts_inside_the_bounds_are_accepted(api, profile, bars):
    resp, task = _post(api, profile, ohlc_timeframe="1d", ohlc_bars=bars)
    assert resp.status_code == 202
    assert task.call_args.kwargs["ohlc_bars"] == bars


@pytest.mark.parametrize("bars", [0, -5, MIN_BARS - 1, MAX_BARS + 1, 100_000])
def test_bar_counts_outside_the_bounds_are_a_clean_400(api, profile, bars):
    resp, _task = _post(api, profile, ohlc_timeframe="1d", ohlc_bars=bars)
    assert resp.status_code == 400
    assert resp.json()["code"] == "invalid_bars"


@pytest.mark.parametrize("bars", ["sixty", [], {"n": 60}])
def test_non_integer_bar_count_is_a_clean_400(api, profile, bars):
    resp, _task = _post(api, profile, ohlc_timeframe="1d", ohlc_bars=bars)
    assert resp.status_code == 400
    assert resp.json()["code"] == "invalid_bars"


def test_omitted_options_keep_the_defaults(api, profile):
    resp, task = _post(api, profile)
    assert resp.status_code == 202
    assert task.call_args.kwargs["ohlc_timeframe"] == "1m"
    assert task.call_args.kwargs["ohlc_bars"] == 60
