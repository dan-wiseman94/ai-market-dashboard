import pytest

from apps.strategy.regime.services import narrative as N

pytestmark = pytest.mark.django_db

AXES = {"volatility": "Elevated", "trend": "Downtrend"}
DRIVERS = ["VIX 24 — Elevated", "SPX trend Downtrend"]


def test_no_provider_config_returns_empty():
    assert N.regime_narrative("Risk-Off", AXES, DRIVERS) == ""


def test_returns_summary_when_provider_ok(monkeypatch):
    from apps.secrets.models import ProviderConfig

    ProviderConfig.objects.create(
        provider="claude", _api_key={"k": "sk-test"}, default_model="claude-opus-4-8"
    )

    class _Report:
        summary = "Risk-off: volatility elevated, trend rolling over."

    monkeypatch.setattr(N, "run_structured", lambda **kw: _Report())
    monkeypatch.setattr(N, "ensure_within_caps", lambda target: None)
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
    monkeypatch.setattr(N, "ensure_within_caps", lambda target: None)
    assert N.regime_narrative("Risk-Off", AXES, DRIVERS) == ""


def test_openai_only_config_produces_summary(monkeypatch):
    from apps.secrets.models import ProviderConfig

    ProviderConfig.objects.create(
        provider="openai", _api_key={"k": "sk-oai"}, default_model="gpt-5.6-sol"
    )
    captured = {}

    class _R:
        summary = "one paragraph"

    monkeypatch.setattr(N, "run_structured", lambda **kw: captured.update(kw) or _R())
    assert N.regime_narrative("Risk-Off", AXES, DRIVERS) == "one paragraph"
    assert captured["provider"] == "openai"
    assert captured["model"] == "gpt-5.6-sol"
