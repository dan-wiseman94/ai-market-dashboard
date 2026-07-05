"""Import-hygiene guard.

Every ``from apps.<x>`` / ``import apps.<x>`` across the backend + e2e trees must name a
REAL installed app. Catches the "moved/removed an app but left a stale import" class of
bug — an e2e-only stale import surfaces only in CI (the `ui` lane), never in the
backend suite, so this guard has to scan the e2e tree too.

Why a STATIC scan (regex over import lines) rather than importing every module:
function-local imports (``def f(): from apps.foo.models import ...``) don't execute
at import time, so an import-based check misses exactly those cases. A static
scan of import statements catches them wherever they live (module- or function-level).

The first dotted segment after ``apps.`` is the app; subpackages like
``apps.observer.triggers`` resolve to the real app ``observer`` and are fine.
"""

from __future__ import annotations

import re
from pathlib import Path

# This file: backend/apps/core/tests/test_import_hygiene.py → parents[4] = repo root.
_ROOT = Path(__file__).resolve().parents[4]
_APPS_DIR = _ROOT / "backend" / "apps"
# e2e/ is absent in backend-only test mounts; present in CI + a full checkout (skipped if absent).
_SCAN_DIRS = (_ROOT / "backend" / "apps", _ROOT / "backend" / "config", _ROOT / "e2e")
_IMPORT_RE = re.compile(r"^\s*(?:from|import)\s+apps\.([a-z_][a-z0-9_]*)")


def _installed_app_labels() -> set[str]:
    return {p.name for p in _APPS_DIR.iterdir() if p.is_dir() and (p / "__init__.py").exists()}


def test_no_stale_app_imports() -> None:
    valid = _installed_app_labels()
    assert valid, "could not enumerate apps/ — wrong root?"
    stale: list[str] = []
    for root in _SCAN_DIRS:
        if not root.exists():
            continue
        for py in root.rglob("*.py"):
            for lineno, line in enumerate(py.read_text(encoding="utf-8").splitlines(), 1):
                m = _IMPORT_RE.match(line)
                if m and m.group(1) not in valid:
                    stale.append(
                        f"{py.relative_to(_ROOT)}:{lineno}: imports `apps.{m.group(1)}` — not an installed app"
                    )
    assert not stale, (
        "Stale `apps.<app>` imports found (an app was moved/removed but a reference "
        "wasn't repointed — e.g. a model that moved into a subpackage):\n  " + "\n  ".join(stale)
    )
