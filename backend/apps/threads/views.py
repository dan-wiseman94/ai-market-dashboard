from django.db import transaction
from rest_framework import mixins, viewsets
from rest_framework.decorators import action
from rest_framework.request import Request
from rest_framework.response import Response

from apps.profiles.models import TradingProfile
from apps.snapshots.models import Snapshot
from apps.snapshots.serializer import serialize_for_ai
from apps.threads.models import Message, Thread
from apps.threads.serializers import MessageSerializer, ThreadSerializer
from apps.threads.stop import request_stop
from apps.threads.tasks import _broadcast, run_ai_on_message


def _e2e_scenario() -> str | None:
    """The active E2E mock scenario to forward to the worker, or None in prod.

    The scenario lives in a web-process ContextVar (set from X-E2E-Scenario by
    middleware); it must be passed explicitly into the Celery task because the
    worker runs in a separate process. No-op outside MOCK_EXTERNAL.
    """
    from apps.core.mocks import current_scenario, is_mock_mode

    return current_scenario() if is_mock_mode() else None


def _error(code: str, message: str, status: int) -> Response:
    return Response({"code": code, "message": message}, status=status)


def _user_text(request: Request) -> str:
    return (request.data.get("text") or "").strip()


def _create_user_message(thread: Thread, text: str) -> Message:
    return Message.objects.create(
        thread=thread,
        role="user",
        content={"text": text},
        status="done",
    )


