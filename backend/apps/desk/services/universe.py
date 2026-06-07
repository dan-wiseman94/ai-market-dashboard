"""The set of tickers the sweep cares about: watchlist + covered + open theses +
open positions. Never raises; a failing source contributes nothing."""

from __future__ import annotations

import logging

log = logging.getLogger(__name__)


def _watchlist():
    from apps.profiles.models import WatchlistSymbol

    return WatchlistSymbol.objects.values_list("ticker", flat=True)


def _coverage():
    from apps.coverage.models import CoverageNote

    return CoverageNote.objects.values_list("ticker", flat=True)


def _theses():
    from apps.thesis.models import Thesis

    return Thesis.objects.filter(status="open").values_list("ticker", flat=True)


def _positions():
    from apps.thesis.models import Position

    return Position.objects.filter(status="open").values_list("ticker", flat=True)


def build_universe() -> list[str]:
    tickers: set[str] = set()
    for src in (_watchlist, _coverage, _theses, _positions):
        try:
            for t in src():
                if t:
                    tickers.add(t.upper())
        except Exception:
            log.warning("desk.universe.source_failed src=%s", src.__name__, exc_info=True)
    return sorted(tickers)
