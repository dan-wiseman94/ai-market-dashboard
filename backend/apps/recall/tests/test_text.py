import pytest

from apps.profiles.models import TradingProfile
from apps.recall.text import build_text, content_hash, extract_tickers
from apps.thesis.models import Thesis


@pytest.mark.django_db
def test_thesis_text_and_tickers():
    p = TradingProfile.objects.create(name="P", default_includes=["quotes"])
    th = Thesis.objects.create(
        title="NVDA run", ticker="NVDA", direction="bullish", rationale="AI demand", profile=p
    )
    assert "NVDA run" in build_text("thesis", th) and "AI demand" in build_text("thesis", th)
    assert extract_tickers("thesis", th) == ["NVDA"]


def test_content_hash_stable():
    assert content_hash("abc") == content_hash("abc") and content_hash("abc") != content_hash("abd")
