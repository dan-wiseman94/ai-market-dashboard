import pytest
from django.utils import timezone

from apps.book.services.var_beta import _beta, compute_var_beta
from apps.market.models import OHLCBar

pytestmark = pytest.mark.django_db


def _make_bars(ticker: str, closes: list[float]) -> None:
    base = timezone.now() - timezone.timedelta(days=len(closes))
    for i, c in enumerate(closes):
        OHLCBar.objects.create(
            ticker=ticker.upper(),
            timeframe="1d",
            open=c,
            high=c,
            low=c,
            close=c,
            volume=1,
            ts=base + timezone.timedelta(days=i),
        )


def test_beta_recovers_exact_slope():
    # asset returns are exactly 2x the market's -> beta == 2.0
    market = [0.001 * (i + 1) for i in range(40)]
    asset = [2.0 * x for x in market]
    assert _beta(asset, market) == pytest.approx(2.0)


def test_compute_var_beta_prices_dollar_positions():
    _make_bars("NVDA", [100 + (i % 7) for i in range(40)])
    _make_bars("AMD", [50 + (i % 5) for i in range(40)])
    _make_bars("$SPX", [400 + (i % 3) for i in range(40)])
    exposures = [
        {"ticker": "NVDA", "dollar": 10000.0, "net_signed": 3, "abs_exposure": 3},
        {"ticker": "AMD", "dollar": -5000.0, "net_signed": -3, "abs_exposure": 3},
        # coverage-only name, no dollar sizing -> not priced
        {"ticker": "TSLA", "dollar": None, "net_signed": 2, "abs_exposure": 2},
    ]
    out = compute_var_beta(exposures)

    assert out["available"] is True
    assert {p["ticker"] for p in out["positions"]} == {"NVDA", "AMD"}
    assert all(p["var_usd"] > 0 for p in out["positions"])
    assert all(p["beta"] is not None for p in out["positions"])

    port = out["portfolio"]
    assert port["gross_dollar"] == pytest.approx(15000.0)
    assert port["net_dollar"] == pytest.approx(5000.0)
    # diversification never increases risk
    assert port["diversified_var_usd"] <= port["undiversified_var_usd"] + 1e-6
    assert port["n_positions"] == 2


def test_compute_var_beta_unavailable_without_dollar_positions():
    out = compute_var_beta([{"ticker": "TSLA", "dollar": None, "net_signed": 2, "abs_exposure": 2}])
    assert out["available"] is False
    assert out["positions"] == []
