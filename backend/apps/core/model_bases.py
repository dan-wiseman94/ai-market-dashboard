"""Shared abstract model bases — the lowest import layer; any app may import these.

Unifies the duplicated "directional call + how it scored" domain that was modelled
separately on thesis.PostMortem and predictions.AIPrediction (byte-identical
forward_return_pct/verdict columns + parallel resolution logic). Concrete models
inherit the relevant base(s); the columns are unchanged, so retrofitting an
existing model is a state-only migration.
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
