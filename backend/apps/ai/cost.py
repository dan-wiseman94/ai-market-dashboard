"""Cost math + daily cap guard."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from decimal import Decimal
from typing import TYPE_CHECKING

from apps.ai.catalog import ceiling_for_provider, get_model
from apps.ai.types import TokenUsage

if TYPE_CHECKING:
    from apps.threads.models import AIRun, Message


class CostCapExceededError(RuntimeError):
    """Raised to abort an AI run when the provider's daily cap is breached."""


_PER_MTOK = Decimal("1000000")
# Anthropic 5-minute prompt-cache write costs 1.25x the base input rate.
_CACHE_WRITE_MULT = Decimal("1.25")


def cost_usd_for(provider: str, model_id: str, usage: TokenUsage) -> Decimal:
    """Compute USD cost for the given run."""
    if provider == "local":
        return Decimal("0")

    model = get_model(provider, model_id) or ceiling_for_provider(provider)
    if model is None:
        return Decimal("0")

    # cached_tokens (reads) and cache_write_tokens (creation) are disjoint subsets
    # of input_tokens; the remainder bills at the full input rate. Cache writes
    # carry Anthropic's 5-minute write premium (1.25x base input).
    cache_read = usage.cached_tokens
    cache_write = usage.cache_write_tokens
    full_rate = max(0, usage.input_tokens - cache_read - cache_write)
    input_cost = _dec(full_rate) * _dec(model.input_per_mtok) / _PER_MTOK
    cached_cost = _dec(cache_read) * _dec(model.cached_per_mtok) / _PER_MTOK
    write_cost = _dec(cache_write) * _dec(model.input_per_mtok) * _CACHE_WRITE_MULT / _PER_MTOK
    output_cost = _dec(usage.output_tokens) * _dec(model.output_per_mtok) / _PER_MTOK
    return (input_cost + cached_cost + write_cost + output_cost).quantize(Decimal("0.000001"))


def _dec(v: float | int) -> Decimal:
    return Decimal(str(v))


def record_ai_run(
    *,
    provider: str,
    model: str,
    usage: TokenUsage,
    message: Message | None = None,
    status: str = "done",
    latency_ms: int = 0,
    error: str = "",
) -> AIRun:
    """Persist an AIRun so a provider call's cost counts against the caps.

    The streaming chat path records its own AIRun inline (threads.tasks); this is
    the shared recorder for the one-shot ``run_structured`` path (post-mortems,
    coverage revisions, regime/book narratives, war-room, eval, predictions),
    whose spend was previously invisible to check_daily_cap / check_monthly_cap
    (both sum AIRun.cost_usd). ``message`` is None for runs not tied to a chat
    Message — AIRun.message is nullable for exactly this reason.
    """
    from apps.threads.models import AIRun

    return AIRun.objects.create(
        message=message,
        provider=provider,
        model=model,
        input_tokens=usage.input_tokens,
        output_tokens=usage.output_tokens,
        cached_tokens=usage.cached_tokens,
        cost_usd=cost_usd_for(provider, model, usage),
        latency_ms=latency_ms,
        status=status,
        error=error,
    )


def _spend_since(provider: str, start: datetime) -> Decimal:
    """Sum a provider's AIRun.cost_usd since ``start``."""
    from django.db.models import Sum

    from apps.threads.models import AIRun

    agg = AIRun.objects.filter(
        provider=provider,
        created_at__gte=start,
    ).aggregate(total=Sum("cost_usd"))
    return agg["total"] or Decimal("0")


def daily_spend_usd(provider: str) -> Decimal:
    """Sum today's AIRun.cost_usd for the given provider (UTC day)."""
    today_start = datetime.now(tz=UTC).replace(hour=0, minute=0, second=0, microsecond=0)
    return _spend_since(provider, today_start)


def check_daily_cap(
    provider: str, cap_usd: Decimal, prospective_cost: Decimal = Decimal("0")
) -> None:
    """Raise if today's spend + the prospective cost would exceed cap."""
    spent = daily_spend_usd(provider)
    if spent + prospective_cost > cap_usd:
        raise CostCapExceededError(
            f"{provider} daily cap ${cap_usd} would be exceeded "
            f"(spent ${spent}, this run ~${prospective_cost})"
        )


def monthly_spend_usd(provider: str) -> Decimal:
    """Sum the last 30 days of AIRun.cost_usd for the given provider."""
    window_start = datetime.now(tz=UTC) - timedelta(days=30)
    return _spend_since(provider, window_start)


def check_monthly_cap(
    provider: str,
    cap_usd: Decimal | None,
    prospective_cost: Decimal = Decimal("0"),
) -> None:
    """Raise if last-30-days + prospective would exceed cap.

    A cap of None (the default when a user hasn't set one on ProviderConfig)
    is a no-op: monthly caps are opt-in.
    """
    if cap_usd is None:
        return
    spent = monthly_spend_usd(provider)
    if spent + prospective_cost > cap_usd:
        raise CostCapExceededError(
            f"{provider} monthly cap ${cap_usd} would be exceeded "
            f"(30-day spend ${spent}, this run ~${prospective_cost})"
        )
