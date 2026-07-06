"""Orchestrates a single observer fire."""

from __future__ import annotations

import contextlib
import hashlib
import logging
from datetime import timedelta
from decimal import Decimal

from cryptography.fernet import InvalidToken
from django.utils import timezone

from apps.ai.catalog import CLAUDE_FAMILY_PROVIDERS, DEFAULT_CLAUDE_MODEL
from apps.ai.cost import CostCapExceededError, check_daily_cap, check_monthly_cap
from apps.ai.providers.claude_structured import run_structured
from apps.core.runtime_config import runtime_config
from apps.market.calendar import any_market_open
from apps.observer.models import ObserverSchedule
from apps.observer.schemas import ObservationReport
from apps.observer.services.notifications import notify
from apps.observer.services.threads import get_or_create_observer_thread
from apps.secrets.models import ProviderConfig
from apps.snapshots.serializer import serialize_for_ai
from apps.snapshots.services import capture
from apps.strategy.coverage.hooks import maybe_revise_from_snapshot
from apps.threads.coach import assemble_coach_context, build_system_prompt
from apps.threads.models import Message
from apps.threads.tasks import run_ai_on_message

log = logging.getLogger(__name__)


def _stamp_fired(sched: ObserverSchedule) -> None:
    sched.last_fired_at = timezone.now()
    sched.save(update_fields=["last_fired_at"])


def run_observer(schedule_id: int) -> int | None:
    """Fire one observer iteration. Returns snapshot_id, or None on skip."""
    sched = ObserverSchedule.objects.select_related("profile").get(id=schedule_id)

    if not sched.enabled:
        log.info("observer %s skipped: disabled", schedule_id)
        return None

    if sched.market_hours_only and not any_market_open(sched.default_watchlist_tickers):
        log.info("observer %s skipped: all watched markets closed", schedule_id)
        return None

    thread = get_or_create_observer_thread(sched.profile)
    provider_name = sched.override_provider or sched.profile.default_provider
    model_name = sched.override_model or sched.profile.default_model

    # Resolve caps — Infinity daily / None monthly when no ProviderConfig row exists.
    # defer the encrypted key: the cap fields are read here without decrypting, so a
    # key/salt rotation can't crash the plain path (the AI call delegates to
    # run_ai_on_message). The structured branch DOES read cfg.api_key (in
    # _run_structured_and_record) — deferred, so it decrypts lazily there and is
    # guarded against InvalidToken.
    cfg = ProviderConfig.objects.filter(provider=provider_name).defer("_api_key").first()
    if cfg is None:
        log.warning(
            "observer %s: no ProviderConfig for %s, skipping cost-cap enforcement",
            schedule_id,
            provider_name,
        )
        cap_usd: Decimal = Decimal("Infinity")
        monthly_cap: Decimal | None = None
    else:
        cap_usd = cfg.daily_cost_cap_usd
        monthly_cap = cfg.monthly_cost_cap_usd

    # Cost-cap check: write placeholder Message instead of running if exceeded.
    try:
        check_daily_cap(provider_name, cap_usd=cap_usd)
        check_monthly_cap(provider_name, cap_usd=monthly_cap)
    except CostCapExceededError as exc:
        Message.objects.create(
            thread=thread,
            role="system",
            content={
                "text": (
                    f"Observer fire skipped at {timezone.now():%Y-%m-%d %H:%M UTC}: "
                    f"cost cap exceeded — {exc}"
                )
            },
            status="done",
        )
        _stamp_fired(sched)
        return None

    snap = capture(
        profile=sched.profile,
        objective=sched.objective_template,
        includes=sched.default_includes or sched.profile.default_includes,
        source="observer",
        watchlist_tickers=sched.default_watchlist_tickers,
    )

    if sched.use_batch:
        from apps.observer.services.batch import submit_watchlist_batch

        try:
            submit_watchlist_batch(sched.id, snapshot_id=snap.id)
        except Exception as exc:
            log.exception("observer %s batch submit failed: %s", sched.id, exc)
            # A log line alone is UI-invisible; the observer timeline reads
            # Messages, so record the failure where the user will see it.
            Message.objects.create(
                thread=thread,
                role="assistant",
                content={"text": f"Observer {sched.name}: batch submit failed — {exc}"},
                status="failed",
                error=str(exc),
            )
        _stamp_fired(sched)
        return snap.id

    payload_text = _build_payload_text(sched, snap, provider_name, model_name)
    coach = assemble_coach_context(snap, sched.profile)
    user_text = coach + payload_text
    prompt_hash = _prompt_hash(user_text, provider_name, model_name)

    msg = Message.objects.create(
        thread=thread,
        role="user",
        content={"text": user_text, "prompt_hash": prompt_hash},
        snapshot_ref=snap,
        status="done",
    )

    if sched.consensus:
        # Consensus is itself a structured operation (fans ObservationReport), so
        # it takes precedence over the plain structured path. Opt-in, ~Nx cost.
        _run_consensus_and_record(sched, thread, user_text)
    elif sched.structured:
        _run_structured_and_record(sched, thread, user_text, provider_name, cfg, snap=snap)
    else:
        rc = runtime_config()  # one row fetch; reused for the gate and the TTL below
        cached = (
            _cached_observer_response(
                thread,
                prompt_hash,
                exclude_message_id=msg.id,
                ttl=rc.observer_response_cache_ttl_seconds,
            )
            if rc.observer_response_cache_enabled
            else None
        )
        if cached is not None:
            # Byte-identical prompt within the TTL — reuse the prior observation
            # instead of paying for another AI call.
            Message.objects.create(
                thread=thread,
                role="assistant",
                content={"text": cached, "kind": "cached_observation"},
                status="done",
            )
        else:
            override: dict = {}
            if sched.override_provider:
                override["provider"] = sched.override_provider
            if sched.override_model:
                override["model"] = sched.override_model
            run_ai_on_message.delay(
                thread_id=thread.id,
                user_message_id=msg.id,
                override=override or None,
                investigate=sched.investigate,
            )

    # Auto-revise the house view when this snapshot's ticker is covered.
    with contextlib.suppress(Exception):
        maybe_revise_from_snapshot(snap)

    _stamp_fired(sched)

    notify(
        user_id=None,
        kind="observer_done",
        title=f"Observer fired: {sched.name}",
        body=f"Snapshot #{snap.id} captured for {sched.profile.name}",
        link=f"/threads/observer/{sched.profile.id}",
    )
    return snap.id


