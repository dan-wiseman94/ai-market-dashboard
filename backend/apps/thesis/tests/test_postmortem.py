"""Tests for the Phase-2 post-mortem scheduler + AI replay.

Covers the deterministic verdict truth table, scheduling idempotency, the
beat-task dispatch filter, the degradation contract (no key => objective verdict
still recorded, never raises), the AI happy path (run_structured mocked, NOT
MOCK_EXTERNAL), create() auto-scheduling, and the run-now endpoint.
"""

from __future__ import annotations

from datetime import timedelta
from unittest.mock import patch

import pytest
from django.test import override_settings
from django.utils import timezone
from rest_framework.test import APIClient

from apps.market.models import OHLCBar
from apps.profiles.models import TradingProfile
from apps.secrets.models import ProviderConfig
from apps.thesis.models import PostMortem, Thesis
from apps.thesis.schemas import PostMortemReport
from apps.thesis.services import postmortem as pm_service
from apps.thesis.services.postmortem import (
    DEADZONE,
    _build_prompt,
    objective_verdict,
    run_postmortem,
    schedule_postmortems,
)
from apps.threads.models import Message

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def api():
    return APIClient()


@pytest.fixture
def profile(db):
    return TradingProfile.objects.create(
        name="PM Profile", style="swing trader", default_provider="claude"
    )


@pytest.fixture
def thesis(db, profile):
    # Opened well in the past so all horizons are due.
    return Thesis.objects.create(
        title="Long AAPL",
        ticker="AAPL",
        direction="bullish",
        conviction=4,
        rationale="breakout setup",
        profile=profile,
        opened_at=timezone.now() - timedelta(days=120),
    )


def _seed_bars(ticker: str, start, *, start_close: float, end_close: float, end) -> None:
    """Seed two daily OHLC bars so forward_return_pct is computable."""
    OHLCBar.objects.create(
        ticker=ticker,
        timeframe="1d",
        open=start_close,
        high=start_close,
        low=start_close,
        close=start_close,
        volume=1_000_000,
        ts=start,
    )
    OHLCBar.objects.create(
        ticker=ticker,
        timeframe="1d",
        open=end_close,
        high=end_close,
        low=end_close,
        close=end_close,
        volume=1_000_000,
        ts=end,
    )


# ---------------------------------------------------------------------------
# objective_verdict truth table
# ---------------------------------------------------------------------------


def _thesis(direction: str) -> Thesis:
    return Thesis(title="x", ticker="X", direction=direction)


@pytest.mark.parametrize(
    ("direction", "fwd", "expected"),
    [
        # None => inconclusive regardless of direction
        ("bullish", None, "inconclusive"),
        ("bearish", None, "inconclusive"),
        ("neutral", None, "inconclusive"),
        # bullish
        ("bullish", 5.0, "correct"),  # strong up
        ("bullish", -5.0, "incorrect"),  # strong down
        ("bullish", 0.5, "mixed"),  # within deadzone
        ("bullish", DEADZONE, "correct"),  # boundary inclusive
        ("bullish", -DEADZONE, "incorrect"),  # boundary inclusive
        ("bullish", 0.999, "mixed"),  # just inside deadzone
        # bearish
        ("bearish", -5.0, "correct"),  # strong down
        ("bearish", 5.0, "incorrect"),  # strong up
        ("bearish", -0.5, "mixed"),  # within deadzone
        ("bearish", -DEADZONE, "correct"),  # boundary inclusive
        ("bearish", DEADZONE, "incorrect"),  # boundary inclusive
        ("bearish", 0.5, "mixed"),
        # neutral
        ("neutral", 0.0, "correct"),  # flat => correct
        ("neutral", 0.5, "correct"),  # inside deadzone
        ("neutral", DEADZONE, "correct"),  # boundary inclusive
        ("neutral", -DEADZONE, "correct"),  # boundary inclusive (abs)
        ("neutral", 5.0, "incorrect"),  # big move => wrong
        ("neutral", -5.0, "incorrect"),
        ("neutral", 1.001, "incorrect"),  # just outside deadzone
    ],
)
def test_objective_verdict_truth_table(direction, fwd, expected):
    assert objective_verdict(_thesis(direction), fwd) == expected


