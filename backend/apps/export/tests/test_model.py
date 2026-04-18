from __future__ import annotations

import pytest

from apps.export.models import ExportJob


@pytest.mark.django_db
def test_exportjob_defaults() -> None:
    j = ExportJob.objects.create(
        scope={"threads": "all"},
        format="zip",
        status="pending",
    )
    assert j.created_at is not None
    assert j.completed_at is None
    assert j.filename == ""
    assert j.size_bytes is None
    assert j.sha256 == ""
    assert j.error == ""
