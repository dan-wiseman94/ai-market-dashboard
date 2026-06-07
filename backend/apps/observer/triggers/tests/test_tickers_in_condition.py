from apps.observer.triggers.dsl import tickers_in_condition


def test_collects_nested_tickers():
    cond = {
        "all": [
            {"metric": "price", "ticker": "SPY", "op": ">", "value": 1},
            {
                "any": [
                    {"metric": "price", "ticker": "BTC-USD", "op": ">", "value": 1},
                    {
                        "not": {
                            "metric": "pct_change",
                            "ticker": "QQQ",
                            "op": ">",
                            "value": 1,
                            "window": "1d",
                        }
                    },
                ]
            },
            {"metric": "vix", "op": ">", "value": 20},  # no ticker
        ]
    }
    assert tickers_in_condition(cond) == {"SPY", "BTC-USD", "QQQ"}


def test_empty_for_tickerless():
    assert tickers_in_condition({"metric": "vix", "op": ">", "value": 1}) == set()
