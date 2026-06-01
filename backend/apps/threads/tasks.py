"""AI run Celery task — drives a provider chosen by the router.

The request-building, stream-driving, and tool-persistence helpers live in
sibling modules (`_request`, `_stream`, `_persist`) and are re-exported here so
existing `apps.threads.tasks.*` import and patch sites keep working. Celery
discovers `run_ai_on_message` by the explicit module path `apps.threads.tasks`,
so the `@shared_task` entrypoint must stay defined in this module.
"""

from __future__ import annotations

import asyncio
import contextlib
import logging
import time
from collections.abc import Callable, Coroutine
from decimal import Decimal
from typing import Any

from celery import shared_task
from django.db import transaction

from apps.ai.capabilities import unsupported_features
from apps.ai.cost import CostCapExceededError, check_daily_cap, check_monthly_cap, cost_usd_for
from apps.ai.providers import get_provider
from apps.ai.router import ResolutionError, resolve_provider_and_model
from apps.ai.types import TokenUsage
from apps.core.realtime import group_broadcast, group_broadcast_async
from apps.secrets.models import ProviderConfig
from apps.threads._persist import _persist_tool_calls
from apps.threads._request import _build_request, _extract_text
from apps.threads._stream import _build_stream_runner
from apps.threads.models import AIRun, Message, Thread
from apps.threads.stop import clear_stop, is_stop_requested

log = logging.getLogger(__name__)

# The sibling helpers are re-exported under `apps.threads.tasks.*` so existing
# call sites and test patches keep resolving here. `__all__` also marks
# `_extract_text` (re-exported but unused in this module) as intentional.
__all__ = [
    "_build_request",
    "_build_stream_runner",
    "_extract_text",
    "_persist_tool_calls",
    "run_ai_on_message",
]

_STOP_POLL_SECONDS = 0.25  # how often the streaming loop checks the stop flag
_PARTIAL_FLUSH_SECONDS = 0.75  # how often buffered text is persisted to the DB mid-stream

_INVESTIGATION_DIRECTIVE = (
    "## Investigation mode\n"
    "You are running autonomously with tools and no human watching. Do not answer "
    "from the given snapshot alone — INVESTIGATE: use your tools to pull what you "
    "need (intraday prices, news, the option chain, your own past calls on this "
    "name), follow the leads they open, and cross-check before you commit to a read. "
    "You have a limited number of tool rounds; spend them, then write ONE conclusion "
    "with exactly these sections:\n"
    "**What I checked** — the tools/data you pulled and why.\n"
    "**What I found** — the concrete findings, each tied to a tool result.\n"
    "**What it means** — your read, with confidence and what would invalidate it.\n"
    "**What to watch** — the specific levels/events that would change the picture."
)


def _apply_investigation_mode(req, *, provider_name: str, cfg) -> None:
    """Turn a normal RunRequest into a bounded autonomous investigation: force the
    toolset on (when the provider can run tools), cap the tool rounds, and append
    the investigation directive to the system prompt. Mutates ``req`` in place."""
    from django.conf import settings

    req.max_tool_iterations = int(getattr(settings, "AI_INVESTIGATION_MAX_ITERATIONS", 8))
    if provider_name == "claude" or getattr(cfg, "supports_tools", False):
        from apps.ai.tools.registry import default_toolset

        ts = default_toolset()
        req.tools = ts.anthropic_tools() if provider_name == "claude" else ts.openai_tools()
    req.system = f"{req.system}\n\n{_INVESTIGATION_DIRECTIVE}"


def _broadcast(thread_id: int, payload: dict) -> None:
    from apps.threads.event_log import record

    group_broadcast(f"thread.{thread_id}", "thread_event", record(thread_id, payload))


async def _broadcast_async(thread_id: int, payload: dict) -> None:
    from apps.threads.event_log import record

    # record() is a quick synchronous Redis round-trip; the buffer must stay
    # ordered with the live broadcast, so stamp the seq here too.
    await group_broadcast_async(f"thread.{thread_id}", "thread_event", record(thread_id, payload))


def _fail(
    *,
    thread_id: int,
    parent_message_id: int | None,
    error: str,
    event: str = "error",
) -> Message:
    """Create a failed assistant message and broadcast a single error/cost_capped event."""
    assistant = Message.objects.create(
        thread_id=thread_id,
        role="assistant",
        content={"text": ""},
        status="failed",
        error=error,
        parent_message_id=parent_message_id,
    )
    _broadcast(thread_id, {"event": event, "message_id": assistant.id, "error": error})
    return assistant


