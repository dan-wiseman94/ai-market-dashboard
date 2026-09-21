"""Per-profile memory for Claude's Memory tool (memory_20250818).

Layout: `<AI_MEMORY_ROOT>/<profile_id>/`. `memory_dir_for_profile` guarantees
isolation between profiles and (unless asked not to) that the directory exists. `MemoryToolHandler`
executes the model's memory commands against that directory — the client side of
the tool, which Anthropic does NOT run for you.

The store is written by the model, and the model reads untrusted DATA (snapshot
text, news, filings, tool output — see the data-boundary directive in
`apps.threads.coach.build_system_prompt`). Anything it writes here is re-read on
every later run of that profile, so `list_memory_entries` / `clear_memory` back
the inspect-and-wipe endpoints (`/api/profiles/<id>/memory/`) that make that
store auditable. Both resolve through `memory_dir_for_profile` and re-check
containment before touching the filesystem: the profile id arrives from a URL
and `clear_memory` removes directory trees.
"""

from __future__ import annotations

import os
import shutil
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

#: Characters of each file surfaced by the viewer. Enough to recognize injected
#: instructions; short enough that a listing of a large store stays cheap.
PREVIEW_CHARS = 400


class MemoryPathError(Exception):
    """A memory command referenced a path outside the sandboxed root."""


def memory_root() -> Path:
    """The resolved directory that every profile's memory lives under."""
    return Path(os.environ.get("AI_MEMORY_ROOT", "/data/memory")).resolve()


def _contains(root: Path, candidate: Path) -> bool:
    return root in candidate.parents


def memory_dir_for_profile(*, profile_id: int | str, create: bool = True) -> str:
    """Resolve (and by default create) one profile's memory directory.

    Raises `MemoryPathError` when `profile_id` resolves anywhere but a direct
    child of the root — the id reaches the read/clear endpoints from a URL, so
    this containment check is the guard, not a formality. `create=False` lets a
    reader ask about a profile that has never run without conjuring a directory
    for it.
    """
    root = memory_root()
    path = (root / str(profile_id)).resolve()
    if not _contains(root, path):
        raise MemoryPathError(f"memory dir escapes memory root: {profile_id!r}")
    if create:
        path.mkdir(parents=True, exist_ok=True)
    return str(path)


def memory_store_exists(*, profile_id: int | str) -> bool:
    """True once the profile has a memory directory (i.e. it has run with memory on)."""
    return Path(memory_dir_for_profile(profile_id=profile_id, create=False)).is_dir()


def _entry(*, file_path: Path, rel: str, preview_chars: int) -> dict[str, Any]:
    stat = file_path.stat()
    # errors="replace" so a binary or mis-encoded file previews as mojibake
    # instead of raising and hiding the whole listing; reading preview_chars+1
    # characters bounds the read no matter how large the file is.
    with file_path.open("r", encoding="utf-8", errors="replace") as fh:
        chunk = fh.read(preview_chars + 1)
    return {
        "path": rel,
        "size_bytes": stat.st_size,
        "modified_at": datetime.fromtimestamp(stat.st_mtime, tz=UTC),
        "preview": chunk[:preview_chars],
        "preview_truncated": len(chunk) > preview_chars,
    }


def list_memory_entries(
    *, profile_id: int | str, preview_chars: int = PREVIEW_CHARS
) -> list[dict[str, Any]]:
    """Every readable file in the profile's store, path-sorted, with a preview.

    A profile that has never run has no directory: that is an empty list, not an
    error. Symlinks are skipped rather than followed — a link planted in the
    store must not turn the viewer into an arbitrary-file reader.
    """
    root = memory_root()
    directory = Path(memory_dir_for_profile(profile_id=profile_id, create=False))
    if not directory.is_dir():
        return []

    entries: list[dict[str, Any]] = []
    for dirpath, dirnames, filenames in os.walk(directory, followlinks=False):
        here = Path(dirpath)
        dirnames[:] = sorted(d for d in dirnames if not (here / d).is_symlink())
        for name in sorted(filenames):
            file_path = here / name
            if file_path.is_symlink() or not file_path.is_file():
                continue
            if not _contains(root, file_path.resolve()):
                continue
            entries.append(
                _entry(
                    file_path=file_path,
                    rel=str(file_path.relative_to(directory)),
                    preview_chars=preview_chars,
                )
            )
    entries.sort(key=lambda e: str(e["path"]))
    return entries


def clear_memory(*, profile_id: int | str) -> dict[str, int]:
    """Delete everything in the profile's store; report what went.

    Counts and bytes come from the same listing the viewer shows (regular files
    only); symlinks are unlinked without being followed or counted. The
    directory itself survives so the next run writes into it as before.
    """
    root = memory_root()
    directory = Path(memory_dir_for_profile(profile_id=profile_id, create=False))
    if not directory.is_dir():
        return {"removed_files": 0, "removed_bytes": 0}
    # Re-check containment immediately before an rmtree: memory_dir_for_profile
    # already refused an escaping id, and this is the line that deletes trees.
    if not _contains(root, directory):
        raise MemoryPathError(f"refusing to clear outside the memory root: {directory}")

    entries = list_memory_entries(profile_id=profile_id, preview_chars=0)
    removed = {
        "removed_files": len(entries),
        "removed_bytes": sum(int(e["size_bytes"]) for e in entries),
    }
    for child in directory.iterdir():
        if child.is_symlink():
            child.unlink()
        elif child.is_dir():
            shutil.rmtree(child)
        else:
            child.unlink()
    return removed


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
            entries = sorted(f"{c.name}/" if c.is_dir() else c.name for c in target.iterdir())
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
