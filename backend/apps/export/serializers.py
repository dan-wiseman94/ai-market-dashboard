"""Serializers for export: pure-function helpers and DRF serializer."""

from __future__ import annotations

from collections.abc import Iterator
from typing import ClassVar

from rest_framework import serializers as drf

from apps.export.models import ExportJob

# ---------------------------------------------------------------------------
# Thread serializers
# ---------------------------------------------------------------------------


def thread_to_json(thread) -> dict:
    from apps.threads.models import Message

    msgs = Message.objects.filter(thread=thread).order_by("created_at")
    return {
        "id": thread.id,
        "kind": thread.kind,
        "title": thread.title,
        "pinned_snapshot_id": thread.pinned_snapshot_id,
        "created_at": thread.created_at.isoformat(),
        "messages": [
            {
                "id": m.id,
                "role": m.role,
                "content": m.content,
                "status": m.status,
                "error": m.error,
                "parent_message_id": m.parent_message_id,
                "created_at": m.created_at.isoformat(),
                "ai_run": _ai_run(m),
            }
            for m in msgs
        ],
    }


def _ai_run(m) -> dict | None:
    try:
        r = m.ai_run
    except Exception:
        return None
    if r is None:
        return None
    return {
        "provider": r.provider,
        "model": r.model,
        "input_tokens": r.input_tokens,
        "output_tokens": r.output_tokens,
        "cached_tokens": r.cached_tokens,
        "cost_usd": str(r.cost_usd),
        "latency_ms": r.latency_ms,
        "status": r.status,
    }


def thread_to_markdown(thread) -> str:
    from apps.threads.models import Message

    lines = [
        f"# {thread.title}",
        "",
        f"_Kind: {thread.kind} · created: {thread.created_at.isoformat()}_",
        "",
    ]
    for m in Message.objects.filter(thread=thread).order_by("created_at"):
        lines.append(f"## {m.role.title()} — {m.created_at.isoformat()}")
        lines.append("")
        text = (m.content or {}).get("text", "") if isinstance(m.content, dict) else str(m.content)
        lines.append(text)
        lines.append("")
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Snapshot serializers
# ---------------------------------------------------------------------------


def snapshot_to_json(snapshot) -> dict:
    from apps.snapshots.models import SnapshotSection

    sections = SnapshotSection.objects.filter(snapshot=snapshot).order_by("kind")
    return {
        "id": snapshot.id,
        "captured_at": snapshot.captured_at.isoformat()
        if getattr(snapshot, "captured_at", None)
        else None,
        "sections": [
            {
                "kind": s.kind,
                "status": s.status,
                "payload": s.payload,
                "payload_tokens": s.payload_tokens,
                "error": s.error,
            }
            for s in sections
        ],
    }


def snapshot_to_markdown(snapshot) -> str:
    from apps.snapshots.models import SnapshotSection

    lines = [f"# Snapshot {snapshot.id}", ""]
    for s in SnapshotSection.objects.filter(snapshot=snapshot).order_by("kind"):
        lines.append(f"## {s.kind}")
        lines.append("")
        lines.append(f"- status: {s.status}")
        if s.error:
            lines.append(f"- error: {s.error}")
        lines.append("")
    return "\n".join(lines)


def snapshot_images(snapshot) -> Iterator[tuple[str, bytes]]:
    """Yield (filename, bytes) for each SnapshotImage on the snapshot."""
    from apps.snapshots.models import SnapshotImage

    for img in SnapshotImage.objects.filter(snapshot=snapshot):
        ext = "png"  # images are always PNG in our pipeline
        name = f"{img.kind}-{img.id}.{ext}"
        yield name, bytes(img.data)


# ---------------------------------------------------------------------------
# Observer serializers
# ---------------------------------------------------------------------------


def observer_runs_to_json(schedule) -> dict:
    """Serialize an ObserverSchedule and its linked observer threads as 'runs'."""
    from apps.threads.models import Thread

    threads = Thread.objects.filter(schedule=schedule).order_by("created_at")
    return {
        "schedule_id": schedule.id,
        "schedule_name": getattr(schedule, "name", ""),
        "profile_id": getattr(schedule, "profile_id", None),
        "enabled": getattr(schedule, "enabled", False),
        "runs": [
            {
                "id": t.id,
                "title": t.title,
                "created_at": t.created_at.isoformat(),
            }
            for t in threads
        ],
    }


def observer_runs_to_markdown(schedule) -> str:
    d = observer_runs_to_json(schedule)
    lines = [
        f"# Observer schedule {d['schedule_id']} — {d['schedule_name']}",
        f"- profile_id: {d['profile_id']}",
        f"- enabled: {d['enabled']}",
        "",
    ]
    for r in d["runs"]:
        lines.append(f"## Run {r['id']} — {r['created_at']}")
        lines.append(f"  {r['title']}")
        lines.append("")
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Trigger serializer
# ---------------------------------------------------------------------------


def trigger_to_json(trigger) -> dict:
    from apps.triggers.models import TriggerFiring

    firings = []
    for f in TriggerFiring.objects.filter(trigger=trigger).order_by("fired_at"):
        firings.append(
            {
                "id": f.id,
                "fired_at": f.fired_at.isoformat(),
                "matched_values": f.matched_values,
                "snapshot_id": f.snapshot_id,
                "thread_id": f.thread_id,
                "cost_capped": f.cost_capped,
            }
        )
    return {
        "id": trigger.id,
        "name": trigger.name,
        "profile_id": getattr(trigger, "profile_id", None),
        "enabled": trigger.enabled,
        "condition": trigger.condition,
        "firings": firings,
    }


# ---------------------------------------------------------------------------
# Profiles serializer
# ---------------------------------------------------------------------------


def profiles_to_json() -> dict:
    from apps.profiles.models import TradingProfile

    return {
        "profiles": [
            {
                "id": p.id,
                "name": p.name,
                "default_provider": getattr(p, "default_provider", ""),
                "default_model": getattr(p, "default_model", ""),
                "active": p.active,
                "created_at": p.created_at.isoformat() if getattr(p, "created_at", None) else None,
            }
            for p in TradingProfile.objects.all()
        ]
    }


# ---------------------------------------------------------------------------
# Watchlists serializer
# ---------------------------------------------------------------------------


def watchlists_to_json() -> dict:
    from apps.profiles.models import Watchlist, WatchlistSymbol

    out = []
    for w in Watchlist.objects.all():
        out.append(
            {
                "id": w.id,
                "name": w.name,
                "tickers": list(
                    WatchlistSymbol.objects.filter(watchlist=w)
                    .order_by("sort_order")
                    .values_list("ticker", flat=True)
                ),
            }
        )
    return {"watchlists": out}


# ---------------------------------------------------------------------------
# DRF serializer
# ---------------------------------------------------------------------------


class ExportJobSerializer(drf.ModelSerializer):
    class Meta:
        model = ExportJob
        fields: ClassVar = [
            "id",
            "created_at",
            "completed_at",
            "scope",
            "format",
            "status",
            "filename",
            "size_bytes",
            "sha256",
            "error",
        ]
        read_only_fields: ClassVar = [
            "id",
            "created_at",
            "completed_at",
            "status",
            "filename",
            "size_bytes",
            "sha256",
            "error",
            "format",
        ]