def _emit_capability_warning(*, thread_id: int, features: list[str], provider_name: str) -> bool:
    """Write a system/done message + broadcast a WS warning when the selected
    provider can't honor enabled profile features. Deduped against the thread's
    most recent system message. Returns True if a message was written."""
    feature_list = ", ".join(features)
    text = (
        f"Heads up: provider '{provider_name}' does not support "
        f"{feature_list}. Those settings were ignored for this run."
    )
    last_system = (
        Message.objects.filter(thread_id=thread_id, role="system").order_by("-created_at").first()
    )
    if last_system is not None and last_system.content.get("text") == text:
        return False
    msg = Message.objects.create(
        thread_id=thread_id,
        role="system",
        content={"text": text, "kind": "capability_warning"},
        status="done",
    )
    _broadcast(thread_id, {"event": "warning", "message_id": msg.id, "text": text})
    return True


@shared_task(name="threads.run_ai_on_message")
def run_ai_on_message(
    *,
    thread_id: int,
    user_message_id: int,
    override: dict | None = None,
    parent_message_id: int | None = None,
    scenario: str | None = None,
    investigate: bool = False,
) -> dict:
    # E2E only: the mock scenario is captured from the request's X-E2E-Scenario
    # header into a web-process ContextVar, which does NOT cross into this worker
    # process. Re-apply it here so MOCK_EXTERNAL streaming honors the scenario
    # (thinking-heavy, tool-use-loop, 5xx-midstream, …). No-op in production,
    # where current_scenario() is always "default" and nothing passes a scenario.
    from apps.core.mocks import is_mock_mode, reset_scenario, set_scenario

    applied = bool(scenario) and is_mock_mode()
    if applied:
        set_scenario(scenario)  # type: ignore[arg-type]
    try:
        return _run_ai_on_message(
            thread_id=thread_id,
            user_message_id=user_message_id,
            override=override,
            parent_message_id=parent_message_id,
            investigate=investigate,
        )
    finally:
        if applied:
            reset_scenario()


def _resolve_run_config(
    *,
    thread: Thread,
    user_msg: Message,
    override: dict | None,
    parent_message_id: int | None,
    investigate: bool = False,
) -> tuple[str, str, ProviderConfig] | dict:
    """Resolve provider/model and its ProviderConfig, enforcing enablement and
    cost caps. Returns (provider_name, model_id, cfg) on success, or a failure
    result dict (already broadcast via _fail) to return from the task.
    """
    try:
        provider_name, model_id = resolve_provider_and_model(
            thread=thread, message=user_msg, override=override
        )
    except ResolutionError as exc:
        _fail(thread_id=thread.id, parent_message_id=parent_message_id, error=str(exc))
        return {"ok": False, "error": "no_provider"}

    try:
        cfg = ProviderConfig.objects.get(provider=provider_name)
    except ProviderConfig.DoesNotExist:
        _fail(
            thread_id=thread.id,
            parent_message_id=parent_message_id,
            error=f"No ProviderConfig row for '{provider_name}'. Visit /settings.",
        )
        return {"ok": False, "error": "no_key"}

    if not cfg.enabled:
        # A profile can pin a provider+model that resolve_provider_and_model returns
        # without consulting `enabled` (it only filters enabled in fallback). Gate here
        # so the Settings "disable provider" toggle actually blocks runs for that provider.
        _fail(
            thread_id=thread.id,
            parent_message_id=parent_message_id,
            error=f"Provider '{provider_name}' is disabled. Enable it in /settings.",
        )
        return {"ok": False, "error": "provider_disabled"}

    try:
        check_daily_cap(provider_name, cap_usd=cfg.daily_cost_cap_usd)
        check_monthly_cap(provider_name, cap_usd=cfg.monthly_cost_cap_usd)
        if investigate:
            # Autonomous runs honor a separate, lower daily ceiling (when set) so
            # background investigations can't drain the interactive budget.
            from decimal import Decimal as _D

            from django.conf import settings as _s

            auto_cap = float(getattr(_s, "AI_AUTONOMOUS_DAILY_CAP_USD", 0.0) or 0.0)
            if auto_cap > 0:
                check_daily_cap(provider_name, cap_usd=_D(str(auto_cap)))
    except CostCapExceededError as exc:
        _fail(
            thread_id=thread.id,
            parent_message_id=parent_message_id,
            error=str(exc),
            event="cost_capped",
        )
        return {"ok": False, "error": "cost_capped"}

    return provider_name, model_id, cfg


