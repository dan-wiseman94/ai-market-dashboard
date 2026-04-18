from __future__ import annotations

from pathlib import Path

from django.http import FileResponse, HttpResponse
from rest_framework import status, viewsets
from rest_framework.decorators import action, api_view
from rest_framework.pagination import PageNumberPagination
from rest_framework.response import Response

from apps.export.models import ExportJob
from apps.export.serializers import ExportJobSerializer
from apps.export.services import exports_dir
from apps.export.tasks import build_export


class _ExportPagination(PageNumberPagination):
    page_size = 50
    page_size_query_param = "page_size"


class ExportViewSet(viewsets.ModelViewSet):
    queryset = ExportJob.objects.all()
    serializer_class = ExportJobSerializer
    http_method_names = ["get", "post", "delete"]
    pagination_class = _ExportPagination

    def create(self, request, *args, **kwargs):
        scope = request.data.get("scope") or {}
        job = ExportJob.objects.create(scope=scope, format="zip", status="pending")
        build_export.delay(job.id)
        return Response(
            self.serializer_class(job).data,
            status=status.HTTP_202_ACCEPTED,
        )

    @action(detail=True, methods=["get"], url_path="download")
    def download(self, request, pk=None):
        job: ExportJob = self.get_object()
        if job.status != "done":
            return Response(
                {"error": f"export not ready (status={job.status})"},
                status=status.HTTP_409_CONFLICT,
            )
        path = exports_dir() / job.filename
        if not path.exists():
            return HttpResponse(status=404)
        return FileResponse(path.open("rb"), as_attachment=True, filename=job.filename)

    def destroy(self, request, *args, **kwargs):
        job: ExportJob = self.get_object()
        (exports_dir() / job.filename).unlink(missing_ok=True)
        job.status = "deleted"
        job.save(update_fields=["status"])
        return Response(status=status.HTTP_204_NO_CONTENT)


@api_view(["POST"])
def export_single_thread(request, thread_id: int):
    job = ExportJob.objects.create(
        scope={"threads": [thread_id]}, format="zip", status="pending",
    )
    build_export.delay(job.id)
    return Response(
        ExportJobSerializer(job).data,
        status=status.HTTP_202_ACCEPTED,
    )
