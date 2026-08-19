"""Lesson distillation: cluster decisive post-mortem lessons into
recurring, tagged rules via embeddings (greedy cosine-threshold) — deterministic,
no AI cost. Look-ahead-safe: reads only decisive, completed post-mortems.

Each not-yet-distilled post-mortem's lesson bullets are embedded and either merged
into the nearest existing Lesson (cosine >= cutoff) or seeded as a new one. A
post-mortem is processed once — it is skipped on later runs once linked to any
Lesson (the `lessons__isnull` filter) — so the task is safe to run on a schedule.
"""

from __future__ import annotations

import logging

import numpy as np
from django.utils import timezone

log = logging.getLogger(__name__)

_SIMILARITY_CUTOFF = 0.80  # cosine sim at/above which a bullet joins an existing cluster
_LESSON_REPORT_KEYS = ("lessons", "what_missed")


def distill_lessons() -> dict:
    """Process not-yet-distilled decisive post-mortems into Lesson clusters.

    Returns a summary dict. Best-effort: returns early (no error) when embeddings
    are unavailable or there is nothing new to process.
    """
    from apps.recall.embeddings import embed
    from apps.thesis.models import Lesson, PostMortem

    pending = list(
        PostMortem.objects.filter(status="done", verdict__in=["correct", "incorrect"])
        .filter(lessons__isnull=True)  # not yet linked to any Lesson
        .select_related("thesis")
        .distinct()
    )
    items: list[tuple] = [(pm, bullet) for pm in pending for bullet in report_bullets(pm)]
    if not items:
        return {"processed": 0, "created": 0, "merged": 0}

    vecs = embed([b for _pm, b in items])
    if not vecs:
        log.warning("lessons.distill: embeddings unavailable, skipping run")
        return {"processed": 0, "created": 0, "merged": 0, "skipped": "no_embeddings"}

    existing = list(Lesson.objects.exclude(embedding=None))
    ex_vecs = [np.asarray(lesson.embedding, dtype=float) for lesson in existing]

    created = merged = 0
    for (pm, bullet), vec in zip(items, vecs, strict=True):
        v = np.asarray(vec, dtype=float)
        match = _nearest(v, ex_vecs, existing)
        if match is not None:
            _attach(match, pm)
            merged += 1
        else:
            lesson = Lesson.objects.create(text=bullet, embedding=vec)
            _attach(lesson, pm)
            existing.append(lesson)
            ex_vecs.append(v)
            created += 1
    return {"processed": len(items), "created": created, "merged": merged}


def report_bullets(pm) -> list[str]:
    """Lesson bullets from a post-mortem's report — the ``lessons`` / ``what_missed``
    free-text lists, read defensively (report is free-form JSON).

    Single source for which report keys count as lessons, shared by this clusterer
    and the coach's lessons block (imported there function-locally) so the two can't
    disagree on what a lesson is.
    """
    report = pm.report if isinstance(pm.report, dict) else {}
    out: list[str] = []
    for key in _LESSON_REPORT_KEYS:
        val = report.get(key)
        if isinstance(val, list):
            out.extend(str(x).strip() for x in val if str(x).strip())
    return out


def _nearest(v, ex_vecs: list, existing: list):
    if not ex_vecs:
        return None
    sims = [_cosine(v, e) for e in ex_vecs]
    best = int(np.argmax(sims))
    return existing[best] if sims[best] >= _SIMILARITY_CUTOFF else None


def _cosine(a, b) -> float:
    na = float(np.linalg.norm(a))
    nb = float(np.linalg.norm(b))
    if na == 0.0 or nb == 0.0:
        return 0.0
    return float(np.dot(a, b) / (na * nb))


def _attach(lesson, pm) -> None:
    """Link a post-mortem to a lesson cluster: merge tags, bump support, restamp."""
    from apps.market.services.fundamentals import sector_for_ticker

    lesson.evidence.add(pm)
    tags = lesson.tags if isinstance(lesson.tags, dict) else {}
    directions = set(tags.get("directions", []))
    sectors = set(tags.get("sectors", []))
    if pm.thesis.direction:
        directions.add(pm.thesis.direction)
    sector = sector_for_ticker(pm.thesis.ticker)
    if sector:
        sectors.add(sector)
    lesson.tags = {"directions": sorted(directions), "sectors": sorted(sectors)}
    lesson.support_n = lesson.evidence.count()
    lesson.last_seen = timezone.now()
    lesson.save(update_fields=["tags", "support_n", "last_seen", "updated_at"])
