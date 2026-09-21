"""ViewSet for the Thesis app."""

from __future__ import annotations

from datetime import timedelta

from django.conf import settings
from django.db import models, transaction
from django.utils import timezone
from drf_spectacular.utils import OpenApiParameter, extend_schema, extend_schema_view
from rest_framework import mixins, viewsets
from rest_framework.decorators import action
from rest_framework.request import Request
from rest_framework.response import Response

from apps.core.http import ErrorEnvelopeSerializer, error_response
from apps.profiles.models import TradingProfile
from apps.snapshots.models import Snapshot
from apps.snapshots.primary import last_price
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
    # `_default_manager` (not `.objects`) so this resolves on the M TypeVar — django-stubs
    # only injects `.objects` onto concrete model classes, not a `type[M]` bound.
    return model._default_manager.filter(id=pk).first()


def _error(code: str, message: str, status: int) -> Response:
    return error_response(code, message, status=status)


_TRUTHY = {"1", "true", "yes", "on"}


def _flag(raw: object) -> bool:
    return str(raw or "").strip().lower() in _TRUTHY


def _default_entry_from_snapshot(snapshot: Snapshot, ticker: str) -> str | None:
    """Best-effort: read the last price for *ticker* from the snapshot's quotes section."""
    price = last_price(snapshot, ticker)
    return str(price) if price is not None else None


@extend_schema_view(
    list=extend_schema(
        parameters=[
            OpenApiParameter(
                "archived",
                str,
                enum=["0", "1", "all"],
                description=(
                    "Which theses to list: omitted or falsy for live ones only (the "
                    "default), truthy for archived only, 'all' for both."
                ),
            )
        ]
    ),
    # DELETE archives by default and only really deletes under ?purge=true, so the
    # parameter is the difference between reversible and destructive. Declared here
    # rather than left in docstring prose: a generated client cannot read prose.
    destroy=extend_schema(
        parameters=[
            OpenApiParameter(
                "purge",
                bool,
                description=(
                    "true to delete the row outright instead of archiving it. Answers "
                    "409 when a completed post-mortem exists, because dropping the "
                    "thesis would cascade away the calibration it feeds."
                ),
            )
        ],
        responses={204: None, 409: ErrorEnvelopeSerializer},
    ),
)
class ThesisViewSet(viewsets.ModelViewSet):
    queryset = (
        Thesis.objects.select_related("profile", "thread", "snapshot", "review_thread")
        .prefetch_related("postmortems")
        .order_by("-opened_at")
    )
    serializer_class = ThesisSerializer

    def get_queryset(self):  # type: ignore[override]
        """The list hides archived theses; ``?archived=1`` shows only those and
        ``?archived=all`` shows both. Detail routes never filter, so an archived
        thesis stays readable (and restorable) at its own URL, and every link
        recorded against it — recall documents, journal entries — still resolves.
        """
        qs = super().get_queryset()
        if self.action != "list":
            return qs
        archived = (self.request.query_params.get("archived") or "").strip().lower()
        if archived == "all":
            return qs
        if _flag(archived):
            return qs.exclude(archived_at=None)
        return qs.filter(archived_at=None)

    def create(self, request: Request, *args: object, **kwargs: object) -> Response:
        data = request.data

        profile = _resolve_fk(TradingProfile, data.get("profile_id"))
        thread = _resolve_fk(Thread, data.get("thread_id"))
        snapshot = _resolve_fk(Snapshot, data.get("snapshot_id"))

        # Mutable copy of posted data so we can inject defaults
        mutable_data = dict(data)

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
            schedule_postmortems(thesis)
            from apps.observer.triggers.services.thesis_guard import sync_thesis_guard

            sync_thesis_guard(thesis)

        return Response(ThesisSerializer(thesis).data, status=201)

    def perform_update(self, serializer):
        thesis = serializer.save()
        from apps.observer.triggers.services.thesis_guard import sync_thesis_guard

        sync_thesis_guard(thesis)

    def destroy(self, request: Request, *args: object, **kwargs: object) -> Response:
        """Archive the thesis (204). It leaves the list, the coach and the guard, and
        keeps its history.

        PostMortem cascades off Thesis, so dropping the row would take every
        completed post-mortem with it — and with them the conviction calibration,
        Brier score and cohort base rates the scorecard, Mirror and Coach compute
        from decisive post-mortems. It would also leave the review thread and the
        recall documents pointing at a thesis that no longer exists.

        ``?purge=true`` drops the row for real, and only while there is nothing to
        destroy: a thesis with a completed post-mortem answers 409 and must be
        archived instead.
        """
        thesis = self.get_object()
        if _flag(request.query_params.get("purge")):
            done = thesis.postmortems.filter(status="done").count()
            if done:
                return _error(
                    "postmortem_history",
                    f"This thesis has {done} completed post-mortem(s) feeding your "
                    "calibration. Archive it instead of deleting it.",
                    409,
                )
            return super().destroy(request, *args, **kwargs)

        if thesis.archived_at is None:
            from apps.observer.triggers.services.thesis_guard import sync_thesis_guard

            thesis.archived_at = timezone.now()
            # An archived thesis must stop costing money: the price guard fires a
            # capture + AI run on every cross.
            thesis.guard_enabled = False
            thesis.save(update_fields=["archived_at", "guard_enabled", "updated_at"])
            sync_thesis_guard(thesis)
        return Response(status=204)

    # request=None: the action reads no body, but get_serializer_class() would
    # otherwise hand the model serializer to both directions and force callers to
    # send a whole Thesis.
    @extend_schema(request=None, responses={200: ThesisSerializer})
    @action(detail=True, methods=["post"])
    def restore(self, request: Request, pk: str | None = None) -> Response:
        """Bring an archived thesis back to the list. The price guard stays off —
        re-arm it deliberately."""
        thesis = self.get_object()
        if thesis.archived_at is not None:
            thesis.archived_at = None
            thesis.save(update_fields=["archived_at", "updated_at"])
        return Response(ThesisSerializer(thesis).data, status=200)

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
        from apps.observer.triggers.services.thesis_guard import sync_thesis_guard

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
        thesis = self.get_object()
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
