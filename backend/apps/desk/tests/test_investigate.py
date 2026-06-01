import pytest

from apps.desk.services import investigate as I

pytestmark = pytest.mark.django_db

CAND = {"anomaly_type": "price_move", "ticker": "NVDA", "severity": 8.0, "evidence": {"pct_change": 8.0}}


def test_no_key_returns_none():
    assert I.investigate(CAND) is None


def test_investigate_returns_finding(monkeypatch):
    from apps.secrets.models import ProviderConfig

    ProviderConfig.objects.create(provider="claude", _api_key={"k": "sk"}, default_model="claude-opus-4-8")

    class _F:
        summary = "NVDA gapped on capex headlines."
        implication = "Watch the breakout retest."
        suggested_actions = ["Convene a War Room on NVDA"]

    monkeypatch.setattr(I, "run_structured", lambda **kw: _F())
    monkeypatch.setattr(I, "check_daily_cap", lambda *a, **k: None)
    monkeypatch.setattr(I, "check_monthly_cap", lambda *a, **k: None)
    out = I.investigate(CAND)
    assert out["finding"].startswith("NVDA")
    assert out["suggested_actions"]
    # the first action is the executable convene_warroom
    assert out["suggested_actions"][0]["type"] == "convene_warroom"
