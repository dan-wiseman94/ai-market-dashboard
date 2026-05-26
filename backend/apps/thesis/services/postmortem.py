"""Post-mortem scheduler + AI-replay service.

Closes the decision loop on a Thesis. ``schedule_postmortems`` lays down one
PostMortem row per configured horizon. ``run_postmortem`` computes the ACTUAL
forward return + price path, assigns a DETERMINISTIC verdict (so the loop closes
even with no AI key), and BEST-EFFORT generates an AI narrative via Claude
structured output, posting it into the per-thesis review thread.

Mirrors apps.observer.services.run for provider/cap resolution and graceful
failure. The hard contract here: the AI narrative is best-effort and NEVER
raises out of the runner — the objective verdict, forward return, and "done"
status must always persist.
"""

from __future__ import annotations

import logging
from datetime import timedelta

from django.conf import settings
from django.utils import timezone

from apps.ai.cost import CostCapExceededError, check_daily_cap, check_monthly_cap
from apps.ai.providers.claude_structured import run_structured
from apps.market.returns import forward_return_pct, price_path_summary
from apps.observer.services.notifications import notify
from apps.secrets.models import ProviderConfig
from apps.threads.models import Message

from ..models import PostMortem, Thesis
from ..schemas import PostMortemReport
from .threads import get_or_create_review_thread

log = logging.getLogger(__name__)

# Symmetric flat band around 0% within which a directional call is treated as
# neither clearly right nor clearly wrong (percent).
DEADZONE = 1.0


def schedule_postmortems(thesis: Thesis) -> None:
    """Lay down one PostMortem per configured horizon. Idempotent."""
    for d in settings.THESIS_POSTMORTEM_HORIZONS:
        PostMortem.objects.get_or_create(
            thesis=thesis,
            horizon_days=d,
            defaults={"due_at": thesis.opened_at + timedelta(days=d)},
        )


def objective_verdict(thesis: Thesis, fwd_pct: float | None) -> str:
    """Deterministic verdict from the thesis direction + actual forward return.

    No AI involved — this is what closes the loop when no key is configured.
    """
    if fwd_pct is None:
        return "inconclusive"

    direction = thesis.direction
    if direction == "neutral":
        # A neutral call is "correct" when the move stayed inside the deadzone.
        return "correct" if abs(fwd_pct) <= DEADZONE else "incorrect"

    if direction == "bullish":
        if fwd_pct >= DEADZONE:
            return "correct"
        if fwd_pct <= -DEADZONE:
            return "incorrect"
        return "mixed"

    # bearish
    if fwd_pct <= -DEADZONE:
        return "correct"
    if fwd_pct >= DEADZONE:
        return "incorrect"
    return "mixed"


def _fmt_fwd(fwd: float | None) -> str:
    """Render the forward return for humans/prompt: 'unavailable' when None."""
    return "unavailable" if fwd is None else f"{fwd}%"


def _build_prompt(thesis: Thesis, pm: PostMortem, fwd: float | None, path: dict) -> str:
    """Compose the user prompt: the thesis as stated, then the actual outcome."""
    return (
        "Review the following trading thesis against what actually happened.\n\n"
        "THESIS AS STATED:\n"
        f"- Title: {thesis.title}\n"
        f"- Ticker: {thesis.ticker}\n"
        f"- Direction: {thesis.direction}\n"
        f"- Conviction (1-5): {thesis.conviction}\n"
        f"- Rationale: {thesis.rationale or '(none given)'}\n"
        f"- Entry price: {thesis.entry_price}\n"
        f"- Target price: {thesis.target_price}\n"
        f"- Invalidation price: {thesis.invalidation_price}\n"
        f"- Horizon under review: {pm.horizon_days} days\n\n"
        "ACTUAL OUTCOME:\n"
        f"- Forward return over the horizon: {_fmt_fwd(fwd)}\n"
        f"- Price path summary: {path}\n\n"
        "Assess what worked, what was missed, the lessons, whether you would "
        "repeat the call, and your own verdict on whether the thesis was correct."
    )