# ---------------------------------------------------------------------------
# schedule_postmortems
# ---------------------------------------------------------------------------


@pytest.mark.django_db
def test_schedule_postmortems_creates_one_per_horizon(thesis):
    schedule_postmortems(thesis)
    pms = PostMortem.objects.filter(thesis=thesis).order_by("horizon_days")
    horizons = [pm.horizon_days for pm in pms]
    assert horizons == [7, 30, 90]
    for pm in pms:
        assert pm.due_at == thesis.opened_at + timedelta(days=pm.horizon_days)
        assert pm.status == "scheduled"


@pytest.mark.django_db
def test_schedule_postmortems_idempotent(thesis):
    schedule_postmortems(thesis)
    schedule_postmortems(thesis)  # second call must not duplicate
    assert PostMortem.objects.filter(thesis=thesis).count() == 3


@override_settings(THESIS_POSTMORTEM_HORIZONS=[1, 14])
@pytest.mark.django_db
def test_schedule_postmortems_respects_settings(thesis):
    schedule_postmortems(thesis)
    assert sorted(
        PostMortem.objects.filter(thesis=thesis).values_list("horizon_days", flat=True)
    ) == [1, 14]


# ---------------------------------------------------------------------------
# run_due_postmortems beat task — only scheduled+due get dispatched
# ---------------------------------------------------------------------------


@pytest.mark.django_db
def test_run_due_postmortems_dispatches_only_due_scheduled(thesis):
    from apps.thesis.tasks import run_due_postmortems

    now = timezone.now()
    due = PostMortem.objects.create(
        thesis=thesis, horizon_days=7, due_at=now - timedelta(days=1), status="scheduled"
    )
    future = PostMortem.objects.create(
        thesis=thesis, horizon_days=30, due_at=now + timedelta(days=30), status="scheduled"
    )
    already_done = PostMortem.objects.create(
        thesis=thesis, horizon_days=90, due_at=now - timedelta(days=1), status="done"
    )

    with patch("apps.thesis.tasks.run_postmortem_task.delay") as mock_delay:
        result = run_due_postmortems()

    assert result == {"dispatched": 1}
    dispatched_ids = {call.args[0] for call in mock_delay.call_args_list}
    assert dispatched_ids == {due.id}
    assert future.id not in dispatched_ids
    assert already_done.id not in dispatched_ids


# ---------------------------------------------------------------------------
# run_postmortem — degradation contract (no key / non-claude)
# ---------------------------------------------------------------------------


@pytest.mark.django_db
def test_run_postmortem_no_provider_records_objective_and_does_not_raise(thesis):
    """No ProviderConfig at all: objective verdict + return recorded, report={}."""
    pm = PostMortem.objects.create(
        thesis=thesis,
        horizon_days=7,
        due_at=thesis.opened_at + timedelta(days=7),
        status="scheduled",
    )
    # AAPL +10% over the window => bullish thesis is "correct".
    _seed_bars(
        "AAPL",
        thesis.opened_at,
        start_close=100.0,
        end_close=110.0,
        end=pm.due_at,
    )

    run_postmortem(pm.id)  # must not raise

    pm.refresh_from_db()
    assert pm.status == "done"
    assert pm.completed_at is not None
    assert pm.forward_return_pct == pytest.approx(10.0)
    assert pm.verdict == "correct"
    assert pm.report == {}
    assert pm.message is None


@pytest.mark.django_db
def test_run_postmortem_non_claude_provider_skips_ai(thesis):
    """Profile points at openai: no AI narrative, but objective still recorded."""
    thesis.profile.default_provider = "openai"
    thesis.profile.save()
    ProviderConfig.objects.create(provider="openai", enabled=True)

    pm = PostMortem.objects.create(
        thesis=thesis,
        horizon_days=7,
        due_at=thesis.opened_at + timedelta(days=7),
        status="scheduled",
    )
    _seed_bars("AAPL", thesis.opened_at, start_close=100.0, end_close=90.0, end=pm.due_at)

    with patch.object(pm_service, "run_structured") as mock_run:
        run_postmortem(pm.id)

    mock_run.assert_not_called()
    pm.refresh_from_db()
    assert pm.status == "done"
    assert pm.forward_return_pct == pytest.approx(-10.0)
    assert pm.verdict == "incorrect"  # bullish thesis, price fell
    assert pm.report == {}


