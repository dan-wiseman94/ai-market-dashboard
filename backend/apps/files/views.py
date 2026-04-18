from __future__ import annotations

from rest_framework import status, viewsets
from rest_framework.parsers import MultiPartParser
from rest_framework.request import Request
from rest_framework.response import Response

from apps.files.models import UserFile
from apps.files.serializers import UserFileSerializer
from apps.files.services import NoKeyError, delete_from_anthropic, upload_to_anthropic


class UserFileViewSet(viewsets.ModelViewSet):
    serializer_class = UserFileSerializer
    parser_classes = (MultiPartParser,)
    http_method_names = ("get", "post", "delete")

    def get_queryset(self):
        qs = UserFile.objects.all()
        kind = self.request.query_params.get("kind")
        ticker = self.request.query_params.get("ticker")
        if kind:
            qs = qs.filter(kind=kind)
        if ticker:
            qs = qs.filter(ticker=ticker.upper())
        return qs.order_by("-uploaded_at")

    def list(self, request: Request, *args, **kwargs) -> Response:
        qs = self.get_queryset()
        return Response({"results": UserFileSerializer(qs, many=True).data})

    def create(self, request: Request, *args, **kwargs) -> Response:
        upload = request.FILES.get("file")
        if upload is None:
            return Response({"code": "no_file"}, status=400)
        try:
            anthropic_id, size = upload_to_anthropic(
                upload.file, filename=upload.name,
                mime=upload.content_type or "application/octet-stream",
            )
        except NoKeyError:
            return Response({"code": "no_key", "message": "Claude key not configured"}, status=400)
        uf = UserFile.objects.create(
            anthropic_id=anthropic_id,
            kind=request.data.get("kind", "other"),
            ticker=(request.data.get("ticker") or "").upper(),
            mime=upload.content_type or "application/octet-stream",
            size=size,
            filename=upload.name[:200],
        )
        return Response(UserFileSerializer(uf).data, status=status.HTTP_201_CREATED)

    def destroy(self, request: Request, *args, **kwargs) -> Response:
        uf = self.get_object()
        try:
            delete_from_anthropic(uf.anthropic_id)
        except NoKeyError:
            pass
        uf.delete()
        return Response(status=204)