def _attempt_ai_narrative(
    pm: PostMortem,
    thesis: Thesis,
    fwd: float | None,
    path: dict,
) -> None:
    """Best-effort: populate pm.report + post a review Message. NEVER raises.

    On non-claude provider / no key / cap exceeded / any provider error we log a
    warning and leave pm.report = {} — the objective verdict + return are already
    recorded by the caller, so the loop still closes.
    """
    provider_name = (
        thesis.profile.default_provider
        if thesis.profile
        else (ProviderConfig.objects.values_list("provider", flat=True).first() or "")
    )
    cfg = ProviderConfig.objects.filter(provider=provider_name).first()

    if provider_name != "claude":
        log.warning(
            "postmortem %s: provider %r is not claude — skipping AI narrative",
            pm.id,
            provider_name,
        )
        return
    if cfg is None or not cfg.api_key:
        log.warning("postmortem %s: no claude key configured — skipping AI narrative", pm.id)
        return

    # Cost caps: cfg is guaranteed non-None here (we returned above otherwise),
    # so read its configured caps directly. daily defaults to 10.00; monthly is
    # nullable and a None monthly cap is a no-op in check_monthly_cap.
    cap_usd = cfg.daily_cost_cap_usd
    monthly_cap = cfg.monthly_cost_cap_usd
    try:
        check_daily_cap(provider_name, cap_usd=cap_usd)
        check_monthly_cap(provider_name, cap_usd=monthly_cap)
    except CostCapExceededError as exc:
        log.warning("postmortem %s: cost cap hit, skipping AI narrative — %s", pm.id, exc)
        return

    model_id = (
        (thesis.profile.default_model if thesis.profile else "")
        or cfg.default_model
        or "claude-opus-4-7"
    )
    system = thesis.profile.style if thesis.profile else ""
    prompt = _build_prompt(thesis, pm, fwd, path)

    report = run_structured(
        api_key=cfg.api_key,
        model=model_id,
        system=system or "",
        user=prompt,
        output_model=PostMortemReport,
        base_url=cfg.base_url or "",
    )

    pm.report = report.model_dump()
    thread = get_or_create_review_thread(thesis)
    msg = Message.objects.create(
        thread=thread,
        role="assistant",
        content={
            "kind": "postmortem_report",
            "report": pm.report,
            "horizon_days": pm.horizon_days,
            "forward_return_pct": fwd,
            "verdict": pm.verdict,
        },
        status="done",
    )
    pm.message = msg


def run_postmortem(pm_id: int) -> None:
    """Run one post-mortem. Objective verdict/return/status always persist.

    Idempotent against double-dispatch: a beat re-tick, a run-now+beat overlap,
    or repeated run-now clicks could otherwise each re-run the AI and post a
    DUPLICATE review message at real $ cost. We guard with an atomic
    compare-and-set status claim — only ONE concurrent caller transitions the
    row out of "scheduled", so the rest are no-ops.
    """
    # Atomic claim: .update() under a row lock means only one concurrent caller
    # gets claimed=1; everyone else (already running/done/failed) is a no-op.
    claimed = PostMortem.objects.filter(id=pm_id, status="scheduled").update(status="running")
    if not claimed:
        log.info("post-mortem %s not claimable (already running/done); skipping", pm_id)
        return

    pm = PostMortem.objects.select_related("thesis", "thesis__profile").get(id=pm_id)
    thesis = pm.thesis

    # 1) Objective outcome — deterministic, no AI. This is the loop-closing core.
    fwd = forward_return_pct(thesis.ticker, thesis.opened_at, pm.due_at)
    path = price_path_summary(thesis.ticker, thesis.opened_at, pm.due_at)
    pm.forward_return_pct = fwd
    pm.verdict = objective_verdict(thesis, fwd)

    # 2) Best-effort AI narrative. Wrapped so a provider error sets nothing worse
    #    than report={} — it must never abort the objective bookkeeping below.
    try:
        _attempt_ai_narrative(pm, thesis, fwd, path)
    except Exception as exc:
        log.warning(
            "postmortem %s: AI narrative failed (%s) — recording objective only", pm.id, exc
        )
        pm.report = {}

    pm.status = "done"
    pm.completed_at = timezone.now()
    pm.save()

    notify(
        user_id=None,
        kind="postmortem",
        title=f"Post-mortem: {thesis.title} ({pm.horizon_days}d)",
        body=f"Verdict: {pm.verdict}, forward return {_fmt_fwd(fwd)}",
        link=f"/theses/{thesis.id}",
    )