def _failover_target(primary_name: str) -> tuple[str, str, ProviderConfig] | None:
    """The secondary (provider, model, cfg) to retry on when the primary errors
    BEFORE emitting any token — or None when failover is unavailable.

    Opt-in via the failover settings (default off; UI-tunable via SystemSettings). The
    configured secondary must differ from the primary, have an enabled ProviderConfig with
    a default_model, and be within its own cost caps.
    """
    from apps.core.runtime_config import runtime_config

    rc = runtime_config()
    if not rc.ai_failover_enabled:
        return None
    name = (rc.ai_failover_provider or "").strip()
    if not name or name == primary_name:
        return None
    try:
        cfg = ProviderConfig.objects.get(provider=name)
    except ProviderConfig.DoesNotExist:
        return None
    if not cfg.enabled or not cfg.default_model:
        return None
    try:
        check_daily_cap(name, cap_usd=cfg.daily_cost_cap_usd)
        check_monthly_cap(name, cap_usd=cfg.monthly_cost_cap_usd)
    except CostCapExceededError:
        return None
    return name, cfg.default_model, cfg


def _make_should_stop(assistant_id: int) -> Callable[[], bool]:
    """Throttled stop poll: hits Redis at most once per _STOP_POLL_SECONDS and
    latches True once a stop has been requested."""
    last_poll = 0.0
    stopped = False

    def _should_stop() -> bool:
        nonlocal last_poll, stopped
        if stopped:
            return True
        now = time.monotonic()
        if now - last_poll < _STOP_POLL_SECONDS:
            return False
        last_poll = now
        if is_stop_requested(assistant_id):
            stopped = True
        return stopped

    return _should_stop


def _make_flush_partial(
    assistant_id: int, buffer: list[str]
) -> Callable[..., Coroutine[Any, Any, None]]:
    """Throttled async flush of the streamed buffer into the assistant Message.

    Persists ``"".join(buffer)`` into ``content`` at most once per
    ``_PARTIAL_FLUSH_SECONDS`` (``force=True`` bypasses the throttle) so a mid-stream
    page reload reads the partial response instead of an empty bubble. The write is
    guarded on ``status='streaming'`` so it can never resurrect or clobber a message
    that the stop endpoint (or the terminal write) has already finalized.
    """
    from asgiref.sync import sync_to_async

    last_flush = 0.0

    @sync_to_async
    def _write(text: str) -> None:
        Message.objects.filter(id=assistant_id, status="streaming").update(content={"text": text})

    async def _flush(force: bool = False) -> None:
        nonlocal last_flush
        now = time.monotonic()
        if not force and now - last_flush < _PARTIAL_FLUSH_SECONDS:
            return
        last_flush = now
        await _write("".join(buffer))

    return _flush