def _build_payload_text(sched: ObserverSchedule, snap, provider_name: str, model_name: str) -> str:
    """The user-turn text for this fire: a diff vs the prior snapshot, or the full payload."""
    if sched.mode == "diff":
        from apps.snapshots.diff import diff_sections
        from apps.snapshots.models import Snapshot

        prev_snap = (
            Snapshot.objects.filter(profile=sched.profile, status="ready")
            .exclude(id=snap.id)
            .order_by("-captured_at")
            .first()
        )
        if prev_snap is not None:
            prev_sections = {s.kind: s.payload for s in prev_snap.sections.all()}
            curr_sections = {s.kind: s.payload for s in snap.sections.all()}
            delta_text = diff_sections(prev_sections, curr_sections)
            return (
                f"Objective: {sched.objective_template}\n\n"
                f"Delta since snapshot #{prev_snap.id}:\n{delta_text}"
            )

    return serialize_for_ai(snap, provider=provider_name, model=model_name)


def _prompt_hash(text: str, provider: str, model: str) -> str:
    return hashlib.sha256(f"{provider}|{model}|{text}".encode()).hexdigest()


def _cached_observer_response(
    thread, prompt_hash: str, exclude_message_id: int, ttl: int
) -> str | None:
    """Text of a recent prior observation on this thread whose fire used a
    byte-identical prompt (same hash), within ``ttl`` seconds — else None.

    The observer thread is linear (user, assistant, user, …), so the response is
    the first ``done`` assistant message after that prior user turn. The current
    fire's own user message is excluded (it was just written with this hash).
    """
    cutoff = timezone.now() - timedelta(seconds=ttl)
    prior_user = (
        Message.objects.filter(
            thread=thread,
            role="user",
            status="done",
            content__prompt_hash=prompt_hash,
            created_at__gte=cutoff,
        )
        .exclude(id=exclude_message_id)
        .order_by("-created_at")
        .first()
    )
    if prior_user is None:
        return None
    asst = (
        Message.objects.filter(
            thread=thread, role="assistant", status="done", created_at__gt=prior_user.created_at
        )
        .order_by("created_at")
        .first()
    )
    if asst is None:
        return None
    return (asst.content or {}).get("text", "") or None


