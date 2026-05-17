"""Visual lane conftest — pin viewport + color scheme."""

from __future__ import annotations

import pytest
from playwright.sync_api import Browser


@pytest.fixture
def context(browser: Browser):
    ctx = browser.new_context(
        viewport={"width": 1280, "height": 800},
        device_scale_factor=1,
        color_scheme="light",
    )
    yield ctx
    ctx.close()
