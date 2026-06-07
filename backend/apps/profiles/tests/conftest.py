"""Restore the migration-seeded AgentPreset builtins before each profiles test.

A ``transaction=True`` test elsewhere (the snapshots/threads consumers, partial_persist)
flushes the DB at teardown, and data-migration-seeded rows are loaded once at test-DB
creation — NOT restored after a TransactionTestCase flush. Under random order such a test
can run before this app's, leaving the AgentPreset table empty so the builtin assertions
in ``test_agent_presets`` fail (the per-commit gate hides it by running ``-p no:randomly``).

pytest-django's ``serialized_rollback`` does not reliably restore the seeds under
``--reuse-db``, so we just re-run the (idempotent, ``get_or_create``-based) seed functions
here — making these tests order- and db-reuse-independent. Scoped to this app's tests only.
"""

from __future__ import annotations

import importlib

import pytest
from django.apps import apps as django_apps

# Every profiles data-migration that seeds builtin AgentPresets. Each exposes
# ``seed_presets(apps, schema_editor)`` doing idempotent get_or_create over its BUILTINS.
_SEED_MIGRATIONS = (
    "apps.profiles.migrations.0005_seed_agent_presets",
    "apps.profiles.migrations.0006_seed_more_agent_presets",
    "apps.profiles.migrations.0008_seed_macro_fundamentals_preset",
)


@pytest.fixture(autouse=True)
def _restore_builtin_presets(db):
    for modname in _SEED_MIGRATIONS:
        # modname is from the hardcoded _SEED_MIGRATIONS whitelist (not user input);
        # importlib is required because migration modules start with a digit.
        mod = importlib.import_module(modname)  # nosemgrep
        mod.seed_presets(django_apps, None)
