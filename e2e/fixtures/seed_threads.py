"""Rung 4 — threads with varied histories.

Five threads:
  1. Pinned-to-snapshot — synthetic first user message references the snapshot.
  2. Plain — empty/ready-to-send (chat).
  3. Compare — one parent user message + two assistant branches.
  4. Tool-use — single assistant message whose ``content.blocks`` contains a
     tool_use → tool_result → text triple.
  5. Empty consult — title only.

Idempotent.
"""

from __future__ import annotations

from django.db import transaction


def seed_threads() -> None:
    from e2e.fixtures.seed_snapshots import seed_snapshots

    seed_snapshots()

    from apps.profiles.models import TradingProfile
    from apps.snapshots.models import Snapshot
    from apps.snapshots.serializer import serialize_for_ai
    from apps.threads.models import Message, Thread

    profile = TradingProfile.objects.get(name="E2E Default")
    snap = Snapshot.objects.filter(status="ready").first()

    # 1. Pinned thread
    with transaction.atomic():
        pinned, _ = Thread.objects.get_or_create(
            title="E2E pinned thread",
            defaults={
                "profile": profile,
                "pinned_snapshot": snap,
                "kind": "consult",
            },
        )
        if not pinned.messages.exists() and snap is not None:
            Message.objects.create(
                thread=pinned,
                role="user",
                status="done",
                content={"text": serialize_for_ai(snap)},
                snapshot_ref=snap,
            )

    # 2. Plain thread
    Thread.objects.get_or_create(
        title="E2E plain thread",
        defaults={"profile": profile, "kind": "chat"},
    )

    # 3. Compare thread (2 branches)
    with transaction.atomic():
        compare, _ = Thread.objects.get_or_create(
            title="E2E compare thread",
            defaults={"profile": profile, "kind": "consult"},
        )
        if not compare.messages.filter(parent_message__isnull=False).exists():
            parent = Message.objects.create(
                thread=compare,
                role="user",
                status="done",
                content={"text": "compare these"},
            )
            for branch_n, provider in enumerate(("claude", "openai"), start=1):
                Message.objects.create(
                    thread=compare,
                    role="assistant",
                    status="done",
                    parent_message=parent,
                    content={"text": f"Branch {branch_n} from {provider}"},
                )

    # 4. Tool-use thread
    with transaction.atomic():
        tools, _ = Thread.objects.get_or_create(
            title="E2E tool-use thread",
            defaults={"profile": profile, "kind": "consult"},
        )
        if not tools.messages.exists():
            Message.objects.create(
                thread=tools, role="user", status="done", content={"text": "use a tool"}
            )
            Message.objects.create(
                thread=tools,
                role="assistant",
                status="done",
                content={
                    "blocks": [
                        {"type": "tool_use", "name": "quotes_now", "input": {"ticker": "AAPL"}},
                        {"type": "tool_result", "content": {"last": 175.0}},
                        {"type": "text", "text": "Result: 175"},
                    ]
                },
            )

    # 5. Empty ready-to-send
    Thread.objects.get_or_create(
        title="E2E empty thread",
        defaults={"profile": profile, "kind": "chat"},
    )
