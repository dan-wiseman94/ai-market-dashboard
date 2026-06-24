from __future__ import annotations

import logging

from django.db import transaction
from django.utils import timezone

from apps.book import constants as C
from apps.book.models import BookSnapshot
from apps.book.services.analytics import concentration, near_invalidation, regime_fit
from apps.book.services.correlation import correlation_clusters
from apps.book.services.exposures import build_exposures
from apps.book.services.narrative import book_narrative
from apps.book.services.var_beta import compute_var_beta

log = logging.getLogger(__name__)


def current_book() -> BookSnapshot | None:
    return BookSnapshot.objects.order_by("-created_at").first()


def _build_payload() -> dict:
    exposures = build_exposures()
    tickers = [e["ticker"] for e in exposures]
    conc = concentration(exposures)
    clusters = correlation_clusters(tickers)
    fit = regime_fit(exposures)
    near = near_invalidation()
    return {
        "exposures": exposures,
        "concentration": conc,
        "clusters": clusters,
        "regime_fit": fit,
        "near_invalidation": near,
        "var_beta": compute_var_beta(exposures),
    }


def _maybe_alert(prior: BookSnapshot, data: dict) -> None:
    prior_hhi = (prior.concentration or {}).get("hhi", 0.0)
    new_hhi = data["concentration"].get("hhi", 0.0)
    worsened = new_hhi - prior_hhi >= C.HHI_ALERT_DELTA
    misaligned = data["regime_fit"].get("alignment") == "misaligned"
    prior_aligned = (prior.regime_fit or {}).get("alignment") != "misaligned"
    if worsened or (misaligned and prior_aligned):
        from apps.observer.services.notifications import notify

        bits = []
        if worsened:
            bits.append(f"concentration up (HHI {prior_hhi:.2f}->{new_hhi:.2f})")
        if misaligned and prior_aligned:
            bits.append(data["regime_fit"].get("note", "regime misalignment"))
        notify(
            user_id=None,
            kind="book",
            title="Book risk changed",
            body="; ".join(bits),
            link="/book",
            meta={"hhi": new_hhi},
        )


def compute_and_store_book() -> BookSnapshot:
    """Build the whole-book X-ray and persist one row per day (idempotent same-day
    update). Alerts on concentration/regime-fit deterioration vs the prior day."""
    data = _build_payload()
    data["narrative"] = book_narrative(data)  # best-effort, "" on failure
    today = timezone.now().date()
    with transaction.atomic():
        prior = BookSnapshot.objects.exclude(as_of_date=today).order_by("-created_at").first()
        snap, _created = BookSnapshot.objects.update_or_create(as_of_date=today, defaults=data)
    if prior is not None:
        try:
            _maybe_alert(prior, data)
        except Exception:
            log.warning("book.alert_failed", exc_info=True)
    return snap
