"""Per-thread WS event log: monotonic seq + ?since replay buffer.

Exercises the real Redis the web/worker share (no mocking) — uses a random
thread id per run so it never collides with live data.
"""

from __future__ import annotations

import itertools
import uuid

from apps.threads.event_log import record, replay_since


def _tid() -> int:
    # uuid4 (os.urandom-based), NOT random.randint — pytest-randomly deterministically
    # reseeds the `random` module per test, which would make ids collide and let a prior
    # run's entries in the shared real Redis (1h TTL) contaminate the replay assertions.
    return uuid.uuid4().int % 9_000_000_000_000 + 1_000_000_000_000


def test_record_stamps_monotonic_seq_and_replays_tail():
    tid = _tid()
    e1 = record(tid, {"event": "message_started", "message_id": 1})
    e2 = record(tid, {"event": "text_delta", "text": "hi"})
    e3 = record(tid, {"event": "message_done", "message_id": 1})

    assert e1["seq"] < e2["seq"] < e3["seq"]

    # Reconnecting after e1 replays exactly the events that followed, in order.
    replayed = replay_since(tid, e1["seq"])
    assert [e["seq"] for e in replayed] == [e2["seq"], e3["seq"]]
    assert replayed[-1]["event"] == "message_done"

    # Caught up → nothing to replay.
    assert replay_since(tid, e3["seq"]) == []


def test_replayed_seqs_are_contiguous():
    tid = _tid()
    seqs = [record(tid, {"event": "text_delta", "text": str(i)})["seq"] for i in range(5)]
    replayed = replay_since(tid, seqs[0])
    got = [e["seq"] for e in replayed]
    assert got == seqs[1:]
    for a, b in itertools.pairwise(got):
        assert b == a + 1
