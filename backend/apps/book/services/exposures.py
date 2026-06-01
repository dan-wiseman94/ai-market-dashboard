"""Unify positions + theses + coverage into one conviction-weighted, signed
directional-exposure list per ticker. Never raises; missing sources contribute
nothing."""

from __future__ import annotations

import logging

from apps.book import constants as C

log = logging.getLogger(__name__)

_THESIS_SIGN = {"bullish": 1, "bearish": -1, "neutral": 0}
_COVERAGE_SIGN = {"bull": 1, "bear": -1, "neutral": 0}
_POSITION_SIGN = {"long": 1, "short": -1}


def _add(acc: dict, ticker: str, signed: float, source: str, dollar: float | None = None) -> None:
    ticker = (ticker or "").upper()
    if not ticker:
        return
    row = acc.setdefault(
        ticker,
        {"ticker": ticker, "net_signed": 0.0, "dollar": 0.0, "sources": [], "has_dollar": False},
    )
    row["net_signed"] += signed
    if source not in row["sources"]:
        row["sources"].append(source)
    if dollar is not None:
        row["dollar"] += dollar
        row["has_dollar"] = True


def build_exposures() -> list[dict]:
    acc: dict[str, dict] = {}

    try:
        from apps.thesis.models import Thesis

        for t in Thesis.objects.filter(status="open"):
            _add(acc, t.ticker, _THESIS_SIGN.get(t.direction, 0) * (t.conviction or 0), "thesis")
    except Exception:
        log.warning("book.exposures.thesis_failed", exc_info=True)

    try:
        from apps.coverage.models import CoverageNote

        for n in CoverageNote.objects.all():
            _add(acc, n.ticker, _COVERAGE_SIGN.get(n.stance, 0) * (n.conviction or 0), "coverage")
    except Exception:
        log.warning("book.exposures.coverage_failed", exc_info=True)

    try:
        from django.utils import timezone

        from apps.market.returns import nearest_bar_close
        from apps.portfolio.models import Position

        now = timezone.now()
        for p in Position.objects.filter(status="open"):
            conv = (
                p.thesis.conviction if p.thesis_id and p.thesis else None
            ) or C.DEFAULT_CONVICTION
            sign = _POSITION_SIGN.get(p.direction, 0)
            last = nearest_bar_close(p.ticker.upper(), now)
            dollar = (float(p.quantity) * last * sign) if last is not None else None
            _add(acc, p.ticker, sign * conv, "position", dollar=dollar)
    except Exception:
        log.warning("book.exposures.position_failed", exc_info=True)

    rows = []
    for row in acc.values():
        row["abs_exposure"] = abs(row["net_signed"])
        row["dollar"] = row["dollar"] if row["has_dollar"] else None
        del row["has_dollar"]
        rows.append(row)
    rows.sort(key=lambda r: r["abs_exposure"], reverse=True)
    return rows
