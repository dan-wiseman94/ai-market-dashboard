"""Shared abstract model bases — the lowest import layer; any app may import these.

Models the "directional call + how it scored" domain shared by thesis.PostMortem
and observer.AIPrediction: common forward_return_pct/verdict columns plus the
parallel resolution logic. Concrete models inherit the relevant base(s).
"""

from __future__ import annotations

from django.db import models

VERDICT_CHOICES: list[tuple[str, str]] = [
    ("correct", "Correct"),
    ("incorrect", "Incorrect"),
    ("mixed", "Mixed"),
    ("inconclusive", "Inconclusive"),
]

DIRECTION_CHOICES: list[tuple[str, str]] = [
    ("bullish", "Bullish"),
    ("bearish", "Bearish"),
    ("neutral", "Neutral"),
]


class TimeStamped(models.Model):
    """created_at (indexed) + updated_at, the pair hand-rolled across ~15 tables."""

    created_at = models.DateTimeField(auto_now_add=True, db_index=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        abstract = True


class DirectionalCall(models.Model):
    """A stated directional call on a ticker (shared by Thesis and AIPrediction)."""

    ticker = models.CharField(max_length=16, db_index=True)
    direction = models.CharField(max_length=16, choices=DIRECTION_CHOICES)
    horizon_days = models.PositiveIntegerField()
    invalidation_price = models.DecimalField(max_digits=14, decimal_places=4, null=True, blank=True)
    invalidation_note = models.CharField(max_length=300, blank=True, default="")

    class Meta:
        abstract = True


class Resolution(models.Model):
    """The scored outcome of a directional call — the byte-identical columns shared
    by PostMortem and AIPrediction. The resolution *timestamp* stays on each
    concrete model (PostMortem.completed_at vs AIPrediction.resolved_at) since the
    names diverge; unifying those is a later, rename-bearing step.

    ``verdict`` values come from :data:`VERDICT_CHOICES` and are computed
    deterministically by :func:`apps.market.returns.direction_verdict`.
    """

    forward_return_pct = models.FloatField(null=True, blank=True)
    verdict = models.CharField(max_length=16, choices=VERDICT_CHOICES, blank=True, default="")

    class Meta:
        abstract = True

    @classmethod
    def claim(cls, pk: int, *, frm: str, to: str) -> bool:
        """Atomic compare-and-set on the concrete model's ``status`` column: exactly
        one caller wins the transition (the rest get False). The idempotent
        scheduled→running / open→resolving claim that stops a beat re-tick and a
        manual run from double-billing. Concrete models keep their own ``status``
        choices — this only moves the value.
        """
        # cls is always a concrete subclass at runtime (with a manager + status);
        # django-stubs only sees the abstract base, hence the narrow ignore.
        manager = cls.objects  # type: ignore[attr-defined]
        return manager.filter(pk=pk, status=frm).update(status=to) == 1
