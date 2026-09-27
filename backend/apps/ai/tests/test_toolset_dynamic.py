"""Toolset: dynamic resolvers (tv_* dispatch without pre-registered specs) and merge."""

from __future__ import annotations

from apps.ai.tools import Toolset, ToolSpec


def _spec(name: str, value: str) -> ToolSpec:
    return ToolSpec(
        name=name, description=name, input_schema={"type": "object"}, fn=lambda **kw: value
    )


def test_run_consults_dynamic_resolvers_on_a_miss() -> None:
    ts = Toolset()
    ts.register(_spec("native", "n"))
    ts.add_resolver(lambda name: _spec(name, "dyn") if name.startswith("tv_") else None)
    assert ts.run("native", {}) == {"ok": True, "result": "n"}
    assert ts.run("tv_anything", {}) == {"ok": True, "result": "dyn"}
    assert ts.run("nope", {}) == {"ok": False, "error": "Unknown tool: nope"}


def test_resolver_raising_at_lookup_degrades_to_tool_error() -> None:
    ts = Toolset()
    ts.register(_spec("native", "n"))

    def raising_resolver(name: str) -> ToolSpec | None:
        raise KeyError("lookup table")

    ts.add_resolver(raising_resolver)
    assert ts.run("tv_anything", {}) == {"ok": False, "error": "KeyError: 'lookup table'"}
    assert ts.run("native", {}) == {"ok": True, "result": "n"}
