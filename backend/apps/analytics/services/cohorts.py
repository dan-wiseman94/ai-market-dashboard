"""Setup-cohort base rates: the OUTSIDE view — how calls resembling the
current situation (same direction, same sector when known) have resolved across
the whole book, excluding the ticker in question. The base-rate corrective the
per-ticker track record doesn't provide ("you've been too bullish on this KIND of
setup").

Reads decisive PostMortem verdicts only (status='done', correct/incorrect) — these
are look-ahead-safe: a horizon-H post-mortem completes >= H days after the thesis
opened, so nothing post-trade leaks into a contemporaneous call.
"""

from __future__ import annotations

_MIN_COHORT_N = 4  # below this a base rate is noise, not signal


def cohort_base_rate(*, direction: str, ticker: str) -> dict | None:
    """Best available outside-view base rate for `direction` calls.

    Prefers the same-sector cohort when it clears the min-n floor, else the
    all-sector cohort. Excludes `ticker`'s own theses (that is the per-ticker
    block's job). Returns ``{scope, n, correct, hit_rate}`` (scope = sector name
    or ``"all"``), or None when neither cohort clears the floor.
    """
    if not direction:
        return None
    from apps.thesis.models import PostMortem

    base = PostMortem.objects.filter(
        status="done", verdict__in=["correct", "incorrect"], thesis__direction=direction
    ).exclude(thesis__ticker=(ticker or "").upper())

    sector = _sector_for(ticker)
    if sector:
        sector_tickers = _sector_tickers(sector)
        if sector_tickers:
            sec = _summarize(base.filter(thesis__ticker__in=sector_tickers), scope=sector)
            if sec is not None:
                return sec
    return _summarize(base, scope="all")


def _summarize(qs, *, scope: str) -> dict | None:
    verdicts = list(qs.values_list("verdict", flat=True))
    n = len(verdicts)
    if n < _MIN_COHORT_N:
        return None
    correct = sum(1 for v in verdicts if v == "correct")
    return {"scope": scope, "n": n, "correct": correct, "hit_rate": round(correct / n, 4)}


def _sector_for(ticker: str) -> str:
    if not ticker:
        return ""
    from apps.market.models import CompanyFundamentals

    sector = (
        CompanyFundamentals.objects.filter(ticker=ticker.upper())
        .exclude(sector="")
        .values_list("sector", flat=True)
        .first()
    )
    return sector or ""


def _sector_tickers(sector: str) -> list[str]:
    from apps.market.models import CompanyFundamentals

    return list(CompanyFundamentals.objects.filter(sector=sector).values_list("ticker", flat=True))
