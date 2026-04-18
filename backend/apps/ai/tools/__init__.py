"""ToolSpec + Toolset — the shape tools present to the AI provider layer.

`ToolSpec` is the declarative metadata (Anthropic passes this to the model).
`Toolset` is a bag of specs keyed by name, with a resolver that runs them.
"""
from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any


@dataclass(frozen=True)
class ToolSpec:
    name: str
    description: str
    input_schema: dict  # JSON schema, passed verbatim to Anthropic
    fn: Callable[..., Any]


@dataclass
class Toolset:
    specs: dict[str, ToolSpec] = field(default_factory=dict)

    def register(self, spec: ToolSpec) -> None:
        self.specs[spec.name] = spec

    def anthropic_tools(self) -> list[dict]:
        """Serialize specs to the shape Claude's tools= param expects."""
        return [
            {"name": s.name, "description": s.description, "input_schema": s.input_schema}
            for s in self.specs.values()
        ]

    def run(self, name: str, tool_input: dict) -> dict:
        """Execute the named tool. Returns {"ok": bool, "result"|"error": ...}."""
        spec = self.specs.get(name)
        if spec is None:
            return {"ok": False, "error": f"Unknown tool: {name}"}
        try:
            result = spec.fn(**tool_input)
            return {"ok": True, "result": result}
        except Exception as exc:
            return {"ok": False, "error": f"{type(exc).__name__}: {exc}"}
