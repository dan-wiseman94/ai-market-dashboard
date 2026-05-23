"""Per-profile memory for Claude's Memory tool (memory_20250818).

Layout: `<AI_MEMORY_ROOT>/<profile_id>/`. `memory_dir_for_profile` guarantees
isolation between profiles and that the directory exists. `MemoryToolHandler`
executes the model's memory commands against that directory — the client side of
the tool, which Anthropic does NOT run for you.
"""

from __future__ import annotations

import os
import shutil
from pathlib import Path
from typing import Any


def memory_dir_for_profile(*, profile_id: int) -> str:
    root = os.environ.get("AI_MEMORY_ROOT", "/data/memory")
    path = Path(root) / str(profile_id)
    path.mkdir(parents=True, exist_ok=True)
    return str(path)


class MemoryPathError(Exception):
    """A memory command referenced a path outside the sandboxed root."""


class MemoryToolHandler:
    """Execute memory_20250818 commands against a sandboxed directory.

    The model addresses files under a virtual `/memories` root; we map that to
    `root` on disk. Every path is confined to `root` — traversal (``..``) that
    would escape the directory is rejected, so one profile's memory can never
    read or write another's (or anything else on the host).

    `run(command_input)` returns `{"ok": True, "result": <str>}` or
    `{"ok": False, "error": <str>}`, matching the Toolset.run contract so the
    provider can stream a tool_result either way.
    """

    def __init__(self, root: str) -> None:
        self._root = Path(root).resolve()
        self._root.mkdir(parents=True, exist_ok=True)

    def run(self, command_input: dict) -> dict[str, Any]:
        cmd = str(command_input.get("command") or "")
        handlers = {
            "view": self._view,
            "create": self._create,
            "str_replace": self._str_replace,
            "insert": self._insert,
            "delete": self._delete,
            "rename": self._rename,
        }
        fn = handlers.get(cmd)
        if fn is None:
            return {"ok": False, "error": f"Unknown memory command: {cmd!r}"}
        try:
            return {"ok": True, "result": fn(command_input)}
        except (MemoryPathError, FileNotFoundError, ValueError) as exc:
            return {"ok": False, "error": str(exc)}
        except Exception as exc:  # pragma: no cover - defensive
            return {"ok": False, "error": f"{type(exc).__name__}: {exc}"}

    def _resolve(self, raw_path: str) -> Path:
        p = (raw_path or "").strip()
        if p.startswith("/memories"):
            p = p[len("/memories") :]
        p = p.lstrip("/")
        candidate = (self._root / p).resolve()
        if candidate != self._root and self._root not in candidate.parents:
            raise MemoryPathError(f"path escapes memory root: {raw_path!r}")
        return candidate

    def _view(self, ci: dict) -> str:
        target = self._resolve(ci.get("path", ""))
        if target.is_dir():
            entries = sorted(
                f"{c.name}/" if c.is_dir() else c.name for c in target.iterdir()
            )
            return "\n".join(entries) if entries else "(empty)"
        if not target.exists():
            raise FileNotFoundError(f"no such file: {ci.get('path')!r}")
        lines = target.read_text(encoding="utf-8").splitlines()
        rng = ci.get("view_range")
        if isinstance(rng, list) and len(rng) == 2:
            start, end = int(rng[0]), int(rng[1])
            lines = lines[max(start - 1, 0) : end]
        return "\n".join(lines)

    def _create(self, ci: dict) -> str:
        target = self._resolve(ci.get("path", ""))
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(ci.get("file_text", ""), encoding="utf-8")
        return f"Created {ci.get('path')}"

    def _str_replace(self, ci: dict) -> str:
        target = self._resolve(ci.get("path", ""))
        if not target.is_file():
            raise FileNotFoundError(f"no such file: {ci.get('path')!r}")
        text = target.read_text(encoding="utf-8")
        old = ci.get("old_str", "")
        if old not in text:
            raise ValueError(f"old_str not found in {ci.get('path')!r}")
        target.write_text(text.replace(old, ci.get("new_str", "")), encoding="utf-8")
        return f"Replaced text in {ci.get('path')}"

    def _insert(self, ci: dict) -> str:
        target = self._resolve(ci.get("path", ""))
        if not target.is_file():
            raise FileNotFoundError(f"no such file: {ci.get('path')!r}")
        lines = target.read_text(encoding="utf-8").splitlines()
        at = int(ci.get("insert_line", len(lines)))
        at = max(0, min(at, len(lines)))
        lines.insert(at, ci.get("insert_text", ""))
        target.write_text("\n".join(lines) + "\n", encoding="utf-8")
        return f"Inserted line into {ci.get('path')}"

    def _delete(self, ci: dict) -> str:
        target = self._resolve(ci.get("path", ""))
        if target == self._root:
            raise MemoryPathError("refusing to delete the memory root")
        if target.is_dir():
            shutil.rmtree(target)
        elif target.exists():
            target.unlink()
        else:
            raise FileNotFoundError(f"no such path: {ci.get('path')!r}")
        return f"Deleted {ci.get('path')}"

    def _rename(self, ci: dict) -> str:
        src = self._resolve(ci.get("old_path", ""))
        dst = self._resolve(ci.get("new_path", ""))
        if not src.exists():
            raise FileNotFoundError(f"no such path: {ci.get('old_path')!r}")
        dst.parent.mkdir(parents=True, exist_ok=True)
        src.rename(dst)
        return f"Renamed {ci.get('old_path')} -> {ci.get('new_path')}"