@pytest.mark.django_db
def test_run_postmortem_claude_no_key_skips_ai(thesis):
    """Claude config exists but api_key is blank: skip AI, record objective."""
    ProviderConfig.objects.create(provider="claude", enabled=True)  # no api_key

    pm = PostMortem.objects.create(
        thesis=thesis,
        horizon_days=7,
        due_at=thesis.opened_at + timedelta(days=7),
        status="scheduled",
    )
    _seed_bars("AAPL", thesis.opened_at, start_close=100.0, end_close=105.0, end=pm.due_at)

    with patch.object(pm_service, "run_structured") as mock_run:
        run_postmortem(pm.id)

    mock_run.assert_not_called()
    pm.refresh_from_db()
    assert pm.verdict == "correct"
    assert pm.report == {}


@pytest.mark.django_db
def test_run_postmortem_no_bars_inconclusive(thesis):
    """No OHLC data => forward return None => inconclusive, still done."""
    pm = PostMortem.objects.create(
        thesis=thesis,
        horizon_days=7,
        due_at=thesis.opened_at + timedelta(days=7),
        status="scheduled",
    )
    run_postmortem(pm.id)
    pm.refresh_from_db()
    assert pm.status == "done"
    assert pm.forward_return_pct is None
    assert pm.verdict == "inconclusive"
    assert pm.report == {}


@pytest.mark.django_db
def test_run_postmortem_provider_error_does_not_raise(thesis):
    """run_structured raising must NOT abort the objective bookkeeping."""
    cfg = ProviderConfig.objects.create(provider="claude", enabled=True)
    cfg.api_key = "sk-test"
    cfg.save()

    pm = PostMortem.objects.create(
        thesis=thesis,
        horizon_days=7,
        due_at=thesis.opened_at + timedelta(days=7),
        status="scheduled",
    )
    _seed_bars("AAPL", thesis.opened_at, start_close=100.0, end_close=120.0, end=pm.due_at)

    with patch.object(pm_service, "run_structured", side_effect=RuntimeError("boom")):
        run_postmortem(pm.id)  # must not raise

    pm.refresh_from_db()
    assert pm.status == "done"
    assert pm.verdict == "correct"
    assert pm.report == {}
    assert pm.message is None


# ---------------------------------------------------------------------------
# run_postmortem — AI happy path (run_structured mocked, NOT MOCK_EXTERNAL)
# ---------------------------------------------------------------------------


@pytest.fixture
def fake_report() -> PostMortemReport:
    return PostMortemReport(
        summary="The breakout held and ran to target.",
        what_worked=["entry timing", "trend alignment"],
        what_missed=["sized too small"],
        lessons=["press winners"],
        would_repeat=True,
    )


@pytest.mark.django_db
def test_run_postmortem_ai_path_populates_report_and_posts_message(thesis, fake_report):
    cfg = ProviderConfig.objects.create(provider="claude", enabled=True)
    cfg.api_key = "sk-test"
    cfg.save()

    pm = PostMortem.objects.create(
        thesis=thesis,
        horizon_days=30,
        due_at=thesis.opened_at + timedelta(days=30),
        status="scheduled",
    )
    _seed_bars("AAPL", thesis.opened_at, start_close=100.0, end_close=115.0, end=pm.due_at)

    with patch.object(pm_service, "run_structured", return_value=fake_report) as mock_run:
        run_postmortem(pm.id)

    mock_run.assert_called_once()
    pm.refresh_from_db()
    assert pm.status == "done"
    assert pm.forward_return_pct == pytest.approx(15.0)
    assert pm.verdict == "correct"
    # Report populated from the mocked structured output.
    assert pm.report["summary"] == fake_report.summary
    assert pm.report["would_repeat"] is True
    # The verdict is deterministic (objective_verdict), not an AI-emitted field.
    assert "narrative_verdict" not in pm.report

    # An assistant Message was posted into the per-thesis review thread.
    assert pm.message is not None
    msg = pm.message
    assert msg.role == "assistant"
    assert msg.status == "done"
    assert msg.content["kind"] == "postmortem_report"
    # horizon_days / verdict / forward_return_pct are read off the PostMortem row
    # (asserted above), not duplicated into the review message.
    assert "verdict" not in msg.content
    assert "forward_return_pct" not in msg.content
    assert "horizon_days" not in msg.content

    # The review thread was linked back onto the thesis.
    thesis.refresh_from_db()
    assert thesis.review_thread_id == msg.thread_id
    assert thesis.review_thread.kind == "consult"


