"""Capability gap detection — which enabled profile features a provider can't honor.

Two kinds of gap land here. Claude is the only provider that honors every profile
feature: OpenAI/local support tool use only when the ProviderConfig opts in
(supports_tools), while extended thinking, memory, Files-API attachments and news
citations remain Claude-only. Separately, vision is a per-endpoint declaration
(``ProviderConfig.supports_vision``) rather than a Claude-only feature, so a
provider whose endpoint has no vision head loses a capture's chart images whoever
it is. This helper drives a warn-and-continue message so every drop is visible
rather than a silent no-op.
"""

from __future__ import annotations

from collections.abc import Sequence


def unsupported_features(
    provider_name: str,
    profile,
    *,
    supports_tools: bool,
    supports_vision: bool = True,
    carries_images: bool = False,
    content_kinds: Sequence[str] = (),
) -> list[str]:
    """Return human-readable names of features that `provider_name` cannot honor.

    `profile` supplies the enabled feature flags. `content_kinds` names Claude-only
    content already attached to this turn — a Files-API document block or citable
    news `search_result` blocks, both of which the request builder strips for other
    providers. `carries_images` says this run would have attached a snapshot's chart
    images, which the request builder strips when `supports_vision` is off. Empty
    list => fully compatible.
    """
    out: list[str] = []
    # Checked ahead of the Claude short-circuit: supports_vision is declared per
    # ProviderConfig row, so turning it off for ANY provider must report the drop.
    if carries_images and not supports_vision:
        out.append("chart images")
    if provider_name == "claude":
        return out
    out.extend(content_kinds)
    if profile is None:
        return out
    if getattr(profile, "enable_tools", False) and not supports_tools:
        out.append("tool use")
    if getattr(profile, "enable_thinking", False):
        out.append("extended thinking")
    if getattr(profile, "enable_memory", False):
        out.append("memory")
    return out
