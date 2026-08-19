"""Per-profile memory directory is isolated and created on demand."""

from __future__ import annotations

import os
import shutil
import tempfile

import pytest

from apps.ai.memory import memory_dir_for_profile


@pytest.fixture
def tmp_data(monkeypatch):
    tmp = tempfile.mkdtemp(prefix="mem-")
    monkeypatch.setenv("AI_MEMORY_ROOT", tmp)
    yield tmp
    shutil.rmtree(tmp, ignore_errors=True)


def test_directory_is_created_per_profile(tmp_data) -> None:
    path = memory_dir_for_profile(profile_id=7)
    assert os.path.isdir(path)
    assert path.endswith("/7")


def test_directories_for_different_profiles_are_isolated(tmp_data) -> None:
    a = memory_dir_for_profile(profile_id=1)
    b = memory_dir_for_profile(profile_id=2)
    assert a != b
    assert os.path.dirname(a) == os.path.dirname(b)


def test_reuses_existing_directory(tmp_data) -> None:
    p1 = memory_dir_for_profile(profile_id=5)
    with open(os.path.join(p1, "note.md"), "w") as f:
        f.write("hi")
    p2 = memory_dir_for_profile(profile_id=5)
    assert p1 == p2
    assert os.path.exists(os.path.join(p2, "note.md"))


@pytest.fixture
def handler(tmp_path):
    from apps.ai.memory import MemoryToolHandler

    return MemoryToolHandler(str(tmp_path / "mem"))


def test_create_then_view_file(handler):
    out = handler.run(
        {"command": "create", "path": "/memories/notes.md", "file_text": "hello\nworld\n"}
    )
    assert out["ok"] is True
    v = handler.run({"command": "view", "path": "/memories/notes.md"})
    assert v["ok"] is True
    assert "hello" in v["result"] and "world" in v["result"]


def test_view_directory_lists_entries(handler):
    handler.run({"command": "create", "path": "/memories/a.md", "file_text": "x"})
    handler.run({"command": "create", "path": "/memories/sub/b.md", "file_text": "y"})
    v = handler.run({"command": "view", "path": "/memories"})
    assert v["ok"] is True
    assert "a.md" in v["result"]
    assert "sub" in v["result"]


def test_view_range_slices_lines(handler):
    handler.run({"command": "create", "path": "/memories/n.md", "file_text": "l1\nl2\nl3\nl4\n"})
    v = handler.run({"command": "view", "path": "/memories/n.md", "view_range": [2, 3]})
    assert "l2" in v["result"] and "l3" in v["result"]
    assert "l1" not in v["result"] and "l4" not in v["result"]


def test_str_replace_replaces_text(handler):
    handler.run({"command": "create", "path": "/memories/n.md", "file_text": "the quick brown fox"})
    out = handler.run(
        {"command": "str_replace", "path": "/memories/n.md", "old_str": "quick", "new_str": "slow"}
    )
    assert out["ok"] is True
    v = handler.run({"command": "view", "path": "/memories/n.md"})
    assert "slow brown fox" in v["result"]


def test_str_replace_missing_old_str_errors(handler):
    handler.run({"command": "create", "path": "/memories/n.md", "file_text": "abc"})
    out = handler.run(
        {"command": "str_replace", "path": "/memories/n.md", "old_str": "zzz", "new_str": "x"}
    )
    assert out["ok"] is False


def test_insert_adds_line_at_position(handler):
    handler.run({"command": "create", "path": "/memories/n.md", "file_text": "l1\nl3\n"})
    out = handler.run(
        {"command": "insert", "path": "/memories/n.md", "insert_line": 1, "insert_text": "l2"}
    )
    assert out["ok"] is True
    res = handler.run({"command": "view", "path": "/memories/n.md"})["result"]
    assert res.index("l1") < res.index("l2") < res.index("l3")


def test_delete_file(handler):
    handler.run({"command": "create", "path": "/memories/n.md", "file_text": "x"})
    assert handler.run({"command": "delete", "path": "/memories/n.md"})["ok"] is True
    assert handler.run({"command": "view", "path": "/memories/n.md"})["ok"] is False


def test_rename_file(handler):
    handler.run({"command": "create", "path": "/memories/a.md", "file_text": "x"})
    out = handler.run(
        {"command": "rename", "old_path": "/memories/a.md", "new_path": "/memories/b.md"}
    )
    assert out["ok"] is True
    assert handler.run({"command": "view", "path": "/memories/b.md"})["ok"] is True
    assert handler.run({"command": "view", "path": "/memories/a.md"})["ok"] is False


def test_path_traversal_is_rejected(handler):
    assert (
        handler.run({"command": "create", "path": "/memories/../escape.md", "file_text": "x"})["ok"]
        is False
    )
    assert handler.run({"command": "view", "path": "../../etc/passwd"})["ok"] is False


def test_unknown_command_errors(handler):
    assert handler.run({"command": "frobnicate", "path": "/memories/x"})["ok"] is False


def test_dispatch_routes_memory_to_handler():
    from apps.ai.providers.claude import _dispatch_tool

    class FakeHandler:
        def __init__(self):
            self.called = None

        def run(self, ci):
            self.called = ci
            return {"ok": True, "result": "MEM"}

    class FakeToolset:
        def run(self, name, ci):
            return {"ok": True, "result": f"TOOL:{name}"}

    mem = FakeHandler()
    out = _dispatch_tool("memory", {"command": "view"}, memory_handler=mem, toolset=FakeToolset())
    assert out["result"] == "MEM"
    assert mem.called == {"command": "view"}

    out2 = _dispatch_tool("get_quote", {"ticker": "SPY"}, memory_handler=mem, toolset=FakeToolset())
    assert out2["result"] == "TOOL:get_quote"


def test_dispatch_memory_without_handler_falls_through_to_toolset():
    from apps.ai.providers.claude import _dispatch_tool

    class FakeToolset:
        def run(self, name, ci):
            return {"ok": False, "error": f"Unknown tool: {name}"}

    out = _dispatch_tool("memory", {}, memory_handler=None, toolset=FakeToolset())
    assert out["ok"] is False
