"""ViewSet for the Thesis app."""

from __future__ import annotations

from django.db import transaction
from django.utils import timezone
from rest_framework import viewsets
from rest_framework.decorators import action
from rest_framework.request import Request
from rest_framework.response import Response

from apps.profiles.models import TradingProfile
from apps.snapshots.models import Snapshot, SnapshotSection
from apps.threads.models import Thread

from .models import Thesis
from .serializers import ThesisSerializer

# Statuses that mean the thesis is no longer "open" — derived from the model to
# avoid divergence when a new status is added later.
_CLOSED_STATUSES = {s for s, _ in Thesis.STATUS_CHOICES if s != "open"}


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
    queryset = Thesis.objects.select_related(
        "profile", "thread", "snapshot", "review_thread"
    ).order_by("-opened_at")
    serializer_class = ThesisSerializer

    def create(self, request: Request, *args: object, **kwargs: object) -> Response:
        data = request.data

        # Resolve optional FKs from the submitted ids
        profile: TradingProfile | None = None
        if pid := data.get("profile_id"):
            profile = TradingProfile.objects.filter(id=pid).first()

        thread: Thread | None = None
        if tid := data.get("thread_id"):
            thread = Thread.objects.filter(id=tid).first()

        snapshot: Snapshot | None = None
        if sid := data.get("snapshot_id"):
            snapshot = Snapshot.objects.filter(id=sid).first()

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
            # Phase 2: schedule_postmortems(thesis)

        return Response(ThesisSerializer(thesis).data, status=201)

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
        return Response(ThesisSerializer(thesis).data, status=200)

    @action(detail=True, methods=["post"], url_path="run-postmortem")
    def run_postmortem(self, request: Request, pk: str | None = None) -> Response:
        """Stub — Phase 2 will dispatch the real post-mortem AI run."""
        self.get_object()  # raises 404 for unknown pk
        # Phase 2: dispatch real post-mortem run
        return Response({"detail": "scheduled"}, status=202)
