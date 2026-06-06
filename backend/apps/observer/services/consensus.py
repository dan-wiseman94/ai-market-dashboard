"""Cross-model consensus signal.

Fans the same structured ObservationReport prompt across every
structured-capable (provider, model) pair and measures agreement. Agreement is
a confidence signal a single model can't give; divergence flags "do more
homework". Degrades honestly to a single-provider result rather than inventing a
consensus.

Reality: ``run_structured`` (Anthropic ``messages.parse``) is Claude-only today,
so "structured-capable" means enabled Claude-family ``ProviderConfig`` rows with
a key. With fewer than 2 usable pairs the result is an explicit
single-provider/no-consensus shape. Expanding to OpenAI/local structured output
is a follow-up (would need provider-side structured support).

OPT-IN ONLY: this multiplies cost ~Nx, so it is gated behind the schedule's
``consensus`` flag and respects each provider's daily/monthly cost cap.
"""

from __future__ import annotations

import logging
from collections import Counter
from decimal import Decimal

from apps.ai.catalog import DEFAULT_CLAUDE_MODEL
from apps.ai.cost import CostCapExceededError, check_daily_cap, check_monthly_cap
from apps.ai.providers.claude_structured import run_structured
from apps.observer.schemas import ConsensusReport, ObservationReport, ProviderTake
from apps.secrets.models import ProviderConfig

log = logging.getLogger(__name__)

# Providers whose configs can drive run_structured (Anthropic messages.parse).
_STRUCTURED_PROVIDERS = ("claude", "anthropic")

_DEGRADED_NOTE = "single provider — no consensus available"

# (provider, model, api_key, base_url, daily_cap_usd, monthly_cap_usd)
StructuredPair = tuple[str, str, str, str, Decimal, Decimal | None]


def structured_capable_pairs() -> list[StructuredPair]:
    """Structured-capable pairs + their cost caps, one per enabled config.

    Tuple shape: ``(provider, model, api_key, base_url, daily_cap, monthly_cap)``.

    Structured output is Claude-only today, so this selects enabled Claude-family
    ``ProviderConfig`` rows that have an API key and a resolvable model. Caps are
    read from the same row here so the aggregation loop needs no further DB access
    (one query, not 1+N). v1 yields one pair per config; expanding to several
    models per provider is a later enhancement.
    """
    pairs: list[StructuredPair] = []
    qs = ProviderConfig.objects.filter(enabled=True, provider__in=_STRUCTURED_PROVIDERS).order_by(
        "provider"
    )
    for cfg in qs:
        key = cfg.api_key
        model = cfg.default_model or DEFAULT_CLAUDE_MODEL
        if not key:
            continue
        pairs.append(
            (
                cfg.provider,
                model,
                key,
                cfg.base_url or "",
                cfg.daily_cost_cap_usd,
                cfg.monthly_cost_cap_usd,
            )
        )
    return pairs


def _modal_and_agreement(biases: list[str]) -> tuple[str | None, float | None, bool]:
    """(modal_bias, agreement_fraction, divergent) for a list of biases.

    agreement = count(modal) / len, rounded to 4dp. None when < 2 biases — no
    consensus is meaningful with a single opinion.
    """
    if not biases:
        return None, None, False
    counts = Counter(biases)
    modal, modal_n = counts.most_common(1)[0]
    divergent = len(counts) > 1
    if len(biases) < 2:
        return modal, None, divergent
    return modal, round(modal_n / len(biases), 4), divergent


def consensus_report(*, system: str, user: str) -> ConsensusReport:
    """Run ObservationReport across structured-capable pairs, aggregate agreement.

    Never raises: a pair that errors (provider failure) or is over its cost cap is
    skipped and counted out. With fewer than 2 surviving takes the result is an
    honest single-provider/no-consensus shape — never a fabricated consensus.
    """
    pairs = structured_capable_pairs()

    takes: list[ProviderTake] = []
    for provider, model, api_key, base_url, cap_usd, monthly_cap in pairs:
        # Respect cost caps per provider; a capped provider is skipped, not run.
        try:
            check_daily_cap(provider, cap_usd=cap_usd)
            check_monthly_cap(provider, cap_usd=monthly_cap)
        except CostCapExceededError as exc:
            log.info("consensus: skipping %s/%s — cap: %s", provider, model, exc)
            continue

        try:
            report: ObservationReport = run_structured(
                api_key=api_key,
                model=model,
                system=system,
                user=user,
                output_model=ObservationReport,
                base_url=base_url,
            )
        except Exception as exc:
            log.warning("consensus: %s/%s structured run failed: %s", provider, model, exc)
            continue

        takes.append(
            ProviderTake(
                provider=provider,
                model=model,
                bias=report.bias,
                signal_bias={s.ticker: s.bias for s in report.signals},
            )
        )

    n = len(takes)
    if n < 2:
        modal = takes[0].bias if takes else None
        return ConsensusReport(
            n_providers=n,
            bias_agreement=None,
            modal_bias=modal,
            divergent=False,
            takes=takes,
            note=_DEGRADED_NOTE,
        )

    modal_bias, bias_agreement, divergent = _modal_and_agreement([t.bias for t in takes])

    # Per-ticker agreement: for each ticker any take called, collect provider->bias.
    per_ticker: dict[str, dict] = {}
    tickers = {ticker for t in takes for ticker in t.signal_bias}
    for ticker in sorted(tickers):
        votes = {
            f"{t.provider}/{t.model}": t.signal_bias[ticker]
            for t in takes
            if ticker in t.signal_bias
        }
        t_modal, t_agreement, _ = _modal_and_agreement(list(votes.values()))
        per_ticker[ticker] = {
            "agreement": t_agreement,
            "modal": t_modal,
            "takes": votes,
        }

    return ConsensusReport(
        n_providers=n,
        bias_agreement=bias_agreement,
        modal_bias=modal_bias,
        divergent=divergent,
        per_ticker=per_ticker,
        takes=takes,
        note="",
    )
