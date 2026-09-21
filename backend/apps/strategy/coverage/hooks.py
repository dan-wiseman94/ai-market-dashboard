"""Observer → coverage integration.

An observer fire queues a house-view revision for the snapshot's primary ticker:
a revision when the ticker is already covered, the first note when it is not and
auto-create is on. Bounded to the primary ticker, so a fire costs at most one
revision.
"""

from __future__ import annotations

import logging

log = logging.getLogger(__name__)


def maybe_revise_from_snapshot(snapshot) -> None:
    """Queue a coverage revision for ``snapshot``'s primary ticker."""
    ticker = (snapshot.primary_ticker or "").upper()
    if not ticker:
        return

    from apps.strategy.coverage.constants import auto_create_enabled
    from apps.strategy.models import CoverageNote

    if not CoverageNote.objects.filter(ticker=ticker).exists() and not auto_create_enabled():
        return

    from apps.strategy.tasks import revise_from_observation

    revise_from_observation.delay(ticker, snapshot.id)
