from __future__ import annotations

from pathlib import Path

import pytest
from django.conf import settings


@pytest.fixture(autouse=True)
def _seed_spa_index() -> None:
    """Ensure an index.html exists for the TemplateView spa-fallback."""
    templates: list[dict] = settings.TEMPLATES
    target = Path(templates[0]["DIRS"][0]) / "index.html"
    if target.exists():
        return
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(
        "<!doctype html><html><head><title>ai-dash</title></head><body></body></html>"
    )
