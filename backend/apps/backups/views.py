from __future__ import annotations

from typing import ClassVar

from django.http import FileResponse, HttpResponse
from rest_framework import status, viewsets
from rest_framework.decorators import action
from rest_framework.pagination import PageNumberPagination
from rest_framework.response import Response

from apps.backups.models import BackupRecord
from apps.backups.serializers import BackupRecordSerializer
from apps.backups.services import backups_dir
from apps.backups.tasks import run_backup


class BackupPagination(PageNumberPagination):
    page_size = 50


class BackupViewSet(viewsets.ModelViewSet):
    queryset = BackupRecord.objects.all()
    serializer_class = BackupRecordSerializer
    pagination_class = BackupPagination
    http_method_names: ClassVar = ["get", "post", "delete"]  # type: ignore[misc]

    def create(self, request, *args, **kwargs):
        return Response(status=status.HTTP_405_METHOD_NOT_ALLOWED)

    @action(detail=False, methods=["post"], url_path="run")
    def run_now(self, request):
        run_backup.delay(kind="manual")
        return Response({"queued": True}, status=status.HTTP_202_ACCEPTED)

    @action(detail=True, methods=["get"], url_path="download")
    def download(self, request, pk=None):
        rec = self.get_object()
        path = backups_dir() / rec.filename
        if not path.exists():
            return HttpResponse(status=404)
        resp = FileResponse(path.open("rb"), as_attachment=True, filename=rec.filename)
        return resp

    def destroy(self, request, *args, **kwargs):
        rec = self.get_object()
        path = backups_dir() / rec.filename
        path.unlink(missing_ok=True)
        rec.status = "deleted"
        rec.save(update_fields=["status"])
        return Response(status=status.HTTP_204_NO_CONTENT)
