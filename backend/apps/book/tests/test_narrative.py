import pytest

from apps.book.services import narrative as N

pytestmark = pytest.mark.django_db

DATA = {
    "concentration": {"hhi": 0.4, "top_n_share": 0.7, "net_long": 11, "net_short": -2},
    "regime_fit": {"alignment": "misaligned", "note": "net-long into risk-off"},
    "clusters": [{"members": ["NVDA", "AMD"], "avg_corr": 0.9}],
    "exposures": [],
    "near_invalidation": [],
}


def test_no_provider_config_returns_empty():
    assert N.book_narrative(DATA) == ""


def test_returns_summary_when_ok(monkeypatch):
    from apps.secrets.models import ProviderConfig

    ProviderConfig.objects.create(
        provider="claude", _api_key={"k": "sk-test"}, default_model="claude-opus-4-8"
    )

    class _R:
        summary = "Concentrated, net-long into a risk-off tape."

    monkeypatch.setattr(N, "run_structured", lambda **kw: _R())
    monkeypatch.setattr(N, "ensure_within_caps", lambda target: None)
    assert "Concentrated" in N.book_narrative(DATA)


def test_error_degrades(monkeypatch):
    from apps.secrets.models import ProviderConfig

    ProviderConfig.objects.create(
        provider="claude", _api_key={"k": "sk-test"}, default_model="claude-opus-4-8"
    )

    def _boom(**kw):
        raise RuntimeError("x")

    monkeypatch.setattr(N, "run_structured", _boom)
    monkeypatch.setattr(N, "ensure_within_caps", lambda target: None)
    assert N.book_narrative(DATA) == ""


def test_openai_only_config_produces_summary(monkeypatch):
    from apps.secrets.models import ProviderConfig

    ProviderConfig.objects.create(
        provider="openai", _api_key={"k": "sk-oai"}, default_model="gpt-5.6-sol"
    )
    captured = {}

    class _R:
        summary = "one paragraph"

    monkeypatch.setattr(N, "run_structured", lambda **kw: captured.update(kw) or _R())
    assert N.book_narrative(DATA) == "one paragraph"
    assert captured["provider"] == "openai"
    assert captured["model"] == "gpt-5.6-sol"