@pytest.mark.django_db
def test_run_postmortem_ai_path_uses_existing_review_thread(thesis, fake_report):
    """A second post-mortem reuses the same per-thesis review thread."""
    from apps.thesis.services.threads import get_or_create_review_thread

    cfg = ProviderConfig.objects.create(provider="claude", enabled=True)
    cfg.api_key = "sk-test"
    cfg.save()

    existing = get_or_create_review_thread(thesis)

    pm = PostMortem.objects.create(
        thesis=thesis,
        horizon_days=7,
        due_at=thesis.opened_at + timedelta(days=7),
        status="scheduled",
    )
    _seed_bars("AAPL", thesis.opened_at, start_close=100.0, end_close=130.0, end=pm.due_at)

    with patch.object(pm_service, "run_structured", return_value=fake_report):
        run_postmortem(pm.id)

    pm.refresh_from_db()
    assert pm.message.thread_id == existing.id


# ---------------------------------------------------------------------------
# create() auto-schedules post-mortems
# ---------------------------------------------------------------------------


@pytest.mark.django_db
def test_create_thesis_schedules_postmortems(api, profile):
    resp = api.post(
        "/api/theses/",
        {
            "title": "Long NVDA",
            "ticker": "nvda",
            "direction": "bullish",
            "profile_id": profile.id,
            "rationale": "AI compute demand",
            "invalidation_note": "breaks below 100",
        },
        format="json",
    )
    assert resp.status_code == 201
    thesis_id = resp.json()["id"]
    pms = PostMortem.objects.filter(thesis_id=thesis_id).order_by("horizon_days")
    assert [pm.horizon_days for pm in pms] == [7, 30, 90]


@pytest.mark.django_db
def test_create_thesis_response_nests_postmortems(api, profile):
    resp = api.post(
        "/api/theses/",
        {
            "title": "Long MSFT",
            "ticker": "MSFT",
            "direction": "bullish",
            "profile_id": profile.id,
            "rationale": "cloud growth",
            "invalidation_note": "breaks below 380",
        },
        format="json",
    )
    assert resp.status_code == 201
    body = resp.json()
    assert "postmortems" in body
    assert len(body["postmortems"]) == 3
    pm = body["postmortems"][0]
    assert pm["status"] == "scheduled"
    assert pm["verdict"] == ""
    assert pm["forward_return_pct"] is None


# ---------------------------------------------------------------------------
# run-now endpoint
# ---------------------------------------------------------------------------


@override_settings(CELERY_TASK_ALWAYS_EAGER=True, CELERY_TASK_EAGER_PROPAGATES=True)
@pytest.mark.django_db
def test_run_now_runs_an_existing_due_postmortem(api, thesis):
    """With a scheduled+due PM, the endpoint runs it (eager) and returns 202."""
    schedule_postmortems(thesis)  # opened 120d ago => all due
    _seed_bars(
        "AAPL",
        thesis.opened_at,
        start_close=100.0,
        end_close=108.0,
        end=thesis.opened_at + timedelta(days=7),
    )

    resp = api.post(f"/api/theses/{thesis.id}/run-postmortem/", format="json")
    assert resp.status_code == 202
    pm_id = resp.json()["postmortem_id"]

    # Earliest due (7d) was chosen and ran eagerly.
    pm = PostMortem.objects.get(id=pm_id)
    assert pm.horizon_days == 7
    assert pm.status == "done"
    assert pm.verdict == "correct"


@override_settings(CELERY_TASK_ALWAYS_EAGER=True, CELERY_TASK_EAGER_PROPAGATES=True)
@pytest.mark.django_db
def test_run_now_creates_adhoc_when_none_scheduled(api, profile):
    """No PMs yet and freshly opened => smallest horizon created + run."""
    thesis = Thesis.objects.create(
        title="fresh", ticker="AAPL", direction="bullish", profile=profile
    )
    PostMortem.objects.filter(thesis=thesis).delete()  # ensure none from create()

    resp = api.post(f"/api/theses/{thesis.id}/run-postmortem/", format="json")
    assert resp.status_code == 202
    pm_id = resp.json()["postmortem_id"]
    pm = PostMortem.objects.get(id=pm_id)
    assert pm.horizon_days == 7  # smallest configured horizon
    assert pm.status == "done"


