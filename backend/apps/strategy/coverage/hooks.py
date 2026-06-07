"""Observer → coverage integration (M14 F3).

An observer fire on a ticker you already cover (a ``CoverageNote`` exists) queues
a house-view revision. Opt-in by virtue of the note existing; bounded to the
snapshot's primary ticker to keep per-fire cost to a single revision.
"""

from __future__ import annotations

import logging

log = logging.getLogger(__name__)


def maybe_revise_from_snapshot(snapshot) -> None:
    """Queue a coverage revision iff ``snapshot``'s primary ticker is covered."""
    ticker = (snapshot.primary_ticker or "").upper()
    if not ticker:
        return

    from apps.strategy.models import CoverageNote

    if not CoverageNote.objects.filter(ticker=ticker).exists():
        return

    from apps.strategy.tasks import revise_from_observation

    revise_from_observation.delay(ticker, snapshot.id)
