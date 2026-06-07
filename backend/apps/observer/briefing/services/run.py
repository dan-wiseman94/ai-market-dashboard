"""Orchestrate one briefing: assemble data, persist, post the AI synthesis, notify."""

from __future__ import annotations

import logging
from datetime import date, datetime
from zoneinfo import ZoneInfo

from django.conf import settings
from django.db import IntegrityError, transaction
from django.utils import timezone

from apps.observer.briefing.services.assemble import assemble
from apps.observer.models import BriefingConfig, BriefingRun
from apps.observer.services.notifications import notify
from apps.profiles.models import TradingProfile
from apps.threads.models import Message, Thread
from apps.threads.tasks import run_ai_on_message

log = logging.getLogger(__name__)


def _now_local() -> datetime:
    tz = ZoneInfo(getattr(settings, "OBSERVER_BEAT_TIMEZONE", "UTC"))
    return timezone.now().astimezone(tz)


def _local_today() -> date:
    return _now_local().date()


def get_or_create_briefing_thread(profile: TradingProfile) -> Thread:
    obj, _ = Thread.objects.get_or_create(
        profile=profile, kind="briefing", defaults={"title": "Morning briefing"}
    )
    return obj


def _fmt(v, suffix="") -> str:
    return "—" if v is None else f"{v}{suffix}"


def render_briefing_markdown(data: dict) -> str:
    lines = [
        "You are writing a concise morning market briefing. Synthesize what matters most "
        "today in 3-6 sentences; lead with the single most actionable item. Do not restate "
        "every row — interpret. Here is today's data:\n",
    ]
    theses = data.get("theses") or []
    if theses:
        lines.append("## Open theses")
        for t in theses:
            lines.append(
                f"- {t.get('ticker')} {t.get('direction')} (conv {t.get('conviction')}): "
                f"now {_fmt(t.get('current'))}, →target {_fmt(t.get('pct_to_target'), '%')}, "
                f"→invalidation {_fmt(t.get('pct_to_invalidation'), '%')}"
            )
    events = data.get("events") or {}
    earn, macro = events.get("earnings") or [], events.get("macro") or []
    if earn or macro:
        lines.append("## Upcoming events")
        for e in earn:
            lines.append(f"- {e.get('ticker')} earnings in {e.get('days_until')}d")
        for m in macro:
            lines.append(f"- {m.get('title') or m.get('kind')} in {m.get('days_until')}d")
    trig = data.get("triggers") or []
    if trig:
        lines.append("## Triggers fired overnight")
        lines += [f"- {t.get('name')}: {t.get('summary')}" for t in trig]
    news = data.get("news") or []
    if news:
        lines.append("## Overnight news")
        lines += [f"- {n.get('headline')} ({n.get('source')})" for n in news[:10]]
    market = data.get("market") or {}
    if market:
        lines.append(
            f"## Market: SPX {_fmt(market.get('spx_last'))}, QQQ {_fmt(market.get('qqq_last'))}, "
            f"VIX {_fmt(market.get('vix_last'))}"
        )
    return "\n".join(lines)


def _one_line_summary(data: dict) -> str:
    n_theses = len(data.get("theses") or [])
    n_trig = len(data.get("triggers") or [])
    return f"{n_theses} open theses · {n_trig} triggers fired overnight"


def run_briefing(*, scheduled: bool) -> BriefingRun | None:
    cfg = BriefingConfig.load()
    if scheduled:
        try:
            with transaction.atomic():
                run = BriefingRun.objects.create(scheduled_date=_local_today(), status="assembling")
        except IntegrityError:
            return None
    else:
        run = BriefingRun.objects.create(scheduled_date=None, status="assembling")

    try:
        data, snapshot = assemble(cfg)
    except Exception as exc:
        log.exception("briefing.assemble_failed")
        run.status, run.error = "failed", str(exc)
        run.save(update_fields=["status", "error"])
        return run

    run.data, run.snapshot, run.status = data, snapshot, "ready"
    run.save()

    profile = cfg.profile or TradingProfile.objects.first()
    if profile is not None:
        thread = get_or_create_briefing_thread(profile)
        msg = Message.objects.create(
            thread=thread,
            role="user",
            content={"text": render_briefing_markdown(data)},
            snapshot_ref=snapshot,
            status="done",
        )
        run.synthesis_message = msg
        run.save(update_fields=["synthesis_message"])
        run_ai_on_message.delay(thread_id=thread.id, user_message_id=msg.id)

    notify(
        user_id=None,
        kind="briefing",
        title="Your morning briefing is ready",
        body=_one_line_summary(data),
        link="/briefing",
    )
    return run
