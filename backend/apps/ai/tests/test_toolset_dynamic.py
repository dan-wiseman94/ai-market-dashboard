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


def test_registered_spec_wins_over_resolvers() -> None:
    ts = Toolset()
    ts.register(_spec("tv_x", "registered"))
    ts.add_resolver(lambda name: _spec(name, "dyn"))
    assert ts.run("tv_x", {}) == {"ok": True, "result": "registered"}


def test_merge_adds_specs_and_resolvers_and_serializes_them() -> None:
    a = Toolset()
    a.register(_spec("a", "a"))
    b = Toolset()
    b.register(_spec("b", "b"))
    b.add_resolver(lambda name: None)
    out = a.merge(b)
    assert out is a
    assert set(a.specs) == {"a", "b"}
    assert len(a.dynamic_resolvers) == 1
    assert [t["name"] for t in a.anthropic_tools()] == ["a", "b"]
    assert [t["function"]["name"] for t in a.openai_tools()] == ["a", "b"]


def test_resolver_exception_surfaces_as_tool_error() -> None:
    ts = Toolset()
    ts.add_resolver(lambda name: _spec(name, "x"))

    def boom(**kw):
        raise ValueError("bad input")

    ts.register(ToolSpec(name="boom", description="", input_schema={}, fn=boom))
    assert ts.run("boom", {}) == {"ok": False, "error": "ValueError: bad input"}
