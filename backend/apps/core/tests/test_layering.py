"""Architecture guard: apps.core is the dependency foundation.

The 15-app graph is a dense web (~20 mutual import pairs, mostly lazy
function-level imports that resolve fine at call time). A full acyclic layering
contract would require moving models and inverting dependencies across that whole
web — deliberately deferred. But ONE invariant is both true today and worth
locking: ``apps.core`` must not import any other app at MODULE LOAD time. It is
the foundation every other app builds on; a module-level ``from apps.<x>`` here
would create a boot-time cycle (core is imported very early) that nothing else
catches until runtime.

Function-level / TYPE_CHECKING imports are allowed (e.g. core.tasks.prune_retention
lazily imports the models it prunes) — those resolve at call time, not at import.
"""

from __future__ import annotations

import ast
import pathlib

CORE = pathlib.Path(__file__).resolve().parent.parent  # backend/apps/core


def _module_level_app_imports(pkg_dir: pathlib.Path, self_app: str) -> list[str]:
    """Module-level (not function-level, not TYPE_CHECKING) `apps.<other>` imports."""
    offenders: list[str] = []
    for py in pkg_dir.rglob("*.py"):
        if "migrations" in py.parts or "tests" in py.parts:
            continue
        tree = ast.parse(py.read_text(), filename=str(py))
        for node in tree.body:  # ONLY the module body — skips functions and `if TYPE_CHECKING:`
            if isinstance(node, ast.ImportFrom) and (node.module or "").startswith("apps."):
                target = node.module.split(".")[1]
                if target != self_app:
                    offenders.append(f"{py.name}: from {node.module} import ...")
            elif isinstance(node, ast.Import):
                for alias in node.names:
                    if alias.name.startswith("apps.") and alias.name.split(".")[1] != self_app:
                        offenders.append(f"{py.name}: import {alias.name}")
    return offenders


def test_core_imports_no_other_app_at_module_load():
    offenders = _module_level_app_imports(CORE, "core")
    assert offenders == [], (
        "apps.core must stay the foundation — move these cross-app imports inside "
        f"the function that uses them (lazy import):\n  " + "\n  ".join(offenders)
    )
