from rest_framework import mixins, viewsets
from rest_framework.decorators import action
from rest_framework.response import Response

from apps.profiles.models import TradingProfile
from apps.snapshots.models import Snapshot
from apps.threads.models import Message, Thread
from apps.threads.serializers import MessageSerializer, ThreadSerializer
from apps.threads.tasks import run_ai_on_message


class ThreadViewSet(
    mixins.ListModelMixin, mixins.RetrieveModelMixin, mixins.CreateModelMixin,
    viewsets.GenericViewSet
):
    queryset = Thread.objects.select_related("profile").prefetch_related("messages__ai_run")
    serializer_class = ThreadSerializer

    def create(self, request, *args, **kwargs):
        data = request.data
        profile = None
        if pid := data.get("profile_id"):
            profile = TradingProfile.objects.filter(id=pid).first()
        snap = None
        if sid := data.get("pinned_snapshot_id"):
            snap = Snapshot.objects.filter(id=sid).first()
        t = Thread.objects.create(
            kind=data.get("kind", "consult"),
            title=data.get("title", ""),
            profile=profile,
            pinned_snapshot=snap,
        )
        return Response(ThreadSerializer(t).data, status=201)

    @action(detail=True, methods=["post"])
    def send(self, request, pk=None):
        thread = self.get_object()
        text = (request.data.get("text") or "").strip()
        if not text:
            return Response({"code": "empty", "message": "text is required"}, status=400)

        user_msg = Message.objects.create(
            thread=thread, role="user", content={"text": text}, status="done",
        )
        run_ai_on_message.delay(thread_id=thread.id, user_message_id=user_msg.id)
        return Response(MessageSerializer(user_msg).data, status=202)

    @action(detail=True, methods=["post"])
    def compare(self, request, pk=None):
        """Send ONE user message and fan out to N provider/model branches.

        Body: {text, branches: [{provider, model}, ...]}
        """
        thread = self.get_object()
        text = (request.data.get("text") or "").strip()
        branches = request.data.get("branches") or []
        if not text:
            return Response({"code": "empty", "message": "text is required"}, status=400)
        if not branches:
            return Response({"code": "no_branches", "message": "Provide at least one branch"}, status=400)

        user_msg = Message.objects.create(
            thread=thread, role="user", content={"text": text}, status="done",
        )
        branch_ids: list[dict] = []
        for b in branches:
            task = run_ai_on_message.delay(
                thread_id=thread.id,
                user_message_id=user_msg.id,
                override={"provider": b["provider"], "model": b["model"]},
                parent_message_id=user_msg.id,
            )
            branch_ids.append({"provider": b["provider"], "model": b["model"], "task_id": task.id})

        return Response(
            {"user_message_id": user_msg.id, "branches": branch_ids},
            status=202,
        )

    @action(detail=True, methods=["post"], url_path=r"stop/(?P<message_id>\d+)")
    def stop(self, request, pk=None, message_id=None):
        """Mark a streaming assistant message as cancelled. Task finishes but skips final write."""
        thread = self.get_object()
        try:
            msg = Message.objects.get(id=message_id, thread=thread, role="assistant")
        except Message.DoesNotExist:
            return Response({"code": "not_found", "message": "Message not found"}, status=404)
        if msg.status != "streaming":
            return Response({"code": "not_streaming", "message": "Message is not streaming"}, status=400)
        msg.status = "failed"
        msg.error = "cancelled"
        msg.save()
        from apps.threads.tasks import _broadcast
        _broadcast(thread.id, {"event": "error", "message_id": msg.id, "error": "cancelled"})
        return Response({"ok": True}, status=200)
