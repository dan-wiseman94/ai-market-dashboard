"""Capability gap detection — which enabled profile features a provider can't honor.

Claude is the only M10-aware provider. OpenAI/local support tool use only when
the ProviderConfig opts in (supports_tools); extended thinking and memory remain
Claude-only. This helper drives a warn-and-continue message so the gap is visible
rather than a silent no-op.
"""

from __future__ import annotations


def unsupported_features(provider_name: str, profile, *, supports_tools: bool) -> list[str]:
    """Return human-readable names of features enabled on `profile` that
    `provider_name` cannot honor. Empty list => fully compatible."""
    if provider_name == "claude" or profile is None:
        return []
    out: list[str] = []
    if getattr(profile, "enable_tools", False) and not supports_tools:
        out.append("tool use")
    if getattr(profile, "enable_thinking", False):
        out.append("extended thinking")
    if getattr(profile, "enable_memory", False):
        out.append("memory")
    return out
