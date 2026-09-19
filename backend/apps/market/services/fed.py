"""Federal Reserve communications via the Fed's public RSS feeds. Keyless.

Follows the treasury.py/edgar.py contract: requests + descriptive User-Agent,
Redis-cached, returns [] on ANY failure (a quiet feed or a Fed outage must
never fail a snapshot section)."""

from __future__ import annotations

import logging
import xml.etree.ElementTree as ET  # nosemgrep: python.lang.security.use-defused-xml.use-defused-xml -- DTD/entities rejected + size-capped in _parse below; defusedxml unavailable in this worktree's baked images
from email.utils import parsedate_to_datetime

import requests

from apps.market import cache
from apps.market.services.safe_log import safe_err

log = logging.getLogger(__name__)

FEEDS = {
    # Confirmed live (HTTP 200, text/xml) against https://www.federalreserve.gov/feeds/
    # at implementation time (Step 1).
    "press_monetary": "https://www.federalreserve.gov/feeds/press_monetary.xml",
    "speeches": "https://www.federalreserve.gov/feeds/speeches.xml",
    "testimony": "https://www.federalreserve.gov/feeds/testimony.xml",
}
_MAX_BYTES = 512 * 1024
_UA = "Ledger single-user market dashboard (github.com/dan-wiseman94/ledger)"

_MOCK_ITEMS = [
    {
        "kind": "press_monetary",
        "title": "Federal Reserve issues FOMC statement",
        "url": "https://www.federalreserve.gov/newsevents/pressreleases/mock.htm",
        "published": "2026-09-16T18:00:00+00:00",
        "summary": "Mock FOMC statement.",
    },
    {
        "kind": "speeches",
        "title": "Chair speech: The economic outlook",
        "url": "https://www.federalreserve.gov/newsevents/speech/mock.htm",
        "published": "2026-09-15T14:00:00+00:00",
        "summary": "Mock speech.",
    },
]


def fetch_fed_communications(*, limit: int = 10) -> list[dict]:
    """Newest-first items across all feeds; [] on any failure."""
    if _is_mock():
        return list(_MOCK_ITEMS)[:limit]
    items: list[dict] = []
    for kind, url in FEEDS.items():
        items.extend(_fetch_feed(kind, url))
    items.sort(key=lambda i: i.get("published") or "", reverse=True)
    return items[:limit]


def _is_mock() -> bool:
    from apps.core.mocks import is_mock_mode

    return is_mock_mode()


def _fetch_feed(kind: str, url: str) -> list[dict]:
    def _pull() -> list[dict]:
        resp = requests.get(url, timeout=10, headers={"User-Agent": _UA}, stream=True)
        resp.raise_for_status()
        raw = resp.raw.read(_MAX_BYTES + 1, decode_content=True)
        if len(raw) > _MAX_BYTES:
            raise ValueError("feed exceeds size cap")
        return _parse(kind, raw)

    try:
        return cache.get_or_fetch(
            f"market:fed:{kind}", ttl_seconds=cache.ttl_for_kind("fed"), fetcher=_pull
        )
    except Exception as exc:
        log.warning("market.fed fetch failed for %s: %s", kind, safe_err(exc))
        return []


def _parse(kind: str, raw: bytes) -> list[dict]:
    # The defusedxml attack classes (XXE, billion-laughs) both require DTD or
    # entity declarations — reject them outright, plus the size cap upstream.
    # This is defusedxml's forbid_dtd/forbid_entities behavior without the dep
    # (the worktree test harness reuses baked images and can't add packages).
    if b"<!DOCTYPE" in raw or b"<!ENTITY" in raw:
        raise ValueError("DTD/entity declarations rejected")
    root = ET.fromstring(raw)  # noqa: S314
    out: list[dict] = []
    for item in root.iter("item"):
        title = (item.findtext("title") or "").strip()
        if not title:
            continue
        pub = (item.findtext("pubDate") or "").strip()
        try:
            published = parsedate_to_datetime(pub).isoformat() if pub else None
        except (TypeError, ValueError):
            published = None
        out.append(
            {
                "kind": kind,
                "title": title,
                "url": (item.findtext("link") or "").strip(),
                "published": published,
                "summary": (item.findtext("description") or "").strip()[:300],
            }
        )
    return out
