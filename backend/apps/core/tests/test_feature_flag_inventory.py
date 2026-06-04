"""Drift gate: the feature-flag registry mirrors the env.bool toggles in settings.

Complexity lever (CLAUDE.md / docs/feature-flags.md): opt-in flags multiply the
behaviour-space the suite must cover.  This keeps the inventory honest — a flag added
to ``config/settings`` without a ``FEATURE_FLAGS`` entry (undocumented), or a registry
entry whose flag was deleted (stale), turns red.  Mirrors the OpenAPI/schema drift
gates for env configuration.

The settings side is derived by scanning the source for ``env.bool("NAME")`` — a
precise, deterministic pattern (numeric tuning knobs use env.int/float and are out of
scope; presence-toggles like SENTRY_DSN are documented in prose, not gated here).
"""

import re
from pathlib import Path

import config.settings.base as base_settings

from apps.core.feature_flags import flag_names

_ENV_BOOL = re.compile(r'env\.bool\(\s*"([A-Z_][A-Z0-9_]*)"')


def _settings_bool_flag_names() -> set[str]:
    settings_dir = Path(base_settings.__file__).parent
    names: set[str] = set()
    for py in settings_dir.glob("*.py"):
        names |= set(_ENV_BOOL.findall(py.read_text()))
    return names


def test_registry_exactly_mirrors_settings_env_bool_flags():
    in_settings = _settings_bool_flag_names()
    in_registry = flag_names()

    undocumented = in_settings - in_registry
    stale = in_registry - in_settings

    assert not undocumented, (
        f"env.bool flag(s) in config/settings with no FEATURE_FLAGS entry: {sorted(undocumented)} "
        "— add them to apps/core/feature_flags.py (and docs/feature-flags.md)"
    )
    assert not stale, (
        f"FEATURE_FLAGS entr(ies) whose env.bool flag no longer exists in settings: {sorted(stale)} "
        "— remove the stale registry entry"
    )
