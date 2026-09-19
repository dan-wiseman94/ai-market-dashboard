"""Cross-model consensus signal.

Fans the same structured ObservationReport prompt across every usable enabled
provider (claude / openai / local — see ``apps.ai.structured``) and measures
agreement. Agreement is a confidence signal a single model can't give;
divergence flags "do more homework". With fewer than 2 usable providers the
result is an explicit single-provider/no-consensus shape — never a fabricated
consensus.

OPT-IN ONLY: this multiplies cost ~Nx, so it is gated behind the schedule's
``consensus`` flag and respects each provider's daily/monthly cost cap.
"""

from __future__ import annotations

import logging
from collections import Counter

from apps.ai.cost import CostCapExceededError, check_daily_cap, check_monthly_cap
from apps.ai.structured import StructuredTarget, run_structured, structured_capable_targets
from apps.observer.schemas import Bias, ConsensusReport, ObservationReport, ProviderTake

log = logging.getLogger(__name__)

_DEGRADED_NOTE = "single provider — no consensus available"

# The consensus loop's name for a usable (provider, model, key, base_url, caps) target.
StructuredPair = StructuredTarget


def structured_capable_pairs() -> list[StructuredTarget]:
    """Every usable enabled provider, one per config (``apps.ai.structured``)."""
    return structured_capable_targets()


def _modal_and_agreement(biases: list[Bias]) -> tuple[Bias | None, float | None, bool]:
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
    """Run ObservationReport across every usable provider, aggregate agreement.

    Never raises: a pair that errors (provider failure) or is over its cost cap is
    skipped and counted out. With fewer than 2 surviving takes the result is an
    honest single-provider/no-consensus shape — never a fabricated consensus.
    """
    pairs = structured_capable_pairs()

    takes: list[ProviderTake] = []
    # Attribute access (not tuple-unpack) keeps the secret pair.api_key isolated
    # from the loggable pair.provider / pair.model — see StructuredPair docstring.
    for pair in pairs:
        # Respect cost caps per provider; a capped provider is skipped, not run.
        try:
            check_daily_cap(pair.provider, cap_usd=pair.daily_cap)
            check_monthly_cap(pair.provider, cap_usd=pair.monthly_cap)
        except CostCapExceededError as exc:
            log.info("consensus: skipping %s/%s — cap: %s", pair.provider, pair.model, exc)
            continue

        try:
            report: ObservationReport = run_structured(
                provider=pair.provider,
                api_key=pair.api_key,
                model=pair.model,
                system=system,
                user=user,
                output_model=ObservationReport,
                base_url=pair.base_url,
            )
        except Exception as exc:
            log.warning(
                "consensus: %s/%s structured run failed: %s", pair.provider, pair.model, exc
            )
            continue

        takes.append(
            ProviderTake(
                provider=pair.provider,
                model=pair.model,
                bias=report.bias,
                signal_bias={s.ticker: s.bias for s in report.signals},
            )
        )

    n = len(takes)
    if n < 2:
        # _modal_and_agreement already returns (modal-or-None, None, False) for a
        # single/zero take — reuse it instead of reimplementing the degraded shape.
        modal_bias, _agreement, divergent = _modal_and_agreement([t.bias for t in takes])
        return ConsensusReport(
            n_providers=n,
            bias_agreement=None,
            modal_bias=modal_bias,
            divergent=divergent,
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
