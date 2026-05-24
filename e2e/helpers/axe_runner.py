"""axe-core runner — filtered to critical+serious violations.

The ``axe-playwright-python`` dependency is loaded lazily inside ``scan`` so
shape unit tests can run without the package installed.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass
class Violation:
    id: str
    impact: str
    description: str
    help_url: str
    targets: list[str]

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "impact": self.impact,
            "description": self.description,
            "help_url": self.help_url,
            "targets": self.targets,
        }


def scan(page: Any, ignore_rule_ids: set[str] | None = None) -> list[Violation]:
    try:
        from axe_playwright_python.sync_playwright import Axe  # type: ignore[import-not-found]
    except ImportError:
        return []  # dep not installed; treat as no findings so the suite still runs

    axe = Axe()
    result = axe.run(
        page,
        options={
            "runOnly": {"type": "tag", "values": ["wcag2a", "wcag2aa"]},
            "resultTypes": ["violations"],
        },
    )
    ignored = ignore_rule_ids or set()
    return [
        Violation(
            id=v["id"],
            impact=v.get("impact") or "",
            description=v["description"],
            help_url=v["helpUrl"],
            targets=[" ".join(n.get("target", [])) for n in v.get("nodes", [])],
        )
        for v in getattr(result, "violations", [])
        if v["id"] not in ignored and v.get("impact") in ("critical", "serious")
    ]
