from __future__ import annotations

from unittest.mock import patch

import pytest

from apps.backups.services import perform_backup


@pytest.mark.django_db
def test_notify_on_success(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("BACKUPS_DIR", str(tmp_path))

    def fake_run(cmd, **kw):
        if hasattr(kw.get("stdout"), "name"):
            from pathlib import Path

            Path(kw["stdout"].name).write_bytes(b"x")

    with (
        patch("apps.backups.services.subprocess.run", side_effect=fake_run),
        patch("apps.backups.services.acquire_lock", return_value=True),
        patch("apps.backups.services.release_lock"),
        patch("apps.backups.services.notify") as n,
    ):
        perform_backup("manual")

    assert n.call_count == 1
    kwargs = n.call_args.kwargs
    assert kwargs["kind"] == "backup"


@pytest.mark.django_db
def test_notify_on_failure(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("BACKUPS_DIR", str(tmp_path))

    with (
        patch("apps.backups.services.subprocess.run", side_effect=RuntimeError("boom")),
        patch("apps.backups.services.acquire_lock", return_value=True),
        patch("apps.backups.services.release_lock"),
        patch("apps.backups.services.notify") as n,
    ):
        perform_backup("scheduled")

    assert n.call_count == 1
    assert n.call_args.kwargs["kind"] == "backup"
    assert (
        "error" in n.call_args.kwargs["title"].lower()
        or "failed" in n.call_args.kwargs["title"].lower()
    )
