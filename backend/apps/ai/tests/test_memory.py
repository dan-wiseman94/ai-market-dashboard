"""Per-profile memory directory is isolated and created on demand."""
from __future__ import annotations

import os
import shutil
import tempfile

import pytest

from apps.ai.memory import memory_dir_for_profile


@pytest.fixture
def tmp_data(monkeypatch):
    tmp = tempfile.mkdtemp(prefix="m10-mem-")
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