@pytest.mark.django_db
def test_run_now_404_for_unknown_pk(api):
    resp = api.post("/api/theses/999999/run-postmortem/", format="json")
    assert resp.status_code == 404


# ---------------------------------------------------------------------------
# Idempotency — the atomic status claim makes a second run a no-op
# ---------------------------------------------------------------------------


@pytest.mark.django_db
def test_run_postmortem_is_idempotent_when_already_done(thesis, fake_report):
    """Calling run_postmortem twice exercises the AI once and posts ONE message.

    The second call sees status != "scheduled" (it is now "done") and bails on
    the atomic claim before touching the AI path — no duplicate review message,
    no second $ charge.
    """
    cfg = ProviderConfig.objects.create(provider="claude", enabled=True)
    cfg.api_key = "sk-test"
    cfg.save()

    pm = PostMortem.objects.create(
        thesis=thesis,
        horizon_days=30,
        due_at=thesis.opened_at + timedelta(days=30),
        status="scheduled",
    )
    _seed_bars("AAPL", thesis.opened_at, start_close=100.0, end_close=115.0, end=pm.due_at)

    with patch.object(pm_service, "run_structured", return_value=fake_report) as mock_run:
        run_postmortem(pm.id)  # first run: claims, runs AI, posts message
        run_postmortem(pm.id)  # second run: status is "done" → no-op

    # The AI path ran exactly once.
    mock_run.assert_called_once()

    pm.refresh_from_db()
    assert pm.status == "done"

    # Exactly ONE assistant message exists in the review thread — not two.
    thesis.refresh_from_db()
    msgs = Message.objects.filter(thread=thesis.review_thread, role="assistant")
    assert msgs.count() == 1
    assert pm.message_id == msgs.first().id


@pytest.mark.django_db
def test_run_postmortem_noop_when_already_running(thesis, fake_report):
    """A row forced to "running" (e.g. concurrent claim) is not re-run."""
    cfg = ProviderConfig.objects.create(provider="claude", enabled=True)
    cfg.api_key = "sk-test"
    cfg.save()

    pm = PostMortem.objects.create(
        thesis=thesis,
        horizon_days=30,
        due_at=thesis.opened_at + timedelta(days=30),
        status="running",  # simulate a claim already taken by another worker
    )
    _seed_bars("AAPL", thesis.opened_at, start_close=100.0, end_close=115.0, end=pm.due_at)

    with patch.object(pm_service, "run_structured", return_value=fake_report) as mock_run:
        run_postmortem(pm.id)

    # Claim filter (status="scheduled") did not match → AI never ran.
    mock_run.assert_not_called()
    pm.refresh_from_db()
    assert pm.status == "running"  # untouched
    assert pm.verdict == ""
    assert pm.report == {}
    assert Message.objects.filter(thread=thesis.review_thread).count() == 0


# ---------------------------------------------------------------------------
# Null-profile provider fallback — resolve claude via ProviderConfig
# ---------------------------------------------------------------------------


@pytest.mark.django_db
def test_run_postmortem_null_profile_falls_back_to_provider_config(db, fake_report):
    """thesis.profile is None → provider resolves from the single ProviderConfig."""
    thesis = Thesis.objects.create(
        title="No-profile call",
        ticker="AAPL",
        direction="bullish",
        conviction=3,
        profile=None,
        opened_at=timezone.now() - timedelta(days=120),
    )
    cfg = ProviderConfig.objects.create(provider="claude", enabled=True)
    cfg.api_key = "sk-test"
    cfg.save()

    pm = PostMortem.objects.create(
        thesis=thesis,
        horizon_days=7,
        due_at=thesis.opened_at + timedelta(days=7),
        status="scheduled",
    )
    _seed_bars("AAPL", thesis.opened_at, start_close=100.0, end_close=112.0, end=pm.due_at)

    with patch.object(pm_service, "run_structured", return_value=fake_report) as mock_run:
        run_postmortem(pm.id)  # must not crash with profile=None

    mock_run.assert_called_once()
    pm.refresh_from_db()
    assert pm.status == "done"
    assert pm.verdict == "correct"  # bullish, +12%
    # Report populated via the ProviderConfig fallback (no profile to read from).
    assert pm.report["summary"] == fake_report.summary
    assert pm.message is not None


