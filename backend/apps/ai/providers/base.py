"""Provider Protocol — structural interface for Claude/OpenAI/Local."""

from __future__ import annotations

from collections.abc import AsyncIterator
from typing import Protocol, runtime_checkable

from apps.ai.types import RunEvent, RunRequest


@runtime_checkable
class Provider(Protocol):
    name: str

    def run(self, req: RunRequest) -> AsyncIterator[RunEvent]:
        """Yield RunEvents: text_delta* → usage → done | error."""
        ...
