"""Drift gates for the Features registry.

The Features page renders entirely from ``apps.core.features``. Without these gates a
toggle added anywhere else in the codebase would simply stop being reachable from the
UI, silently — the page would still look complete. Each gate names the fix in its
failure message, mirroring ``test_feature_flag_inventory.py``.

Tests are excluded from the ``apps.core`` layering walk, so ``apps.get_model`` and
cross-app imports are fair game here.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest
from django.apps import apps as django_apps
from django.db import models

from apps.core.feature_flags import FEATURE_FLAGS
from apps.core.features import (
    EXEMPT_MODEL_FIELDS,
    FEATURES,
    GATED_MODELS,
    GROUPS,
    SCOPE_NOUN,
    env_vars,
    feature_keys,
    groups_by_key,
    model_field_pairs,
    setting_name,
    system_settings_fields,
)
from apps.core.runtime_config import _SPEC, RuntimeConfig

REPO_ROOT = Path(__file__).resolve().parents[4]
ROUTER_TSX = REPO_ROOT / "frontend" / "src" / "router.tsx"

# One pass over router.tsx, in source order: a `path:` value, the `[` that opens a
# `children:` array, and every other brace or bracket. Braces frame the route object a
# `path:` belongs to; a `children:` bracket carries that object's path down to its
# children. A flat scan for `path:` cannot do this — it reads `path: "features"` inside
# the `settings` subtree as `/features`. Full-line comments are stripped first so a
# commented-out route cannot unbalance the stacks.
_LINE_COMMENT = re.compile(r"(?m)^[ \t]*//.*$")
_ROUTE_TOKEN = re.compile(r'path:\s*"([^"]*)"|children\s*:\s*\[|[{}\[\]]')

# CI runs pytest from the repo root, where router.tsx is present and these gates bite.
# The dev `web` container mounts only backend/, so there they skip rather than lie.
needs_spa_source = pytest.mark.skipif(
    not ROUTER_TSX.exists(),
    reason="frontend/src/router.tsx not mounted in this container (CI runs from the repo root)",
)


# --- (a) registry <-> _SPEC, exact ------------------------------------------------


def test_registry_exactly_mirrors_runtime_config_spec():
    in_spec = {f for f, _, _ in _SPEC}
    in_registry = system_settings_fields()

    missing = in_spec - in_registry
    stale = in_registry - in_spec

    assert not missing, (
        f"runtime_config._SPEC field(s) with no Features registry row: {sorted(missing)} "
        "— add a backing='system_settings' row to apps/core/features.py or the knob is "
        "unreachable from Settings → Features"
    )
    assert not stale, (
        f"Features registry row(s) naming a _SPEC field that no longer exists: "
        f"{sorted(stale)} — remove the stale row"
    )


def test_each_system_settings_field_has_exactly_one_row():
    seen: dict[str, int] = {}
    for f in FEATURES:
        if f.backing == "system_settings":
            seen[f.settings_field] = seen.get(f.settings_field, 0) + 1
    dupes = {k: n for k, n in seen.items() if n > 1}
    assert not dupes, f"two registry rows write the same SystemSettings field: {dupes}"


def test_system_settings_rows_do_not_repeat_the_hard_default():
    """_SPEC owns the hard default. A second copy on the row is a drift source."""
    offenders = [
        f.key for f in FEATURES if f.backing == "system_settings" and f.shipped_default is not None
    ]
    assert not offenders, (
        f"row(s) redeclaring shipped_default for a _SPEC-backed field: {offenders} "
        "— drop it; hard_default() reads _SPEC"
    )


# --- (b) FEATURE_FLAGS coverage + infra exclusion ---------------------------------


def test_every_product_feature_flag_is_reachable_from_the_registry():
    product = {f.name for f in FEATURE_FLAGS if f.category == "feature"}
    reachable = {setting_name(f) for f in FEATURES} | env_vars()
    unreachable = product - reachable
    assert not unreachable, (
        f"product feature flag(s) with no Features page row: {sorted(unreachable)} "
        "— add a registry row (backing='system_settings', or 'env_only' with a reason)"
    )


def test_infra_and_test_flags_can_never_appear_on_the_features_page():
    forbidden = {f.name for f in FEATURE_FLAGS if f.category in ("infra", "test")}
    leaked = forbidden & (env_vars() | {setting_name(f) for f in FEATURES})
    assert not leaked, (
        f"infra/test flag(s) exposed on the Features page: {sorted(leaked)} — "
        "DJANGO_DEBUG and MOCK_EXTERNAL must never get a UI switch (a UI-settable "
        "MOCK_EXTERNAL makes every provider silently return canned fixtures)"
    )


def test_env_only_rows_state_a_reason():
    offenders = [f.key for f in FEATURES if f.backing == "env_only" and not f.env_only_reason]
    assert not offenders, (
        f"env_only row(s) with no env_only_reason: {offenders} — the page shows the "
        "reason inline; a read-only row without one reads as a bug"
    )


def test_the_four_known_env_only_knobs_are_present_and_read_only():
    """They are deliberately not migratable; the page must say so rather than omit them."""
    expected = {
        "AI_PROVIDER_MAX_RETRIES",
        "AI_PROVIDER_TIMEOUT_SECONDS",
        "TRIGGER_TICK_SECONDS",
        "OBSERVER_BEAT_TIMEZONE",
    }
    env_only = {f.env_var for f in FEATURES if f.backing == "env_only"}
    assert expected <= env_only, f"missing read-only row(s) for {sorted(expected - env_only)}"


# --- (c) per-object BooleanField coverage -----------------------------------------


@pytest.mark.django_db
def test_every_boolean_field_on_a_gated_model_has_a_registry_row():
    covered = model_field_pairs()
    missing: list[str] = []
    for label in GATED_MODELS:
        model = django_apps.get_model(label)
        for field in model._meta.get_fields():
            if not isinstance(field, models.BooleanField):
                continue
            dotted = f"{label}.{field.name}"
            if dotted in EXEMPT_MODEL_FIELDS:
                continue
            if (label, field.name) not in covered:
                missing.append(dotted)
    assert not missing, (
        f"BooleanField(s) with no Features registry row: {sorted(missing)} — add a row "
        "to apps/core/features.py, or add it to EXEMPT_MODEL_FIELDS with a comment "
        "saying why it records state rather than being a switch"
    )


def test_registry_model_labels_resolve():
    for label in sorted({f.model_label for f in FEATURES if f.model_label}):
        django_apps.get_model(label)  # raises LookupError on a stale label


@pytest.mark.django_db
def test_registry_model_fields_exist_on_their_model():
    missing = []
    for f in FEATURES:
        if not f.model_label:
            continue
        model = django_apps.get_model(f.model_label)
        names = {fl.name for fl in model._meta.get_fields()}
        if f.model_field not in names:
            missing.append(f"{f.key} -> {f.model_label}.{f.model_field}")
    assert not missing, f"registry row(s) pointing at a field that does not exist: {missing}"


# --- (d) honesty invariants -------------------------------------------------------


def test_keys_are_unique():
    keys = [f.key for f in FEATURES]
    dupes = sorted({k for k in keys if keys.count(k) > 1})
    assert not dupes, f"duplicate feature key(s): {dupes}"


def test_every_row_has_copy():
    blank = [f.key for f in FEATURES if not f.summary.strip() or not f.help.strip()]
    assert not blank, (
        f"row(s) with an empty summary or help: {blank} — the page renders both, and a "
        "switch nobody can explain is a switch nobody should flip"
    )


def test_costs_money_implies_a_cost_note():
    offenders = [f.key for f in FEATURES if f.costs_money and not f.cost_note.strip()]
    assert not offenders, (
        f"costs_money row(s) with no cost_note: {offenders} — the money badge must be "
        "able to say what it costs"
    )


def test_retroactive_rows_say_so_in_their_help():
    offenders = [f.key for f in FEATURES if f.retroactive and "retroactiv" not in f.help.lower()]
    assert not offenders, (
        f"retroactive row(s) whose help never says it: {offenders} — the confirm dialog "
        "quotes the help; it has to state that recorded numbers get restated"
    )


def test_requires_targets_are_real_keys():
    keys = feature_keys()
    broken = {f.key: [r for r in f.requires if r not in keys] for f in FEATURES}
    broken = {k: v for k, v in broken.items() if v}
    assert not broken, f"row(s) whose `requires` names an unknown feature key: {broken}"


def test_provider_only_is_a_known_provider():
    allowed = {"", "claude", "openai", "local"}
    offenders = {f.key: f.provider_only for f in FEATURES if f.provider_only not in allowed}
    assert not offenders, f"unknown provider_only value(s): {offenders}"


def test_every_group_referenced_exists_and_every_group_is_used():
    declared = set(groups_by_key())
    used = {f.group for f in FEATURES}
    assert not (used - declared), f"row(s) in an undeclared group: {sorted(used - declared)}"
    assert not (declared - used), f"declared group with no rows: {sorted(declared - used)}"
    orders = [g.order for g in GROUPS]
    assert len(set(orders)) == len(orders), "two groups share a sort order"


def test_per_object_scopes_have_a_rollup_noun():
    missing = sorted({f.scope for f in FEATURES if f.scope.startswith("per_")} - set(SCOPE_NOUN))
    assert not missing, f"per-object scope(s) with no plural noun for the rollup: {missing}"


def test_editable_rows_name_where_the_write_goes():
    """The page never invents an endpoint; it PATCHes whatever write_path says."""
    offenders = [
        f.key
        for f in FEATURES
        if f.backing == "system_settings" and f.write_path != "/api/settings/"
    ]
    assert not offenders, f"SystemSettings row(s) with the wrong write_path: {offenders}"


def test_no_secret_or_connection_variable_leaked_into_the_registry():
    """The exclusion rule, executable. Settings → Connections owns these."""
    banned_substrings = ("API_KEY", "SECRET", "PASSWORD", "TOKEN", "_URL", "DSN", "SALT")
    leaked = sorted(v for v in env_vars() if any(b in v for b in banned_substrings))
    assert not leaked, (
        f"secret/connection variable(s) exposed as a feature toggle: {leaked} — the "
        "Features page is not a .env editor"
    )


# --- (e) deep-link integrity ------------------------------------------------------


def _resolve_routes(src: str) -> set[str]:
    """Every concrete URL `createBrowserRouter` can match, nesting resolved.

    A child route's `path` is relative to its parent's, so the full URL is the chain of
    `path` values down the `children:` arrays. `prefixes` holds that chain, one entry
    per open bracket — a `children:` bracket inherits the enclosing route object's path,
    any other bracket contributes nothing, so a pathless layout route adds no segment.
    `paths` holds the path of each open brace, which is what a `children:` reads.
    Parameterised and wildcard routes match a family rather than one URL, so they are
    not deep-link targets and are dropped.
    """
    routes = {"/"}
    prefixes: list[str] = []
    paths: list[str] = []
    for match in _ROUTE_TOKEN.finditer(_LINE_COMMENT.sub("", src)):
        token = match.group(0)
        if token.startswith("path"):
            if paths:
                paths[-1] = match.group(1)
            routes.add("/" + "/".join(p for p in [*prefixes, match.group(1).strip("/")] if p))
        elif token.startswith("children"):
            prefixes.append(paths[-1].strip("/") if paths else "")
        elif token == "{":
            paths.append("")
        elif token == "[":
            prefixes.append("")
        elif token == "}":
            if paths:
                paths.pop()
        elif prefixes:
            prefixes.pop()
    return {r for r in routes if ":" not in r and "*" not in r}


def _spa_routes() -> set[str]:
    return _resolve_routes(ROUTER_TSX.read_text())


def test_route_resolution_reads_nesting_rather_than_flattening_it():
    """The resolver is the gate. A flat scan for `path:` reports `/features` for a page
    served at `/settings/features`, which passes a deep link that 404s and fails one
    that works — so the resolver's own nesting behaviour is asserted here."""
    fixture = """
      { path: "/render/chart", element: <R /> },
      { path: "/", element: <L />, children: [
          { index: true, element: <D /> },
          { path: "settings", element: <S />, children: [
              { path: "features", element: <F /> },
              { path: "deep/er", element: <X /> },
          ] },
          { path: "watchlists/:id", element: <W /> },
          { element: <Pathless />, children: [{ path: "costs" }] },
      ] },
    """
    assert _resolve_routes(fixture) == {
        "/",
        "/render/chart",
        "/settings",
        "/settings/features",
        "/settings/deep/er",
        "/costs",  # a pathless layout route contributes no segment
    }


