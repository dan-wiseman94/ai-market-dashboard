from __future__ import annotations

import logging
import subprocess
import time
from typing import ClassVar

from django.http import FileResponse, HttpResponse
from drf_spectacular.types import OpenApiTypes
from drf_spectacular.utils import extend_schema
from rest_framework import status, viewsets
from rest_framework.decorators import action
from rest_framework.pagination import PageNumberPagination
from rest_framework.response import Response

from apps.backups.models import BackupRecord
from apps.backups.serializers import (
    BackupRecordSerializer,
    QueuedSerializer,
    RestoreErrorSerializer,
    RestoreRequestSerializer,
    RestoreResponseSerializer,
)
from apps.backups.services import (
    RestoreFailed,
    acquire_lock,
    backups_dir,
    perform_restore,
    release_lock,
)
from apps.backups.tasks import run_backup
from apps.core.runtime_config import runtime_config

logger = logging.getLogger(__name__)

# The CLI (`make restore`) stops beat + worker around the restore so nothing writes to a
# database whose tables are being dropped and recreated. No compose file mounts
# /var/run/docker.sock into any service, so a container has no way to reach the Docker
# daemon and this endpoint CANNOT reproduce that step: worker and beat keep running
# through the restore. They survive it (their queries are short and the restore does not
# wait on them), but they hold connections planned against the pre-restore catalog and
# their in-memory beat schedule is now stale, so they must be restarted afterwards. The
# response says so in `warning`; `workers_quiesced` is always False for the same reason.
RESTORE_WORKER_WARNING = (
    "worker and beat kept running through the restore — this endpoint cannot stop them. "
    "Restart them (`make reload-workers`) before trusting scheduled work."
)


class BackupPagination(PageNumberPagination):
    page_size = 50
    page_size_query_param = "page_size"


