"""Per-profile memory directory helper for Claude's Memory tool.

Layout: `<AI_MEMORY_ROOT>/<profile_id>/` — intentionally flat; the Memory
tool itself manages files inside. We only guarantee isolation between
profiles and existence of the directory.
"""
from __future__ import annotations

import os
from pathlib import Path


def memory_dir_for_profile(*, profile_id: int) -> str:
    root = os.environ.get("AI_MEMORY_ROOT", "/data/memory")
    path = Path(root) / str(profile_id)
    path.mkdir(parents=True, exist_ok=True)
    return str(path)
