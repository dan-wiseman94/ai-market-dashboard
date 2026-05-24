"""Cost math + daily cap guard."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from decimal import Decimal

from apps.ai.catalog import ceiling_for_provider, get_model
from apps.ai.types import TokenUsage


class CostCapExceededError(RuntimeError):
    """Raised to abort an AI run when the provider's daily cap is breached."""


_PER_MTOK = Decimal("1000000")


def cost_usd_for(provider: str, model_id: str, usage: TokenUsage) -> Decimal:
    """Compute USD cost for the given run."""
    if provider == "local":
        return Decimal("0")

    model = get_model(provider, model_id) or ceiling_for_provider(provider)
    if model is None:
        return Decimal("0")

    non_cached = max(0, usage.input_tokens - usage.cached_tokens)
    input_cost = _dec(non_cached) * _dec(model.input_per_mtok) / _PER_MTOK
    cached_cost = _dec(usage.cached_tokens) * _dec(model.cached_per_mtok) / _PER_MTOK
    output_cost = _dec(usage.output_tokens) * _dec(model.output_per_mtok) / _PER_MTOK
    return (input_cost + cached_cost + output_cost).quantize(Decimal("0.000001"))


def _dec(v: float | int) -> Decimal:
    return Decimal(str(v))


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