class BackupViewSet(viewsets.ModelViewSet):
    queryset = BackupRecord.objects.all()
    serializer_class = BackupRecordSerializer
    pagination_class = BackupPagination
    http_method_names: ClassVar = ["get", "post", "delete"]  # type: ignore[misc]

    def create(self, request, *args, **kwargs):
        return Response(status=status.HTTP_405_METHOD_NOT_ALLOWED)

    # Same fabrication as restore(): without this, get_serializer_class() declares a
    # BackupRecord body on an action that reads none, and a BackupRecord 200 on a 202.
    @extend_schema(request=None, responses={202: QueuedSerializer})
    @action(detail=False, methods=["post"], url_path="run")
    def run_now(self, request):
        run_backup.delay(kind="manual")
        return Response({"queued": True}, status=status.HTTP_202_ACCEPTED)

    # A binary FileResponse, not a BackupRecord. OpenApiTypes.BINARY is the honest
    # declaration; the default would promise JSON the endpoint never returns.
    @extend_schema(
        responses={
            (200, "application/octet-stream"): OpenApiTypes.BINARY,
            404: None,
        }
    )
    @action(detail=True, methods=["get"], url_path="download")
    def download(self, request, pk=None):
        rec = self.get_object()
        path = backups_dir() / rec.filename
        if not path.exists():
            return HttpResponse(status=404)
        resp = FileResponse(path.open("rb"), as_attachment=True, filename=rec.filename)
        return resp

    # Synchronous, not queued. A whole-database restore measures ~5s over a populated
    # database (~3s into an empty one) — far inside any HTTP timeout — and the request's
    # own connection survives it: ATOMIC_REQUESTS is off, so the request runs in
    # autocommit and holds no table locks for `--clean` to wait on, and CONN_MAX_AGE is 0,
    # so Django opens a fresh connection per request and cannot carry a stale one past the
    # swap. Queueing it to Celery would be worse, not safer: the worker would be replacing
    # the very database it reports progress into, so any status row written before the
    # restore is destroyed by the restore itself and the UI could never poll a trustworthy
    # result — and `make restore` deliberately STOPS the worker, so handing it the restore
    # inverts the CLI's own precaution.
    #
    # The confirmation string is a deliberate-action guard, not a secret: the list endpoint
    # hands out the filename. It exists because the API is unauthenticated by design
    # (network isolation, 127.0.0.1-bound), so a stray POST must not be enough.
    # Without this the ViewSet's serializer_class leaks into the contract and the
    # action documents itself as taking and returning a BackupRecord, which it does
    # neither of. Every status the body below can produce is listed.
    @extend_schema(
        request=RestoreRequestSerializer,
        responses={
            200: RestoreResponseSerializer,
            400: RestoreErrorSerializer,
            403: RestoreErrorSerializer,
            409: RestoreErrorSerializer,
            500: RestoreErrorSerializer,
            504: RestoreErrorSerializer,
        },
    )
    @action(detail=True, methods=["post"], url_path="restore")
    def restore(self, request, pk=None):
        """Restore the database from this backup, replacing its entire contents.

        Requires `{"confirm": "<exact backup filename>"}` in the body.
        """
        if not runtime_config().restore_from_ui_enabled:
            return Response(
                {
                    "code": "restore_disabled",
                    "detail": (
                        "Restore from the UI is switched off. Turn on 'Restore from UI' "
                        "in Settings → Features to enable it."
                    ),
                },
                status=status.HTTP_403_FORBIDDEN,
            )

        rec = self.get_object()
        data = request.data if isinstance(request.data, dict) else {}
        if data.get("confirm") != rec.filename:
            return Response(
                {
                    "code": "confirmation_mismatch",
                    "detail": "Type the backup filename exactly to confirm the restore.",
                    "expected": rec.filename,
                },
                status=status.HTTP_400_BAD_REQUEST,
            )
        if rec.status != "ok":
            return Response(
                {
                    "code": "backup_not_restorable",
                    "detail": f"Backup status is '{rec.status}'; only an 'ok' backup restores.",
                },
                status=status.HTTP_409_CONFLICT,
            )

        # Same Redis lock the backup writer takes: a pg_dump running against a database
        # mid-restore would capture a half-dropped schema, and two concurrent restores
        # would fight over every table.
        if not acquire_lock():
            return Response(
                {
                    "code": "backup_in_progress",
                    "detail": "A backup or restore is already running; try again shortly.",
                },
                status=status.HTTP_409_CONFLICT,
            )

        # Capture everything the response needs BEFORE pg_restore runs: --clean drops and
        # recreates every table, so this BackupRecord row is replaced by whatever the
        # archive holds and may not exist afterwards. Nothing below touches the ORM.
        filename, backup_id = rec.filename, rec.id
        started = time.monotonic()
        try:
            perform_restore(filename)
        except FileNotFoundError:
            return Response(
                {
                    "code": "backup_file_missing",
                    "detail": "The backup file could not be found on the server.",
                },
                status=status.HTTP_409_CONFLICT,
            )
        except RestoreFailed as exc:
            # The body withholds stderr on purpose; log it so the pointer to the
            # server logs is true. RestoreFailed.stderr is already scrubbed of
            # credentials, which is what makes it safe to write down at all.
            logger.error(
                "backups.restore_failed: backup=%s exit=%s stderr=%s",
                backup_id,
                exc.returncode,
                exc.stderr,
            )
            return Response(
                {
                    "code": "restore_failed",
                    "detail": (
                        "Restore failed due to a server-side error. Check server logs for details."
                    ),
                    "exit_code": exc.returncode,
                },
                status=status.HTTP_500_INTERNAL_SERVER_ERROR,
            )
        except subprocess.TimeoutExpired:
            return Response(
                {
                    "code": "restore_timeout",
                    "detail": "pg_restore exceeded its 1800s limit; the database may be "
                    "partially restored. Check the server before using it.",
                },
                status=status.HTTP_504_GATEWAY_TIMEOUT,
            )
        finally:
            release_lock()
        # No connections.close_all() here: nothing below touches the ORM, and CONN_MAX_AGE
        # is 0 so the next request opens a fresh connection against the restored catalog.
        # (Closing mid-request would also poison the surrounding atomic block under test.)

        return Response(
            {
                "restored": True,
                "backup_id": backup_id,
                "filename": filename,
                "duration_ms": int((time.monotonic() - started) * 1000),
                "workers_quiesced": False,
                "warning": RESTORE_WORKER_WARNING,
            },
            status=status.HTTP_200_OK,
        )

    def destroy(self, request, *args, **kwargs):
        rec = self.get_object()
        path = backups_dir() / rec.filename
        path.unlink(missing_ok=True)
        rec.status = "deleted"
        rec.save(update_fields=["status"])
        return Response(status=status.HTTP_204_NO_CONTENT)
