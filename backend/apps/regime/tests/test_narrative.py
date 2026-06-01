import pytest

from apps.regime.services import narrative as N

pytestmark = pytest.mark.django_db

AXES = {"volatility": "Elevated", "trend": "Downtrend"}
DRIVERS = ["VIX 24 — Elevated", "SPX trend Downtrend"]


def test_no_claude_config_returns_empty():
    assert N.regime_narrative("Risk-Off", AXES, DRIVERS) == ""


def test_returns_summary_when_provider_ok(monkeypatch):
    from apps.secrets.models import ProviderConfig

    ProviderConfig.objects.create(
        provider="claude", _api_key={"k": "sk-test"}, default_model="claude-opus-4-8"
    )

    class _Report:
        summary = "Risk-off: volatility elevated, trend rolling over."

    monkeypatch.setattr(N, "run_structured", lambda **kw: _Report())
    monkeypatch.setattr(N, "check_daily_cap", lambda *a, **k: None)
    monkeypatch.setattr(N, "check_monthly_cap", lambda *a, **k: None)
    out = N.regime_narrative("Risk-Off", AXES, DRIVERS)
    assert "Risk-off" in out


def test_provider_error_degrades_to_empty(monkeypatch):
    from apps.secrets.models import ProviderConfig

    ProviderConfig.objects.create(
        provider="claude", _api_key={"k": "sk-test"}, default_model="claude-opus-4-8"
    )

    def _boom(**kw):
        raise RuntimeError("upstream 500")

    monkeypatch.setattr(N, "run_structured", _boom)
    monkeypatch.setattr(N, "check_daily_cap", lambda *a, **k: None)
    monkeypatch.setattr(N, "check_monthly_cap", lambda *a, **k: None)
    assert N.regime_narrative("Risk-Off", AXES, DRIVERS) == ""