class ThreadViewSet(
    mixins.ListModelMixin,
    mixins.RetrieveModelMixin,
    mixins.CreateModelMixin,
    viewsets.GenericViewSet,
):
    queryset = Thread.objects.select_related("profile").prefetch_related("messages__ai_run")
    serializer_class = ThreadSerializer

    def create(self, request: Request, *args: object, **kwargs: object) -> Response:
        data = request.data
        profile = None
        if pid := data.get("profile_id"):
            profile = TradingProfile.objects.filter(id=pid).first()
        snap = None
        if sid := data.get("pinned_snapshot_id"):
            snap = Snapshot.objects.filter(id=sid).first()
            if snap is not None and snap.status != "ready":
                return _error("snapshot_not_ready", "Snapshot is not ready", 400)
        synthetic_msg = None
        with transaction.atomic():
            t = Thread.objects.create(
                kind=data.get("kind", "consult"),
                title=data.get("title", ""),
                profile=profile,
                pinned_snapshot=snap,
            )
            if snap is not None:
                # Budget the payload for the model that will actually consume it
                # (the profile default), not the 40k fallback — serialization is
                # frozen into content["text"] here, so this is the only chance to
                # size it correctly. No profile → keep the conservative default.
                serialize_kwargs = (
                    {"provider": profile.default_provider, "model": profile.default_model}
                    if profile is not None
                    else {}
                )
                synthetic_msg = Message.objects.create(
                    thread=t,
                    role="user",
                    content={"text": serialize_for_ai(snap, **serialize_kwargs)},
                    snapshot_ref=snap,
                    status="done",
                )
        # "Capture + ask" opts in via auto_reply: stream an AI reply to the pinned
        # snapshot immediately rather than leaving the thread silent. Dispatched
        # on_commit so the worker sees the committed thread + synthetic message.
        # No override → profile default provider/model; cost caps + capability
        # warnings are enforced inside run_ai_on_message.
        if synthetic_msg is not None and data.get("auto_reply"):
            transaction.on_commit(
                lambda: run_ai_on_message.delay(
                    thread_id=t.id,
                    user_message_id=synthetic_msg.id,
                )
            )
        return Response(ThreadSerializer(t).data, status=201)

    @action(detail=True, methods=["post"])
    def send(self, request: Request, pk: str | None = None) -> Response:
        thread = self.get_object()
        text = _user_text(request)
        if not text:
            return _error("empty", "text is required", 400)

        user_msg = _create_user_message(thread, text)
        override_provider = (request.data.get("override_provider") or "").strip()
        override_model = (request.data.get("override_model") or "").strip()
        override = (
            {"provider": override_provider, "model": override_model}
            if override_provider and override_model
            else None
        )
        run_ai_on_message.delay(
            thread_id=thread.id,
            user_message_id=user_msg.id,
            override=override,
            scenario=_e2e_scenario(),
        )
        return Response(MessageSerializer(user_msg).data, status=202)

    @action(detail=True, methods=["post"])
    def compare(self, request: Request, pk: str | None = None) -> Response:
        """Send one user message and fan out to N provider/model branches in parallel."""
        thread = self.get_object()
        text = _user_text(request)
        branches = request.data.get("branches") or []
        if not text:
            return _error("empty", "text is required", 400)
        if not branches:
            return _error("no_branches", "Provide at least one branch", 400)

        for b in branches:
            if not (isinstance(b, dict) and b.get("provider") and b.get("model")):
                return _error("bad_branch", "Each branch needs a provider and model", 400)

        user_msg = _create_user_message(thread, text)
        branch_ids: list[dict] = []
        for b in branches:
            task = run_ai_on_message.delay(
                thread_id=thread.id,
                user_message_id=user_msg.id,
                override={"provider": b["provider"], "model": b["model"]},
                parent_message_id=user_msg.id,
                scenario=_e2e_scenario(),
            )
            branch_ids.append(
                {
                    "provider": b["provider"],
                    "model": b["model"],
                    "task_id": str(task.id),
                }
            )
        return Response(
            {"user_message_id": user_msg.id, "branches": branch_ids},
            status=202,
        )

    @action(detail=True, methods=["post"], url_path="attach-file")
    def attach_file(self, request: Request, pk: str | None = None) -> Response:
        """Attach a previously uploaded UserFile to the thread as a user Message.

        Body: {file_id: int, prompt?: str}. Creates a Message whose content is
        a `blocks` list: one document block referencing the Anthropic file_id
        + one text block carrying the prompt.
        """
        from apps.files.models import UserFile

        thread = self.get_object()
        file_id = request.data.get("file_id")
        prompt = (request.data.get("prompt") or "").strip() or "Please review this document."
        if file_id is None:
            return _error("not_found", "File not found", 404)
        try:
            uf = UserFile.objects.get(id=int(file_id))
        except (UserFile.DoesNotExist, ValueError, TypeError):
            return _error("not_found", "File not found", 404)
        msg = Message.objects.create(
            thread=thread,
            role="user",
            status="done",
            content={
                "blocks": [
                    {"type": "document", "source": {"type": "file", "file_id": uf.anthropic_id}},
                    {"type": "text", "text": prompt},
                ]
            },
        )
        return Response({"message_id": msg.id}, status=201)

    @action(detail=True, methods=["post"], url_path=r"stop/(?P<message_id>\d+)")
    def stop(self, request: Request, pk=None, message_id=None) -> Response:
        """Mark a streaming assistant message as cancelled; the running task will skip its final write."""
        thread = self.get_object()
        try:
            msg = Message.objects.get(id=message_id, thread=thread, role="assistant")
        except Message.DoesNotExist:
            return _error("not_found", "Message not found", 404)
        if msg.status != "streaming":
            # The run already reached a terminal state (natural finish, or a prior
            # stop). Stopping it is a benign no-op — a 400 here just turns a UI race
            # (or a stale "streaming" button left by a dropped WS) into console noise.
            return Response({"ok": True, "already_terminal": True}, status=200)
        # Signal the worker to abort the live stream, then record the cancellation.
        request_stop(msg.id)
        msg.status = "failed"
        msg.error = "cancelled"
        msg.save()
        _broadcast(thread.id, {"event": "error", "message_id": msg.id, "error": "cancelled"})
        return Response({"ok": True}, status=200)
