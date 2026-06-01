"""Revise the living house view for a ticker (M14 F3).

The hysteresis gate is the model's ``material_change`` flag plus an actual
stance/conviction delta: a ``CoverageRevision`` row + note update happen only
when something earned it, so the house view doesn't churn on noise. Everything
is best-effort — a revision failure (no key, cap, undecryptable cred, AI error)
returns ``None`` and never breaks the fire that triggered it.

``run_structured`` has no ``MOCK_EXTERNAL`` short-circuit; tests patch the name
bound here.
"""

from __future__ import annotations

import logging
from typing import Any

from cryptography.fernet import InvalidToken
from django.utils import timezone

from apps.ai.cost import CostCapExceededError, check_daily_cap, check_monthly_cap
from apps.ai.providers.claude_structured import run_structured
from apps.coverage.models import CoverageNote, CoverageRevision
from apps.coverage.schemas import CoverageRevisionDraft
from apps.secrets.models import ProviderConfig
from apps.snapshots.diff import diff_sections
from apps.snapshots.primary import previous_snapshot_for
from apps.snapshots.serializer import serialize_for_ai
from apps.threads.coach import build_system_prompt

log = logging.getLogger(__name__)


def revise_coverage(ticker: str, snapshot, *, profile) -> CoverageRevision | None:
    """Ask the AI to revise the house view on ``ticker`` given ``snapshot``.

    Returns the new ``CoverageRevision`` when the view materially changed, or
    ``None`` on a reaffirm / skip (no key, cap exceeded, undecryptable cred, AI
    error). Never raises — callers (observer fires, the manual endpoint) treat a
    revision as additive, not load-bearing.
    """
    ticker = ticker.upper()
    provider_name = profile.default_provider

    cfg = ProviderConfig.objects.filter(provider=provider_name).first()
    if cfg is None:
        return None
    try:
        api_key = cfg.api_key
    except InvalidToken:
        # Undecryptable on a key/salt rotation — skip, never crash the caller.
        return None
    if not api_key:
        return None
    try:
        check_daily_cap(provider_name, cap_usd=cfg.daily_cost_cap_usd)
        check_monthly_cap(provider_name, cap_usd=cfg.monthly_cost_cap_usd)
    except CostCapExceededError as exc:
        log.info("coverage: cap exceeded, skipping %s revision: %s", ticker, exc)
        return None

    note, created = CoverageNote.objects.get_or_create(
        ticker=ticker, defaults={"stance": "neutral", "conviction": 1}
    )
    model_id = cfg.default_model or "claude-opus-4-8"
    try:
        draft = run_structured(
            api_key=api_key,
            model=model_id,
            system=build_system_prompt(profile, now=timezone.now()),
            user=_build_prompt(note, snapshot, ticker, provider_name, model_id),
            output_model=CoverageRevisionDraft,
            base_url=cfg.base_url or "",
        )
    except Exception as exc:
        log.warning("coverage: revision AI call failed for %s: %s", ticker, exc)
        return None

    return _apply_draft(note, draft, snapshot, created=created)


def _note_dict(note: CoverageNote) -> dict[str, Any]:
    return {
        "stance": note.stance,
        "conviction": note.conviction,
        "bull_case": note.bull_case,
        "bear_case": note.bear_case,
        "key_levels": note.key_levels,
        "watching_for": note.watching_for,
    }


def _apply_draft(
    note: CoverageNote, draft: CoverageRevisionDraft, snapshot, *, created: bool
) -> CoverageRevision | None:
    """Persist a revision only on a material change (or the first-ever view);
    otherwise touch ``updated_at`` and return None (reaffirm, no churn row)."""
    changed = (
        created
        or draft.material_change
        or draft.stance != note.stance
        or draft.conviction != note.conviction
    )
    if not changed:
        note.save(update_fields=["updated_at"])
        return None

    prior = _note_dict(note)
    note.stance = draft.stance
    note.conviction = draft.conviction
    note.bull_case = draft.bull_case
    note.bear_case = draft.bear_case
    note.key_levels = draft.key_levels
    note.watching_for = draft.watching_for
    note.save()
    return CoverageRevision.objects.create(
        note=note,
        prior=prior,
        new=_note_dict(note),
        reason=draft.reason,
        source_snapshot=snapshot,
    )


def _build_prompt(
    note: CoverageNote, snapshot, ticker: str, provider_name: str, model_id: str
) -> str:
    """Prior house view + the current situation — a compact diff vs the prior
    snapshot when one exists, else the full serialized payload."""
    prev = previous_snapshot_for(snapshot)
    if prev is not None:
        prev_sections = {s.kind: s.payload for s in prev.sections.all()}
        curr_sections = {s.kind: s.payload for s in snapshot.sections.all()}
        delta = diff_sections(prev_sections, curr_sections)
        situation = f"Changes since snapshot #{prev.id}:\n{delta}"
    else:
        situation = serialize_for_ai(snapshot, provider=provider_name, model=model_id)

    return (
        f"You maintain a standing house view on {ticker}. The current view:\n\n"
        f"{_format_prior(note)}\n\n"
        f"New information:\n{situation}\n\n"
        "Revise the house view ONLY if something material changed. If nothing "
        "material did, set material_change=false and reaffirm the existing view "
        "unchanged. Always explain your reasoning in `reason`."
    )


def _format_prior(note: CoverageNote) -> str:
    return (
        f"Stance: {note.stance} (conviction {note.conviction}/5)\n"
        f"Bull case: {note.bull_case or '(none yet)'}\n"
        f"Bear case: {note.bear_case or '(none yet)'}\n"
        f"Key levels: {note.key_levels or '{}'}\n"
        f"Watching for: {note.watching_for or '(nothing yet)'}"
    )
