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
