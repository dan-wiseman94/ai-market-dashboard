import pytest

from apps.market.calendar.registry import MARKETS, MARKET_CHOICES, get_market_calendar


def test_markets_has_the_seven_keys():
    assert set(MARKETS) == {
        "us_equity", "us_bond", "cme_futures", "cfe_futures", "crypto", "lse", "jpx"
    }


def test_market_choices_mirrors_markets():
    assert {k for k, _ in MARKET_CHOICES} == set(MARKETS)


@pytest.mark.parametrize("key", list(MARKETS))
def test_get_market_calendar_returns_cached_calendar(key):
    cal_a = get_market_calendar(key)
    cal_b = get_market_calendar(key)
    assert cal_a is cal_b  # cached at import / memoized


def test_unknown_key_falls_back_to_us_equity():
    assert get_market_calendar("nonsense") is get_market_calendar("us_equity")