def _run_ai_on_message(
    *,
    thread_id: int,
    user_message_id: int,
    override: dict | None = None,
    parent_message_id: int | None = None,
    investigate: bool = False,
) -> dict:
    thread = Thread.objects.select_related("profile").get(id=thread_id)
    user_msg = Message.objects.get(id=user_message_id)

    resolved = _resolve_run_config(
        thread=thread,
        user_msg=user_msg,
        override=override,
        parent_message_id=parent_message_id,
        investigate=investigate,
    )
    if isinstance(resolved, dict):
        return resolved
    provider_name, model_id, cfg = resolved

    gaps = unsupported_features(provider_name, thread.profile, supports_tools=cfg.supports_tools)
    if gaps:
        # Best-effort: a warning failure (DB/broadcast error) must never abort a valid run.
        with contextlib.suppress(Exception):
            _emit_capability_warning(
                thread_id=thread_id, features=gaps, provider_name=provider_name
            )

    req = _build_request(
        thread, user_msg, provider_name=provider_name, supports_tools=cfg.supports_tools
    )
    req.model = model_id
    if investigate:
        _apply_investigation_mode(req, provider_name=provider_name, cfg=cfg)

    assistant = Message.objects.create(
        thread=thread,
        role="assistant",
        content={"text": "", "kind": "investigation"} if investigate else {"text": ""},
        status="streaming",
        parent_message_id=parent_message_id,
    )
    _broadcast(
        thread_id,
        {
            "event": "message_started",
            "message_id": assistant.id,
            "parent_message_id": parent_message_id,
            "provider": provider_name,
            "model": model_id,
        },
    )

    t0 = time.perf_counter()
    buffer: list[str] = []
    counts: dict[str, int] = {"input_tokens": 0, "output_tokens": 0, "cached_tokens": 0}
    err_container: list[str] = []
    tool_events: list[dict] = []
    should_stop = _make_should_stop(assistant.id)
    flush_partial = _make_flush_partial(assistant.id, buffer)

    def _run_attempt(p_name: str, p_cfg: ProviderConfig, attempt_req: Any) -> None:
        provider = get_provider(p_name, api_key=p_cfg.api_key, base_url=p_cfg.base_url or "")
        drive = _build_stream_runner(
            buffer,
            counts,
            err_container,
            tool_events,
            provider,
            attempt_req,
            thread_id,
            assistant.id,
            should_stop,
            flush_partial,
        )
        asyncio.run(drive())

    _run_attempt(provider_name, cfg, req)

    # Cross-provider failover (C1): the primary errored BEFORE any token streamed.
    # Retry once on a configured secondary — never after a token (that would
    # duplicate the response). Opt-in; _failover_target returns None when off.
    secondary = _failover_target(provider_name) if (err_container and not buffer) else None
    if secondary is not None and not should_stop():
        sec_name, sec_model, sec_cfg = secondary
        # Log the transition only — not the provider's raw error string, which
        # could carry sensitive context (CWE-532 / the repo's no-secret-logging rule).
        log.warning(
            "ai failover: %s/%s -> %s/%s (primary errored before first token)",
            provider_name,
            model_id,
            sec_name,
            sec_model,
        )
        buffer.clear()
        counts.update({"input_tokens": 0, "output_tokens": 0, "cached_tokens": 0})
        err_container.clear()
        tool_events.clear()
        sec_req = _build_request(
            thread, user_msg, provider_name=sec_name, supports_tools=sec_cfg.supports_tools
        )
        sec_req.model = sec_model
        _run_attempt(sec_name, sec_cfg, sec_req)
        provider_name, model_id = sec_name, sec_model

    clear_stop(assistant.id)
    latency_ms = int((time.perf_counter() - t0) * 1000)
    err: str | None = err_container[0] if err_container else None

    with transaction.atomic():
        assistant.refresh_from_db()
        if assistant.status == "failed" and assistant.error == "cancelled":
            # Stop endpoint already marked the message; don't overwrite cancellation.
            AIRun.objects.create(
                message=assistant,
                provider=provider_name,
                model=model_id,
                status="failed",
                error="cancelled",
                latency_ms=latency_ms,
                input_tokens=counts["input_tokens"],
                output_tokens=counts["output_tokens"],
            )
            return {"ok": False, "error": "cancelled"}

        assistant.content = {"text": "".join(buffer)}
        if err:
            assistant.status = "failed"
            assistant.error = err
            assistant.save()
            AIRun.objects.create(
                message=assistant,
                provider=provider_name,
                model=model_id,
                status="failed",
                error=err,
                latency_ms=latency_ms,
            )
            _broadcast(thread_id, {"event": "error", "message_id": assistant.id, "error": err})
            return {"ok": False, "error": err}

        assistant.status = "done"
        assistant.save()
        _persist_tool_calls(assistant, tool_events)

        cost = (
            cost_usd_for(provider_name, model_id, TokenUsage(**counts))
            if any(counts.values())
            else Decimal("0")
        )
        AIRun.objects.create(
            message=assistant,
            provider=provider_name,
            model=model_id,
            cost_usd=cost,
            latency_ms=latency_ms,
            status="done",
            **counts,
        )
        _broadcast(
            thread_id,
            {
                "event": "message_done",
                "message_id": assistant.id,
                "cost_usd": str(cost),
            },
        )
        _broadcast(
            thread_id,
            {
                "event": "cost",
                "message_id": assistant.id,
                "parent_message_id": parent_message_id,
                "cost_usd": str(cost),
                "tokens_in": counts["input_tokens"],
                "tokens_out": counts["output_tokens"],
                "tokens_cached": counts["cached_tokens"],
                "duration_ms": latency_ms,
            },
        )
        return {"ok": True}
