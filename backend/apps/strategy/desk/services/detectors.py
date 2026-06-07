"""Deterministic anomaly detectors over existing data + services. Each returns a
list of candidate dicts {anomaly_type, ticker, severity, evidence}. Best-effort;
a failing detector contributes nothing. Composes F1 (regime) + F2 (book)."""

from __future__ import annotations

import logging
import sys
from datetime import timedelta

from django.utils import timezone

from apps.strategy.desk import constants as C

log = logging.getLogger(__name__)


def _daily(ticker: str, n: int) -> list[float]:
    from apps.market.models import OHLCBar

    rows = list(
        OHLCBar.objects.filter(ticker=ticker.upper(), timeframe="1d")
        .order_by("-ts")
        .values_list("close", flat=True)[:n]
    )
    return [float(c) for c in reversed(rows)]


def detect_price(universe: list[str]) -> list[dict]:
    out = []
    for t in universe:
        try:
            closes = _daily(t, 2)
            if len(closes) < 2 or not closes[-2]:
                continue
            pct = (closes[-1] / closes[-2] - 1.0) * 100.0
            if abs(pct) >= C.PCT_CHANGE:
                out.append(
                    {
                        "anomaly_type": "price_move",
                        "ticker": t.upper(),
                        "severity": abs(pct),
                        "evidence": {"pct_change": round(pct, 2)},
                    }
                )
        except Exception:
            log.warning("desk.detect_price.failed t=%s", t, exc_info=True)
    return out


def detect_options(universe: list[str]) -> list[dict]:
    from apps.analytics.services.unusual_options import unusual_options

    now = timezone.now()
    out = []
    for t in universe:
        try:
            lines = unusual_options(ticker=t.upper(), at=now, top_n=5)
            if lines:
                top = max(lines, key=lambda x: x.get("score", 0))
                out.append(
                    {
                        "anomaly_type": "unusual_options",
                        "ticker": t.upper(),
                        "severity": float(top.get("score", 0)),
                        "evidence": {"line": top},
                    }
                )
        except Exception:
            log.warning("desk.detect_options.failed t=%s", t, exc_info=True)
    return out


def detect_regime_change() -> list[dict]:
    from apps.strategy.models import RegimeReading

    last2 = list(RegimeReading.objects.order_by("-created_at")[:2])
    if len(last2) == 2 and last2[0].composite != last2[1].composite:
        return [
            {
                "anomaly_type": "regime_change",
                "ticker": "",
                "severity": 10.0,
                "evidence": {"from": last2[1].composite, "to": last2[0].composite},
            }
        ]
    return []


def detect_book() -> list[dict]:
    from apps.book.models import BookSnapshot

    last2 = list(BookSnapshot.objects.order_by("-created_at")[:2])
    if len(last2) < 2:
        return []
    cur, prev = last2[0], last2[1]
    hhi_jump = (cur.concentration or {}).get("hhi", 0) - (prev.concentration or {}).get("hhi", 0)
    newly_misaligned = (cur.regime_fit or {}).get("alignment") == "misaligned" and (
        prev.regime_fit or {}
    ).get("alignment") != "misaligned"
    if hhi_jump >= 0.1 or newly_misaligned:
        return [
            {
                "anomaly_type": "book_deterioration",
                "ticker": "",
                "severity": 8.0,
                "evidence": {"hhi_jump": round(hhi_jump, 3), "newly_misaligned": newly_misaligned},
            }
        ]
    return []


def detect_breadth_divergence() -> list[dict]:
    """Bearish index-vs-breadth divergence: the tape is in an uptrend while
    participation is narrow/deteriorating (fewer names carrying the rally).
    Reads the latest F1 regime axes — book-wide, no per-ticker scan."""
    from apps.strategy.models import RegimeReading

    latest = RegimeReading.objects.order_by("-created_at").first()
    if not latest:
        return []
    axes = latest.axes or {}
    trend = axes.get("trend")
    breadth = axes.get("breadth")
    if trend == "Uptrend" and breadth in {"Narrow", "Deteriorating"}:
        return [
            {
                "anomaly_type": "breadth_divergence",
                "ticker": "",
                "severity": 7.0,
                "evidence": {"trend": trend, "breadth": breadth},
            }
        ]
    return []


def detect_earnings_proximity(universe: list[str]) -> list[dict]:
    """A name you watch reports within EARNINGS_WITHIN_DAYS — a heads-up that the
    house view may be about to be tested. Reads the stored MarketEvent calendar
    directly (no per-ticker network fill — detectors stay cheap/deterministic)."""
    from apps.market.models import MarketEvent

    now = timezone.now()
    today = now.date()
    horizon = now + timedelta(days=C.EARNINGS_WITHIN_DAYS)
    tickers = [t.upper() for t in universe if t]
    if not tickers:
        return []
    out = []
    for e in MarketEvent.objects.filter(
        kind="earnings", ticker__in=tickers, event_time__gte=now, event_time__lte=horizon
    ).order_by("event_time"):
        days = (e.event_time.date() - today).days
        out.append(
            {
                "anomaly_type": "earnings_soon",
                "ticker": e.ticker.upper(),
                # Sooner earnings rank higher (a low-urgency surface overall).
                "severity": float(C.EARNINGS_WITHIN_DAYS - days + 1),
                "evidence": {"days_until": days, "title": e.title},
            }
        )
    return out


def detect_coverage_stale(universe: list[str]) -> list[dict]:
    from apps.strategy.models import CoverageNote

    cutoff = timezone.now() - timedelta(days=C.COVERAGE_STALE_DAYS)
    out = []
    for note in CoverageNote.objects.filter(updated_at__lt=cutoff):
        closes = _daily(note.ticker, 11)
        if len(closes) >= 11 and closes[0]:
            move = abs(closes[-1] / closes[0] - 1.0) * 100.0
            if move >= C.COVERAGE_MOVE_PCT:
                out.append(
                    {
                        "anomaly_type": "coverage_stale",
                        "ticker": note.ticker.upper(),
                        "severity": move,
                        "evidence": {"move_pct": round(move, 1)},
                    }
                )
    return out


def run_detectors(universe: list[str]) -> list[dict]:
    mod = sys.modules[__name__]
    out: list[dict] = []
    for name in (
        "detect_price",
        "detect_options",
        "detect_coverage_stale",
        "detect_earnings_proximity",
    ):
        try:
            out.extend(getattr(mod, name)(universe))
        except Exception:
            log.warning("desk.detector_failed %s", name, exc_info=True)
    for name in ("detect_regime_change", "detect_book", "detect_breadth_divergence"):
        try:
            out.extend(getattr(mod, name)())
        except Exception:
            log.warning("desk.detector_failed %s", name, exc_info=True)
    return out