# ---------------------------------------------------------------------------
# _build_prompt / notify None formatting — "unavailable", not "None%"
# ---------------------------------------------------------------------------


@pytest.mark.django_db
def test_build_prompt_renders_unavailable_for_none_forward_return(thesis):
    """Forward return None must read 'unavailable', never 'None%'."""
    pm = PostMortem.objects.create(
        thesis=thesis,
        horizon_days=7,
        due_at=thesis.opened_at + timedelta(days=7),
        status="scheduled",
    )
    prompt = _build_prompt(thesis, pm, None, {"return_pct": None})
    assert "unavailable" in prompt
    assert "None%" not in prompt

    # A real value still renders as a percentage.
    prompt_with_value = _build_prompt(thesis, pm, 12.5, {"return_pct": 12.5})
    assert "12.5%" in prompt_with_value


@pytest.mark.django_db
def test_run_postmortem_notify_body_says_unavailable_when_no_bars(thesis):
    """No OHLC data → forward return None → notify body says 'unavailable'."""
    pm = PostMortem.objects.create(
        thesis=thesis,
        horizon_days=7,
        due_at=thesis.opened_at + timedelta(days=7),
        status="scheduled",
    )
    with patch.object(pm_service, "notify") as mock_notify:
        run_postmortem(pm.id)

    mock_notify.assert_called_once()
    body = mock_notify.call_args.kwargs["body"]
    assert "unavailable" in body
    assert "None%" not in body


# ---------------------------------------------------------------------------
# run-now replay — POST twice, both 202, PM ends "done" (not stuck)
# ---------------------------------------------------------------------------


@override_settings(CELERY_TASK_ALWAYS_EAGER=True, CELERY_TASK_EAGER_PROPAGATES=True)
@pytest.mark.django_db
def test_run_now_replay_twice_ends_done(api, thesis):
    """Two run-now POSTs each return 202 and leave their PM "done", not stuck.

    Run-now resets the chosen PM to "scheduled" before dispatch, so each click
    actually runs (never a no-op) and the row never gets stuck in "running".
    The first click consumes the earliest due 7d PM; once that is "done", the
    endpoint picks the next earliest scheduled+due PM (30d) on the second click.
    """
    schedule_postmortems(thesis)  # opened 120d ago => all 7/30/90 due
    # One start bar shared by both horizons (the uniq_bar constraint forbids a
    # duplicate (ticker, timeframe, ts)), plus an end bar at each horizon.
    OHLCBar.objects.create(
        ticker="AAPL",
        timeframe="1d",
        open=100.0,
        high=100.0,
        low=100.0,
        close=100.0,
        volume=1_000_000,
        ts=thesis.opened_at,
    )
    for horizon in (7, 30):
        OHLCBar.objects.create(
            ticker="AAPL",
            timeframe="1d",
            open=108.0,
            high=108.0,
            low=108.0,
            close=108.0,
            volume=1_000_000,
            ts=thesis.opened_at + timedelta(days=horizon),
        )

    resp1 = api.post(f"/api/theses/{thesis.id}/run-postmortem/", format="json")
    assert resp1.status_code == 202
    pm1 = PostMortem.objects.get(id=resp1.json()["postmortem_id"])
    assert pm1.horizon_days == 7  # earliest due chosen first
    assert pm1.status == "done"  # not stuck in "running"
    assert pm1.completed_at is not None

    resp2 = api.post(f"/api/theses/{thesis.id}/run-postmortem/", format="json")
    assert resp2.status_code == 202
    pm2 = PostMortem.objects.get(id=resp2.json()["postmortem_id"])
    assert pm2.status == "done"  # second click also completes cleanly
    assert pm2.completed_at is not None

    # No PM left stuck in the "running" claim state.
    assert not PostMortem.objects.filter(thesis=thesis, status="running").exists()
