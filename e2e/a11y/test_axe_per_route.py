"""Axe-core scans — one per top-level route. Critical+serious only."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from e2e.a11y.a11y_ignores import IGNORED_RULES
from e2e.helpers import axe_runner

ROUTES: list[tuple[str, str, str]] = [
    ("/", "minimal", "dashboard"),
    ("/snapshot", "minimal", "snapshot_composer"),
    ("/threads", "threads", "threads_list"),
    ("/threads/<thread>", "threads", "thread_detail"),
    ("/threads/observer/<profile>", "observer", "observer_timeline"),
    ("/schedules", "observer", "schedules"),
    ("/triggers", "triggers", "triggers_list"),
    ("/triggers/new", "minimal", "trigger_editor"),
    ("/analytics", "analytics", "analytics"),
    ("/watchlists", "market", "watchlists"),
    ("/watchlists/<wl>", "market", "watchlist_detail"),
    ("/profiles", "minimal", "profiles"),
    ("/costs", "analytics", "costs"),
    ("/settings/backups", "minimal", "backups"),
    ("/settings/export", "threads", "export"),
]


ARTIFACTS = Path("e2e/a11y/artifacts")


def _resolve_path(path: str) -> str:
    if path == "/threads/<thread>":
        from apps.threads.models import Thread

        t = Thread.objects.first()
        return f"/threads/{t.id}" if t else "/threads"
    if path == "/watchlists/<wl>":
        from apps.profiles.models import Watchlist

        w = Watchlist.objects.first()
        return f"/watchlists/{w.id}" if w else "/watchlists"
    if path == "/threads/observer/<profile>":
        from apps.profiles.models import TradingProfile

        p = TradingProfile.objects.first()
        return f"/threads/observer/{p.id}" if p else "/threads"
    return path


@pytest.mark.integration
@pytest.mark.a11y
@pytest.mark.parametrize("path,rung,name", ROUTES)
def test_axe_per_route(page, frontend_base_url, path, rung, name, request) -> None:
    request.getfixturevalue(rung)
    resolved = _resolve_path(path)
    page.goto(f"{frontend_base_url}{resolved}")
    page.wait_for_load_state("networkidle")
    violations = axe_runner.scan(page, ignore_rule_ids=IGNORED_RULES)
    ARTIFACTS.mkdir(parents=True, exist_ok=True)
    if violations:
        (ARTIFACTS / f"{name}.json").write_text(
            json.dumps([v.to_dict() for v in violations], indent=2)
        )
    assert not violations, f"{name}: {len(violations)} critical/serious a11y violations"
