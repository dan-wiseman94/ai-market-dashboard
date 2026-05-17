"""Unit-shape test for the console guard helper."""

from __future__ import annotations


def test_console_guard_api() -> None:
    from e2e.helpers import console_guard

    assert hasattr(console_guard, "attach")
    assert hasattr(console_guard, "ALLOWED_CONSOLE_PATTERNS")
    assert hasattr(console_guard, "ALLOWED_NETWORK_PATHS")
