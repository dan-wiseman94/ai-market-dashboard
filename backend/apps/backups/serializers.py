from typing import ClassVar

from rest_framework import serializers

from apps.backups.models import BackupRecord


class BackupRecordSerializer(serializers.ModelSerializer):
    class Meta:
        model = BackupRecord
        fields: ClassVar = [
            "id",
            "created_at",
            "filename",
            "size_bytes",
            "sha256",
            "kind",
            "status",
            "error",
        ]
        read_only_fields: ClassVar = fields


class RestoreRequestSerializer(serializers.Serializer):
    """Body of ``POST /api/backups/{id}/restore/``.

    The confirmation is a deliberate-action guard, not a secret: it must equal the
    backup's own ``filename``, which the list endpoint already hands out.
    """

    confirm = serializers.CharField(
        help_text="The backup's exact filename. Anything else answers 400.",
    )


class RestoreResponseSerializer(serializers.Serializer):
    """A completed restore. ``workers_quiesced`` is always false — this endpoint
    cannot stop worker/beat (no Docker socket in the container), so ``warning``
    says to restart them."""

    restored = serializers.BooleanField()
    backup_id = serializers.IntegerField()
    filename = serializers.CharField()
    duration_ms = serializers.IntegerField()
    workers_quiesced = serializers.BooleanField()
    warning = serializers.CharField()


class RestoreErrorSerializer(serializers.Serializer):
    """The restore endpoint's refusal envelope. ``code`` is the machine-readable
    reason; the optional keys are present only for the codes that carry them."""

    code = serializers.CharField()
    detail = serializers.CharField()
    expected = serializers.CharField(
        required=False,
        help_text="confirmation_mismatch only: the filename the client had to type.",
    )
    exit_code = serializers.IntegerField(
        required=False,
        help_text="restore_failed only: pg_restore's exit status.",
    )
    stderr = serializers.CharField(
        required=False,
        help_text="restore_failed only: the last 4000 bytes of credential-scrubbed "
        "pg_restore stderr.",
    )


class QueuedSerializer(serializers.Serializer):
    """The 202 body of a fire-and-forget action: the work is queued, not done."""

    queued = serializers.BooleanField()
