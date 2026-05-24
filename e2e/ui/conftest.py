"""UI lane conftest — Playwright fixtures are inherited from top-level e2e/conftest.py.

Adds an autouse fixture that attaches the console guard to every UI-marked
test. Any unhandled ``console.error``, ``pageerror``, or unexpected 5xx network
response fails the test even if its asserts pass.
"""

from __future__ import annotations

import pytest

from e2e.helpers import console_guard


@pytest.fixture(autouse=True)
def _ui_console_guard(request):
    marker = request.node.get_closest_marker("ui")
    if marker is None:
        yield
        return
    # ``page`` may not be requested by this test — only attach if it is.
    try:
        page = request.getfixturevalue("page")
    except pytest.FixtureLookupError:
        yield
        return
    errors = console_guard.attach(page)
    yield
    if errors:
        pytest.fail("Unexpected console/network errors:\n" + "\n".join(errors))
