"""rotate_exports keeps the most-recent N completed exports and unlinks the rest,
bounding unbounded growth of /data/exports."""

from __future__ import annotations

import pytest
from django.utils import timezone

from apps.export.models import ExportJob
from apps.export.services import rotate_exports


@pytest.mark.django_db
def test_rotate_exports_keeps_recent_unlinks_old(tmp_path, monkeypatch):
    monkeypatch.setenv("EXPORTS_DIR", str(tmp_path))
    for i in range(5):
        fname = f"exp-{i}.zip"
        (tmp_path / fname).write_bytes(b"zip-bytes")
        ExportJob.objects.create(
            scope={}, format="zip", status="done", filename=fname, completed_at=timezone.now()
        )

    removed = rotate_exports(keep=2)

    assert removed == 3
    assert ExportJob.objects.filter(status="done").count() == 2
    # only the 2 most-recent files remain on disk
    assert sum(1 for _ in tmp_path.iterdir()) == 2


@pytest.mark.django_db
def test_rotate_exports_noop_under_keep(tmp_path, monkeypatch):
    monkeypatch.setenv("EXPORTS_DIR", str(tmp_path))
    (tmp_path / "only.zip").write_bytes(b"z")
    ExportJob.objects.create(
        scope={}, format="zip", status="done", filename="only.zip", completed_at=timezone.now()
    )
    assert rotate_exports(keep=20) == 0
    assert ExportJob.objects.filter(status="done").count() == 1
