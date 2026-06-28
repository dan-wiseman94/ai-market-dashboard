"""Unit-shape + behavior tests for the console guard helper."""

from __future__ import annotations

from typing import Any


def test_console_guard_api() -> None:
    from e2e.helpers import console_guard

    assert hasattr(console_guard, "attach")
    assert hasattr(console_guard, "ALLOWED_CONSOLE_PATTERNS")
    assert hasattr(console_guard, "ALLOWED_NETWORK_PATHS")


class _Msg:
    """Minimal stand-in for a Playwright ConsoleMessage."""

    def __init__(self, type_: str, text: str) -> None:
        self.type = type_
        self.text = text


class _FakePage:
    """Records the handlers ``console_guard.attach`` registers, lets us emit events."""

    def __init__(self) -> None:
        self._handlers: dict[str, Any] = {}

    def on(self, event: str, cb: Any) -> None:
        self._handlers[event] = cb

    def emit_console(self, text: str) -> None:
        self._handlers["console"](_Msg("error", text))


def test_react_router_errorboundary_is_not_masked() -> None:
    """A route that throws into React Router's default ErrorBoundary must FAIL the
    test — it is the signature of navigating to a broken/unregistered route."""
    from e2e.helpers import console_guard

    page = _FakePage()
    errors = console_guard.attach(page)
    page.emit_console("Error handled by React Router default ErrorBoundary: Error: 404")
    assert errors, "router ErrorBoundary console error must surface (broken-route regression)"


def test_unexpected_404_still_surfaces() -> None:
    """A 404 from an endpoint that is NOT on the benign allow-list must surface."""
    from e2e.helpers import console_guard

    page = _FakePage()
    errors = console_guard.attach(page)
    page.emit_console(
        "Failed to load resource: the server responded with a status of "
        "404 (Not Found) /api/widgets/"
    )
    assert errors, "an unexpected 404 must surface; only known-benign URLs are allowed"


def test_known_benign_files_404_is_allowed() -> None:
    """The documented benign /api/files/ 404 (before any file exists) stays allowed."""
    from e2e.helpers import console_guard

    page = _FakePage()
    errors = console_guard.attach(page)
    page.emit_console(
        "Failed to load resource: the server responded with a status of 404 (Not Found) /api/files/"
    )
    assert not errors, "the documented benign /api/files/ 404 stays allow-listed"