def _extract_prediction(report, *, snap, message, provider: str, model: str, profile) -> None:
    """Best-effort: promote the structured call into an AIPrediction.

    Isolated + suppressed — a failure here (or the model carrying no directional
    call) must never break the observer fire that already produced the report.
    """
    try:
        from apps.observer.predictions.services.extract import extract_from_observation

        extract_from_observation(
            report, snapshot=snap, message=message, provider=provider, model=model, profile=profile
        )
    except Exception as exc:
        log.warning(
            "observer %s: prediction extraction failed: %s", getattr(profile, "id", "?"), exc
        )


def _run_structured_and_record(
    sched: ObserverSchedule,
    thread,
    payload_text: str,
    provider_name: str,
    cfg: ProviderConfig | None,
    *,
    snap=None,
) -> None:
    """Invoke messages.parse with ObservationReport and persist the result."""
    if provider_name not in CLAUDE_FAMILY_PROVIDERS:
        # Structured outputs run through Anthropic messages.parse — skip with a
        # visible Message (mirrors the postmortem/consensus guards) instead of
        # sending another vendor's key to the Anthropic endpoint and failing
        # every fire with an opaque 401.
        Message.objects.create(
            thread=thread,
            role="system",
            content={
                "text": (
                    f"Observer {sched.name}: structured mode requires a Claude "
                    f"provider (schedule resolves to {provider_name!r}); fire skipped."
                )
            },
            status="failed",
            error="unsupported_provider",
        )
        return
    try:
        has_key = cfg is not None and bool(cfg.api_key)
    except InvalidToken:
        # The stored key can't be decrypted (DJANGO_SECRET_KEY / salt rotated since it
        # was saved). cfg was fetched with .defer("_api_key"), so decryption happens
        # lazily on this first access and raises here. Mirror the threads path
        # (threads/tasks.py) and record an actionable failed Message instead of letting
        # InvalidToken crash the fire silently (the observer timeline reads Messages).
        Message.objects.create(
            thread=thread,
            role="assistant",
            content={
                "text": (
                    f"Observer {sched.name}: {provider_name} API key could not be decrypted "
                    "(the encryption key may have changed). Re-enter it in "
                    "Settings → Providers."
                )
            },
            status="failed",
            error="undecryptable_key",
        )
        return
    # `cfg is None` is redundant with has_key at runtime but narrows the type
    # for the attribute reads below (mypy zero-baseline gate).
    if cfg is None or not has_key:
        Message.objects.create(
            thread=thread,
            role="system",
            content={"text": f"Observer {sched.name}: no {provider_name} key configured"},
            status="failed",
            error="no_key",
        )
        return
    model_id = sched.override_model or cfg.default_model or DEFAULT_CLAUDE_MODEL
    try:
        report = run_structured(
            api_key=cfg.api_key,
            model=model_id,
            system=build_system_prompt(sched.profile, now=timezone.now()),
            user=payload_text,
            output_model=ObservationReport,
            base_url=cfg.base_url or "",
        )
    except Exception as exc:
        Message.objects.create(
            thread=thread,
            role="assistant",
            content={"text": f"Structured run failed: {exc}"},
            status="failed",
            error=str(exc),
        )
        return
    msg = Message.objects.create(
        thread=thread,
        role="assistant",
        content={"kind": "structured_observation", "report": report.model_dump()},
        status="done",
    )
    _extract_prediction(
        report,
        snap=snap,
        message=msg,
        provider=provider_name,
        model=model_id,
        profile=sched.profile,
    )


def _run_consensus_and_record(sched: ObserverSchedule, thread, payload_text: str) -> None:
    """Fan ObservationReport across structured-capable providers; record the signal.

    Always records an assistant ``consensus_report`` Message — even the honest
    degraded shape (``n_providers<2``, ``bias_agreement=None``) — because that is
    a valid, truthful result, not a failure. ``consensus_report`` never raises
    (a provider that errors or is over its cap is skipped + counted out), so this
    needs no extra crash guard.
    """
    from apps.observer.services.consensus import consensus_report

    report = consensus_report(
        system=build_system_prompt(sched.profile, now=timezone.now()),
        user=payload_text,
    )
    Message.objects.create(
        thread=thread,
        role="assistant",
        content={"kind": "consensus_report", "report": report.model_dump()},
        status="done",
    )
