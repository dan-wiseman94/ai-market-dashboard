import pytest

from apps.profiles.models import TradingProfile
from apps.regime.models import RegimeReading
from apps.threads.coach import _regime_block, assemble_coach_context_for_message

pytestmark = pytest.mark.django_db


def test_regime_block_empty_when_no_reading():
    assert _regime_block() == ""


def test_regime_block_renders_latest():
    RegimeReading.objects.create(
        composite="Risk-Off",
        axes={"volatility": "Elevated"},
        drivers=["VIX 24 — Elevated", "SPX trend Downtrend"],
    )
    block = _regime_block()
    assert "Risk-Off" in block
    assert "VIX 24" in block


def test_bare_chat_coach_includes_regime(monkeypatch):
    RegimeReading.objects.create(composite="Stress", axes={}, drivers=["VIX 35 — Stress"])
    profile = TradingProfile.objects.create(name="t", style="", enable_coach=True)
    out = assemble_coach_context_for_message("what's the setup today?", profile)
    assert "Stress" in out
