from datetime import timedelta
from decimal import Decimal
from unittest.mock import patch

import pytest
from django.utils import timezone

from apps.observer.briefing.services import assemble as A
from apps.observer.models import BriefingConfig, BriefingRun
from apps.thesis.models import Thesis


def test_pct_move():
    assert A._pct_move(100, 110) == 10.0
    assert A._pct_move(100, 90) == -10.0
    assert A._pct_move(None, 110) is None
    assert A._pct_move(0, 110) is None


@pytest.mark.django_db
def test_theses_section_computes_distances():
    Thesis.objects.create(
        title="t",
        ticker="NVDA",
        direction="bullish",
        target_price=Decimal("110"),
        invalidation_price=Decimal("90"),
        status="open",
    )
    with patch(
        "apps.observer.briefing.services.assemble.fetch_quotes",
        return_value={"NVDA": {"last": 100.0}},
    ):
        rows = A._theses_section()
    assert rows[0]["ticker"] == "NVDA"
    assert rows[0]["current"] == 100.0
    assert rows[0]["pct_to_target"] == 10.0
    assert rows[0]["pct_to_invalidation"] == -10.0


@pytest.mark.django_db
def test_since_uses_prior_ready_run_else_24h():
    s1 = A._since()
    assert s1 < timezone.now() - timedelta(hours=23)
    prev = BriefingRun.objects.create(status="ready")
    assert A._since() == prev.created_at


@pytest.mark.django_db
def test_assemble_combines_sections_and_captures_snapshot():
    cfg = BriefingConfig.load()
    with (
        patch(
            "apps.observer.briefing.services.assemble._theses_section",
            return_value=[{"ticker": "NVDA"}],
        ),
        patch(
            "apps.observer.briefing.services.assemble.upcoming_events",
            return_value={"earnings": [], "macro": [{"kind": "cpi"}]},
        ),
        patch("apps.observer.briefing.services.assemble._triggers_section", return_value=[]),
        patch("apps.observer.briefing.services.assemble._news_section", return_value=[]),
        patch(
            "apps.observer.briefing.services.assemble._capture_market",
            return_value=(None, {"vix_last": 18.2}),
        ),
    ):
        data, _snap = A.assemble(cfg)
    assert data["theses"] == [{"ticker": "NVDA"}]
    assert data["events"]["macro"][0]["kind"] == "cpi"
    assert data["market"]["vix_last"] == 18.2
    assert "since" in data


@pytest.mark.django_db
def test_assemble_never_raises_when_a_section_fails():
    cfg = BriefingConfig.load()
    with (
        patch(
            "apps.observer.briefing.services.assemble._watchlist_union",
            side_effect=RuntimeError("db down"),
        ),
        patch("apps.observer.briefing.services.assemble._capture_market", return_value=(None, {})),
        patch(
            "apps.observer.briefing.services.assemble._theses_section",
            side_effect=RuntimeError("boom"),
        ),
        patch(
            "apps.observer.briefing.services.assemble.upcoming_events",
            side_effect=RuntimeError("boom"),
        ),
        patch(
            "apps.observer.briefing.services.assemble._triggers_section",
            side_effect=RuntimeError("boom"),
        ),
        patch(
            "apps.observer.briefing.services.assemble._news_section",
            side_effect=RuntimeError("boom"),
        ),
    ):
        data, _snap = A.assemble(cfg)
    assert data["theses"] == [] and data["events"] == {"earnings": [], "macro": []}
    assert data["triggers"] == [] and data["news"] == []
    assert "since" in data
