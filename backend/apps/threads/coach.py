"""Decision Coach: a base observational system prompt + an auto-assembled,
stateful "what you already know" context block.

`build_system_prompt` is pure (profile + clock). `assemble_coach_context`
(added in a later task) composes prior theses / diff-vs-last / track record /
recall and uses LAZY, function-local cross-app imports so importing this module
from `apps.threads` never triggers the documented threads -> thesis cycle.
"""

from __future__ import annotations

import logging
from datetime import datetime
from zoneinfo import ZoneInfo

from django.conf import settings

log = logging.getLogger(__name__)

_BASE_FRAMING = (
    "You are a market-observation assistant for one experienced trader.\n"
    "{when}\n\n"
    "Your role is strictly observational: describe what the data shows, surface "
    "what's notable, reason about scenarios. Do NOT issue buy/sell/hold directives.\n\n"
    "Ground every claim in the specific data you were given and name which section "
    "it came from. Explicitly flag data that is missing, stale, or pruned. Quantify "
    "your confidence and state what would invalidate your read."
)


def _when_line(now: datetime) -> str:
    """'Today is <local date/time>; US equity markets are OPEN|CLOSED.'

    Localized to OBSERVER_BEAT_TIMEZONE (the repo's display-tz convention).
    Entirely best-effort: any failure (bad tz setting, calendar error) degrades
    to a date-only line so build_system_prompt never raises.
    """
    try:
        tz = ZoneInfo(getattr(settings, "OBSERVER_BEAT_TIMEZONE", "UTC") or "UTC")
        stamp = now.astimezone(tz).strftime("%A %Y-%m-%d, %H:%M %Z")
        from apps.market.calendar.sessions import market_state

        st = market_state(market="us_equity", at=now)
        return f"Today is {stamp}; US equity markets are {'OPEN' if st.is_open else 'CLOSED'}."
    except Exception:
        log.warning("coach.session_lookup_failed", exc_info=True)
        return f"Today is {now.strftime('%Y-%m-%d')}."


def build_system_prompt(profile, *, now: datetime) -> str:
    """Base framing + current date/session, wrapping `profile.style`.

    Returns just `profile.style` (legacy behavior) when `profile` is None or
    `enable_coach` is False. Never raises.
    """
    style = (getattr(profile, "style", "") or "") if profile is not None else ""
    if profile is None or not getattr(profile, "enable_coach", False):
        return style
    framing = _BASE_FRAMING.format(when=_when_line(now))
    if style.strip():
        return f"{framing}\n\n## Your trading style\n{style}"
    return framing
