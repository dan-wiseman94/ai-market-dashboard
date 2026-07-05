"""Persist tool_use/tool_result stream events as ToolCall audit rows.

Re-exported as ``apps.threads.tasks._persist_tool_calls``.
"""

from __future__ import annotations

from apps.threads.models import Message, ToolCall


def _tool_output_for_jsonfield(result: object) -> dict | list:
    """JSONField requires dict/list; wrap scalars and None as ``{"value": ...}``."""
    if result is None:
        return {}
    if isinstance(result, dict | list):
        return result
    return {"value": result}


def _persist_tool_calls(assistant: Message, events: list[dict]) -> None:
    """Pair tool_call with tool_result events by tool_use_id; create ToolCall rows."""
    calls: dict[str, dict] = {}
    for evt in events:
        tuid = evt["tool_use_id"]
        bucket = calls.setdefault(tuid, {})
        if evt["kind"] == "call":
            bucket["name"] = evt["name"]
            bucket["input"] = evt["input"]
        else:
            bucket["ok"] = evt.get("ok", True)
            bucket["result"] = evt.get("result")
            bucket["error"] = evt.get("error", "")
            bucket["latency_ms"] = evt.get("latency_ms", 0)

    to_create = [
        ToolCall(
            message=assistant,
            tool_use_id=tuid,
            tool_name=v.get("name", ""),
            tool_input=v.get("input") or {},
            tool_output=_tool_output_for_jsonfield(v.get("result")),
            ok=v.get("ok", True),
            error=v.get("error", ""),
            latency_ms=v.get("latency_ms", 0),
        )
        for tuid, v in calls.items()
    ]
    if to_create:
        ToolCall.objects.bulk_create(to_create)
