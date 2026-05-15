from __future__ import annotations

import hashlib
import json
import logging
import os
import traceback
import uuid
import zipfile
from datetime import UTC, datetime
from pathlib import Path

from django.utils import timezone

from apps.export import serializers as S
from apps.export.models import ExportJob

log = logging.getLogger(__name__)


def exports_dir() -> Path:
    return Path(os.environ.get("EXPORTS_DIR", "/data/exports"))


def build_export_bundle(job_id: int) -> None:
    job = ExportJob.objects.get(pk=job_id)
    job.status = "running"
    job.save(update_fields=["status"])

    path: Path | None = None
    try:
        d = exports_dir()
        d.mkdir(parents=True, exist_ok=True)
        filename = f"ai-dashboard-export-{datetime.now(UTC).strftime('%Y%m%d-%H%M%S')}-{uuid.uuid4().hex[:6]}.zip"
        path = d / filename
        counts = {"threads": 0, "snapshots": 0, "observations": 0, "triggers": 0}

        scope = job.scope or {}

        with zipfile.ZipFile(path, "w", zipfile.ZIP_DEFLATED) as zf:
            root = path.stem

            if scope.get("threads"):
                from apps.threads.models import Thread

                qs = (
                    Thread.objects.all()
                    if scope["threads"] == "all"
                    else Thread.objects.filter(id__in=scope["threads"])
                )
                for t in qs:
                    zf.writestr(
                        f"{root}/threads/{t.id}/meta.json",
                        json.dumps(S.thread_to_json(t), default=str, indent=2),
                    )
                    zf.writestr(
                        f"{root}/threads/{t.id}/thread.md",
                        S.thread_to_markdown(t),
                    )
                    counts["threads"] += 1

            if scope.get("snapshots"):
                from apps.snapshots.models import Snapshot

                snapshot_qs = (
                    Snapshot.objects.all()
                    if scope["snapshots"] == "all"
                    else Snapshot.objects.filter(id__in=scope["snapshots"])
                )
                for s in snapshot_qs:
                    zf.writestr(
                        f"{root}/snapshots/{s.id}/meta.json",
                        json.dumps(S.snapshot_to_json(s), default=str, indent=2),
                    )
                    zf.writestr(
                        f"{root}/snapshots/{s.id}/summary.md",
                        S.snapshot_to_markdown(s),
                    )
                    for name, data in S.snapshot_images(s):
                        zf.writestr(f"{root}/snapshots/{s.id}/images/{name}", data)
                    counts["snapshots"] += 1

            if scope.get("observations"):
                from apps.observer.models import ObserverSchedule

                for sched in ObserverSchedule.objects.all():
                    zf.writestr(
                        f"{root}/observations/{sched.id}/runs.json",
                        json.dumps(S.observer_runs_to_json(sched), default=str, indent=2),
                    )
                    zf.writestr(
                        f"{root}/observations/{sched.id}/runs.md",
                        S.observer_runs_to_markdown(sched),
                    )
                    counts["observations"] += 1

            if scope.get("triggers"):
                from apps.triggers.models import EventTrigger

                for trig in EventTrigger.objects.all():
                    zf.writestr(
                        f"{root}/triggers/{trig.id}/config.json",
                        json.dumps(S.trigger_to_json(trig), default=str, indent=2),
                    )
                    counts["triggers"] += 1

            if scope.get("profiles"):
                zf.writestr(
                    f"{root}/profiles/profiles.json",
                    json.dumps(S.profiles_to_json(), default=str, indent=2),
                )
            if scope.get("watchlists"):
                zf.writestr(
                    f"{root}/watchlists/watchlists.json",
                    json.dumps(S.watchlists_to_json(), default=str, indent=2),
                )

            manifest = {
                "version": 1,
                "generated_at": timezone.now().isoformat(),
                "scope": scope,
                "counts": counts,
            }
            zf.writestr(f"{root}/manifest.json", json.dumps(manifest, indent=2))

        # sha256 streaming read — never buffer the whole zip in memory
        h = hashlib.sha256()
        with path.open("rb") as f:
            for chunk in iter(lambda: f.read(1024 * 1024), b""):
                h.update(chunk)

        job.status = "done"
        job.filename = filename
        job.size_bytes = path.stat().st_size
        job.sha256 = h.hexdigest()
        job.completed_at = timezone.now()
        job.save()
    except Exception:
        job.status = "failed"
        job.error = traceback.format_exc()[:4000]
        job.completed_at = timezone.now()
        job.save()
        # Don't leave a partial zip on disk; failed jobs have no filename.
        if path is not None:
            try:
                path.unlink(missing_ok=True)
            except OSError:
                log.warning("could not unlink failed export path %s", path)


def reconcile_export_disk() -> None:
    d = exports_dir()
    for job in ExportJob.objects.filter(status="done"):
        if not (d / job.filename).exists():
            job.status = "missing"
            job.save(update_fields=["status"])
