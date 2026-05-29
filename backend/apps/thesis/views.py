"""ViewSet for the Thesis app."""

from __future__ import annotations

from datetime import timedelta

from django.conf import settings
from django.db import models, transaction
from django.utils import timezone
from rest_framework import mixins, viewsets
from rest_framework.decorators import action
from rest_framework.request import Request
from rest_framework.response import Response

from apps.profiles.models import TradingProfile
from apps.snapshots.models import Snapshot, SnapshotSection
from apps.threads.models import Thread

from .models import DecisionJournalEntry, PostMortem, Thesis
from .serializers import JournalEntrySerializer, ThesisSerializer
from .services.postmortem import schedule_postmortems
from .tasks import run_postmortem_task

# Statuses that mean the thesis is no longer "open" — derived from the model to
# avoid divergence when a new status is added later.
_CLOSED_STATUSES = {s for s, _ in Thesis.STATUS_CHOICES if s != "open"}


def _resolve_fk[M: models.Model](model: type[M], pk: object) -> M | None:
    """Look up *model* by pk, returning None for a falsy pk or unknown row."""
    if not pk:
        return None
    return model.objects.filter(id=pk).first()


def _error(code: str, message: str, status: int) -> Response:
    return Response({"code": code, "message": message}, status=status)


def _default_entry_from_snapshot(snapshot: Snapshot, ticker: str) -> str | None:
    """Best-effort: read the last price for *ticker* from the snapshot's quotes section."""
    try:
        section = SnapshotSection.objects.filter(
            snapshot=snapshot,
            kind="quotes",
            status="done",
        ).first()
        if section is None or not isinstance(section.payload, dict):
            return None
        price = section.payload.get(ticker, {}).get("last")
        return str(price) if price is not None else None
    except (TypeError, KeyError, AttributeError):
        return None


class ThesisViewSet(viewsets.ModelViewSet):
    queryset = (
        Thesis.objects.select_related("profile", "thread", "snapshot", "review_thread")
        .prefetch_related("postmortems")
        .order_by("-opened_at")
    )
    serializer_class = ThesisSerializer

    def create(self, request: Request, *args: object, **kwargs: object) -> Response:
        data = request.data

        # Resolve optional FKs from the submitted ids (unknown id -> None)
        profile = _resolve_fk(TradingProfile, data.get("profile_id"))
        thread = _resolve_fk(Thread, data.get("thread_id"))
        snapshot = _resolve_fk(Snapshot, data.get("snapshot_id"))

        # Mutable copy of posted data so we can inject defaults
        mutable_data = dict(data)

        # Default entry_price from the snapshot's quotes section when the client
        # hasn't provided one explicitly.
        if snapshot is not None and not mutable_data.get("entry_price"):
            ticker = (mutable_data.get("ticker") or "").upper()
            if ticker:
                derived = _default_entry_from_snapshot(snapshot, ticker)
                if derived is not None:
                    mutable_data["entry_price"] = derived

        serializer = ThesisSerializer(data=mutable_data)
        serializer.is_valid(raise_exception=True)

        with transaction.atomic():
            thesis = serializer.save(
                profile=profile,
                thread=thread,
                snapshot=snapshot,
            )
            # Lay down the 7/30/90-day post-mortems for this new thesis.
            schedule_postmortems(thesis)
            from apps.triggers.services.thesis_guard import sync_thesis_guard

            sync_thesis_guard(thesis)

        return Response(ThesisSerializer(thesis).data, status=201)

    def perform_update(self, serializer):
        thesis = serializer.save()
        from apps.triggers.services.thesis_guard import sync_thesis_guard

        sync_thesis_guard(thesis)

    @action(detail=True, methods=["post"])
    def close(self, request: Request, pk: str | None = None) -> Response:
        """Close or invalidate the thesis.

        Body: {status: "closed_win"|"closed_loss"|"closed_scratch"|"invalidated",
               close_note?: str}
        """
        thesis = self.get_object()
        new_status = (request.data.get("status") or "").strip()
        if new_status not in _CLOSED_STATUSES:
            return _error(
                "invalid_status",
                f"status must be one of: {', '.join(sorted(_CLOSED_STATUSES))}",
                400,
            )
        thesis.status = new_status
        if "close_note" in request.data:
            thesis.close_note = (request.data.get("close_note") or "").strip()
        thesis.closed_at = timezone.now()
        thesis.save()
        from apps.triggers.services.thesis_guard import sync_thesis_guard

        sync_thesis_guard(thesis)
        return Response(ThesisSerializer(thesis).data, status=200)

    @action(detail=True, methods=["post"], url_path="run-postmortem")
    def run_postmortem(self, request: Request, pk: str | None = None) -> Response:
        """Replay a post-mortem for this thesis now (out of band of the scheduler).

        Picks which PostMortem to run:
        1. If a *scheduled* PM is already due, run the earliest such one.
        2. Otherwise create/get an ad-hoc PM for the smallest configured horizon
           whose due window has elapsed; if none has elapsed yet, fall back to
           the smallest horizon so the replay still works immediately.

        Returns 202 with the chosen pm id; the actual run is dispatched async.
        Run-now resets the chosen PM to "scheduled" before dispatch, so it
        doubles as an explicit replay AND recovers a crashed/stuck "running"
        row. The atomic claim in run_postmortem then ensures exactly one run
        happens per click even if beat dispatches the same row concurrently.
        """
        thesis = self.get_object()  # raises 404 for unknown pk
        now = timezone.now()

        # 1) An already-due scheduled PM takes priority.
        pm = (
            PostMortem.objects.filter(thesis=thesis, status="scheduled", due_at__lte=now)
            .order_by("due_at")
            .first()
        )

        if pm is None:
            # 2) Smallest horizon whose due window has elapsed, else the smallest
            #    configured horizon (horizons are sorted ascending).
            horizons = sorted(settings.THESIS_POSTMORTEM_HORIZONS)
            elapsed = [d for d in horizons if thesis.opened_at + timedelta(days=d) <= now]
            horizon = elapsed[0] if elapsed else horizons[0]
            pm, _ = PostMortem.objects.get_or_create(
                thesis=thesis,
                horizon_days=horizon,
                defaults={"due_at": thesis.opened_at + timedelta(days=horizon)},
            )

        # Reset to a runnable state so run-now is an explicit replay and also
        # recovers a row left stuck in "running" by a crashed worker.
        PostMortem.objects.filter(id=pm.id).update(status="scheduled", completed_at=None)
        run_postmortem_task.delay(pm.id)
        return Response({"detail": "scheduled", "postmortem_id": pm.id}, status=202)


class JournalEntryViewSet(
    mixins.CreateModelMixin,
    mixins.ListModelMixin,
    viewsets.GenericViewSet,
):
    """Create and list decision journal entries.

    Create: POST /api/journal/  {thread_id, decision, note?, thesis_id?, snapshot_id?}
    List:   GET  /api/journal/?thread=<id>   (filter by thread; omit for all entries)
    """

    serializer_class = JournalEntrySerializer

    def get_queryset(self):  # type: ignore[override]
        qs = DecisionJournalEntry.objects.select_related("thread", "thesis", "snapshot").order_by(
            "-created_at"
        )
        thread_id = self.request.query_params.get("thread")
        if thread_id:
            try:
                qs = qs.filter(thread_id=int(thread_id))
            except (ValueError, TypeError):
                return qs.none()
        return qs
