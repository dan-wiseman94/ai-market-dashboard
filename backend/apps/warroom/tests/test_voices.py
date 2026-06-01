import pytest

from apps.warroom.services.voices import assign_voices

pytestmark = pytest.mark.django_db


def test_single_mode_all_default(monkeypatch):
    monkeypatch.setattr(
        "apps.warroom.services.voices._enabled_providers", lambda: [("claude", "claude-opus-4-8")]
    )
    out = assign_voices("single")
    assert {p for _persona, p, _m in out} == {"claude"}
    assert [persona for persona, _p, _m in out] == ["bull", "bear", "skeptic"]


def test_multi_mode_spreads_across_providers(monkeypatch):
    monkeypatch.setattr(
        "apps.warroom.services.voices._enabled_providers",
        lambda: [("claude", "claude-opus-4-8"), ("openai", "gpt-5")],
    )
    out = assign_voices("multi")
    provs = [p for _persona, p, _m in out]
    assert len(set(provs)) > 1  # spread across providers


def test_multi_with_one_provider_falls_back(monkeypatch):
    monkeypatch.setattr(
        "apps.warroom.services.voices._enabled_providers", lambda: [("claude", "claude-opus-4-8")]
    )
    out = assign_voices("multi")
    assert {p for _persona, p, _m in out} == {"claude"}


def test_no_providers_returns_empty_assignments(monkeypatch):
    monkeypatch.setattr("apps.warroom.services.voices._enabled_providers", lambda: [])
    out = assign_voices("single")
    assert [persona for persona, _p, _m in out] == ["bull", "bear", "skeptic"]
    assert all(prov == "" for _persona, prov, _m in out)
