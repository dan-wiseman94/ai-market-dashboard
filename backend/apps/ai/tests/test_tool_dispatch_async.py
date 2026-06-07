"""Tool dispatch must run its (sync, ORM-touching) work OFF the asyncio loop thread.

Root cause of the documented streaming flake (CLAUDE.md "Determinism + flakes"):
the providers run tools by calling the synchronous ``Toolset.run`` (which calls
ORM-touching tool fns like recall/track_record/get_quote) *directly inside*
``asyncio.run(drive())`` on the worker thread. Django guards DB ``connect()`` with
``@async_unsafe``: a warm connection sails through, but whenever the connection
must reconnect (a prior task/test closed it, a recycled worker) the reconnect
happens ON the loop thread and raises ``SynchronousOnlyOperation`` — the ~1/8,
connection-state-dependent flake.

These tests pin the structural distinction without touching the DB (so they can't
wipe data-migration seed rows): the sync path runs the tool ON the loop thread;
the fix (``sync_to_async(thread_sensitive=True)``, mirroring the partial-flush
write in ``apps.threads.tasks``) runs it OFF the loop thread, where no event loop
is running and an ORM reconnect is therefore safe.
"""

from __future__ import annotations

import asyncio
import threading

from asgiref.sync import sync_to_async

from apps.ai.tools import Toolset, ToolSpec

_SCHEMA = {"type": "object", "properties": {}}


def _thread_recording_toolset(sink: dict) -> Toolset:
    def _rec(**_kwargs):
        sink["tool_thread"] = threading.get_ident()
        return "ok"

    ts = Toolset()
    ts.register(ToolSpec(name="rec", description="record thread", input_schema=_SCHEMA, fn=_rec))
    return ts


def test_sync_run_executes_on_the_loop_thread():
    """Characterization: calling Toolset.run directly inside the loop runs the tool
    (and any ORM it does) ON the loop thread — where @async_unsafe fires on reconnect.
    """
    sink: dict = {}
    ts = _thread_recording_toolset(sink)
    loop: dict = {}

    async def drive():
        loop["thread"] = threading.get_ident()
        return ts.run("rec", {})

    outcome = asyncio.run(drive())
    assert outcome["ok"] is True
    assert sink["tool_thread"] == loop["thread"]  # the hazard: tool ran on the loop thread


def test_sync_to_async_offload_runs_off_the_loop_thread():
    """The fix the providers apply: sync_to_async(thread_sensitive=True) runs the tool
    on asgiref's executor thread — no running loop there, so an ORM reconnect is safe.
    """
    sink: dict = {}
    ts = _thread_recording_toolset(sink)
    loop: dict = {}

    async def drive():
        loop["thread"] = threading.get_ident()
        return await sync_to_async(ts.run, thread_sensitive=True)("rec", {})

    outcome = asyncio.run(drive())
    assert outcome["ok"] is True
    assert sink["tool_thread"] != loop["thread"]  # the fix: tool ran off the loop thread
