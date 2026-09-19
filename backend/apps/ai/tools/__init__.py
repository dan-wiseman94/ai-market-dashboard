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
    input_schema: dict  # JSON Schema object — passed verbatim to Anthropic and OpenAI
    fn: Callable[..., Any]


@dataclass
class Toolset:
    specs: dict[str, ToolSpec] = field(default_factory=dict)
    # Consulted by run() when a name has no registered spec. Lets a family of tools whose
    # schemas are only known on the sync request path (TradingView's tv_*) still be
    # executed from the providers' async loops, which build the toolset without I/O.
    dynamic_resolvers: list[Callable[[str], ToolSpec | None]] = field(default_factory=list)

    def register(self, spec: ToolSpec) -> None:
        self.specs[spec.name] = spec

    def add_resolver(self, resolver: Callable[[str], ToolSpec | None]) -> None:
        self.dynamic_resolvers.append(resolver)

    def merge(self, other: Toolset) -> Toolset:
        """Add ``other``'s specs and resolvers into this toolset (in place); returns self."""
        self.specs.update(other.specs)
        self.dynamic_resolvers.extend(other.dynamic_resolvers)
        return self

    def resolve(self, name: str) -> ToolSpec | None:
        spec = self.specs.get(name)
        if spec is not None:
            return spec
        for resolver in self.dynamic_resolvers:
            spec = resolver(name)
            if spec is not None:
                return spec
        return None

    def anthropic_tools(self) -> list[dict]:
        """Serialize specs to the shape Claude's tools= param expects."""
        return [
            {"name": s.name, "description": s.description, "input_schema": s.input_schema}
            for s in self.specs.values()
        ]

    def openai_tools(self) -> list[dict]:
        """Serialize specs to the shape OpenAI's tools= param expects."""
        return [
            {
                "type": "function",
                "function": {
                    "name": s.name,
                    "description": s.description,
                    "parameters": s.input_schema,
                },
            }
            for s in self.specs.values()
        ]

    def run(self, name: str, tool_input: dict) -> dict:
        """Execute the named tool. Returns {"ok": bool, "result"|"error": ...}."""
        spec = self.resolve(name)
        if spec is None:
            return {"ok": False, "error": f"Unknown tool: {name}"}
        try:
            result = spec.fn(**tool_input)
            return {"ok": True, "result": result}
        except Exception as exc:
            return {"ok": False, "error": f"{type(exc).__name__}: {exc}"}