def test_router_source_is_anchored_inside_this_checkout():
    """`REPO_ROOT` is `parents[4]` of this file. A wrong index points `ROUTER_TSX` at a
    path that never exists, `needs_spa_source` skips every deep-link gate, and the
    registry's links stop being checked against anything at all."""
    anchors = [
        REPO_ROOT / "backend" / "apps" / "core" / "features.py",
        REPO_ROOT / "backend" / "apps" / "core" / "tests" / "test_feature_registry.py",
    ]
    missing = [str(p) for p in anchors if not p.is_file()]
    assert not missing, (
        f"REPO_ROOT resolves to {REPO_ROOT}, which is not this checkout — {missing} is "
        "not there. Fix the parents[N] index; until then every gate below skips."
    )


@needs_spa_source
def test_every_deep_link_resolves_to_a_real_spa_route():
    routes = _spa_routes()
    broken = sorted(
        {f.deep_link for f in FEATURES if f.deep_link and f.deep_link.split("#")[0] not in routes}
    )
    assert not broken, (
        f"deep_link(s) pointing at a route that does not exist in frontend/src/router.tsx: "
        f"{broken} — an empty deep_link is legal and means 'no UI surface yet'"
    )


@needs_spa_source
def test_every_toggles_doc_page_name_is_a_real_spa_route():
    """`toggles_doc.PAGES` names the page behind each deep link. A key that is not a
    route names a page the document sends the reader to and the app cannot open."""
    from apps.core.management.commands.toggles_doc import PAGES

    routes = _spa_routes()
    broken = sorted(link for link in PAGES if link.split("#")[0] not in routes)
    assert not broken, (
        f"toggles_doc.PAGES key(s) that are not SPA routes: {broken} — drop them, or "
        "point them at the route the page is actually served from"
    )


@needs_spa_source
def test_the_tradingview_manage_path_resolves():
    """The gated-row reason links here; a dead link there is worse than no link."""
    from apps.core.feature_views import _TRADINGVIEW_MANAGE_PATH

    assert _TRADINGVIEW_MANAGE_PATH == "/settings/connections"
    assert _TRADINGVIEW_MANAGE_PATH in _spa_routes(), (
        "Settings → Connections moved; update _TRADINGVIEW_MANAGE_PATH in "
        "apps/core/feature_views.py"
    )


# --- (f) structural drift ---------------------------------------------------------


@pytest.mark.django_db
def test_spec_dataclass_and_columns_stay_in_lockstep():
    """A _SPEC row without its RuntimeConfig annotation makes runtime_config() raise
    TypeError on EVERY call — capture, observer, triggers and threads all at once."""
    from apps.core.models import SystemSettings

    spec_fields = {f for f, _, _ in _SPEC}
    assert set(RuntimeConfig.__dataclass_fields__) == spec_fields
    columns = {f.name for f in SystemSettings._meta.get_fields()}
    assert spec_fields <= columns, (
        f"_SPEC field(s) with no SystemSettings column: {sorted(spec_fields - columns)}"
    )
