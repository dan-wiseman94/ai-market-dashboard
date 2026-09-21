"""Render the Features registry to ``docs/toggles.md``.

The registry (``apps.core.features``) is the single source of truth for what the app
can switch on and off; this command turns it into the human inventory, and
``apps/core/tests/test_toggles_doc.py`` fails when the committed file and the registry
disagree. That gate is the reason the doc is generated: a Markdown narrative nothing
checks goes stale the first time a toggle is added.

Rendering reads the registry, the runtime-config spec and Django model field defaults —
no database, no environment, no live values — so the output is the *shipped* posture and
is byte-identical on any machine.

Usage (the docs directory is not mounted inside the ``web`` container, so redirect from
the host rather than writing in place)::

    docker compose exec -T web uv run python manage.py toggles_doc > docs/toggles.md
    docker compose exec -T web uv run python manage.py toggles_doc --check   # CI-style

No module-level ``from apps.<other>`` import: ``apps/core/tests/test_layering.py`` walks
this package. Model defaults are reached through ``django.apps.apps.get_model``.
"""

from __future__ import annotations

from decimal import Decimal
from pathlib import Path
from typing import Any

from django.apps import apps as django_apps
from django.core.management.base import BaseCommand, CommandError
from django.db.models import NOT_PROVIDED

from apps.core.features import (
    FEATURES,
    GROUPS,
    Feature,
    hard_default,
    setting_name,
)

DOC_PATH = Path(__file__).resolve().parents[5] / "docs" / "toggles.md"

# SPA page behind each deep link. `apps/core/tests/test_toggles_doc.py` fails on a
# deep link with no entry here, and the registry's own gate fails on a deep link that
# is not a real route — between them a renamed page cannot rot silently in this file.
PAGES: dict[str, str] = {
    "/profiles": "Profiles",
    "/schedules": "Schedules",
    "/triggers": "Triggers",
    "/theses": "Theses",
    "/briefing": "Briefing",
    "/snapshot": "Snapshot composer",
    "/lessons": "Lessons",
    "/settings": "Settings → AI Providers",
}

# Display name per `requires_connection` id. Same reason as PAGES: the doc must not
# invent a spelling for something the user has to find in the UI.
CONNECTIONS: dict[str, str] = {"tradingview": "TradingView"}

# Singular of SCOPE_NOUN, for "per schedule" phrasing in the location column.
SCOPE_SINGULAR: dict[str, str] = {
    "per_provider": "provider",
    "per_profile": "profile",
    "per_preset": "preset",
    "per_schedule": "schedule",
    "per_trigger": "trigger",
    "per_thesis": "thesis",
    "per_lesson": "lesson",
    "per_capture": "profile",
}

# Mirrors the EXCLUSION RULE in apps/core/features.py. These never become toggles;
# `test_no_secret_or_connection_variable_leaked_into_the_registry` enforces it.
EXCLUDED_CONNECTION_VARS: tuple[str, ...] = (
    "DJANGO_SECRET_KEY",
    "DJANGO_ALLOWED_HOSTS",
    "POSTGRES_*",
    "REDIS_URL",
    "CELERY_*",
    "ENCRYPTION_SALT_PATH",
    "SNAPSHOT_IMAGE_DIR",
    "RENDER_BASE_URL",
    "FRONTEND_BASE_URL",
    "SCHWAB_*",
    "TRADINGVIEW_MCP_URL",
    "TRADINGVIEW_MCP_CALLBACK_URL",
    "SEC_EDGAR_USER_AGENT",
    "SENTRY_DSN",
    "MCP_AUTH_TOKEN",
    "*_API_KEY",
)


# --- value formatting -------------------------------------------------------------


def _model_default(f: Feature) -> Any:
    """The default a new row gets, with a callable default resolved.

    A JSON list field that defaults empty may still be seeded on save from a
    ``DEFAULT_<NAME>`` class constant (``TradingProfile.default_includes`` ->
    ``DEFAULT_INCLUDES``). Reporting the raw empty list there would understate what a
    fresh profile actually captures.
    """
    model = django_apps.get_model(f.model_label)
    default = model._meta.get_field(f.model_field).default
    if default is NOT_PROVIDED:
        return None
    value = default() if callable(default) else default
    if value == []:
        seeded = getattr(model, f"DEFAULT_{f.model_field.removeprefix('default_').upper()}", None)
        if seeded:
            return list(seeded)
    return value


def _default_of(f: Feature) -> Any:
    if f.backing == "model_field" and f.scope != "singleton":
        return _model_default(f)
    return hard_default(f)


def _default_section_kinds() -> list[str]:
    return list(django_apps.get_model("profiles.TradingProfile").DEFAULT_INCLUDES)


def _fmt_number(value: float, unit: str) -> str:
    if unit == "USD":
        return f"${value:,.2f}"
    rendered = f"{value:,g}"
    return f"{rendered} {unit}".strip()


def _fmt_default(f: Feature, value: Any) -> str:
    if f.key.startswith("section."):
        if f.backing == "informational":
            return "Always on"
        kind = f.key.removeprefix("section.")
        return "On" if kind in _default_section_kinds() else "Off"
    if isinstance(value, bool):
        return "On" if value else "Off"
    if value is None:
        return "—"
    if isinstance(value, list):
        return ", ".join(str(v) for v in value) if value else "empty"
    if isinstance(value, int | float | Decimal):
        return _fmt_number(float(value), f.unit)
    text = str(value)
    if not text:
        return "empty"
    if f.value_type == "time":
        return text[:5]
    return f"`{text}`"


# --- location ---------------------------------------------------------------------


def _where(f: Feature) -> str:
    if f.backing == "system_settings":
        return "Settings → Features"
    if f.backing == "env_only":
        return "Environment variable, then restart"
    if f.backing == "informational":
        return "Not switchable"
    if f.scope == "singleton":
        page = PAGES.get(f.deep_link, "")
        return f"Settings → Features, or the {page} page" if page else "Settings → Features"
    if not f.write_path:
        return "Read-only"
    page = PAGES.get(f.deep_link, "")
    noun = SCOPE_SINGULAR.get(f.scope, "item")
    if page:
        return f"{page} page, per {noun}"
    return f"`{f.write_path}` (no control on the Features page)"


# --- markdown helpers -------------------------------------------------------------


def _cell(text: str) -> str:
    return " ".join(text.split()).replace("|", "\\|")


def _what(f: Feature) -> str:
    notes: list[str] = []
    if f.provider_only:
        notes.append(
            {"claude": "Claude only", "openai": "OpenAI only", "local": "Local only"}[
                f.provider_only
            ]
        )
    if f.requires_connection:
        notes.append(f"needs a connected {CONNECTIONS[f.requires_connection]}")
    if f.requires:
        labels = [g.label for g in FEATURES if g.key in f.requires]
        notes.append("needs " + " and ".join(labels))
    if f.retroactive:
        notes.append("**retroactive**")
    tail = f" _({'; '.join(notes)})_" if notes else ""
    return f"**{_cell(f.label)}** — {_cell(f.summary)}{tail}"


def _rows(features: list[Feature]) -> list[str]:
    out = ["| What it does | Where to change it | Default | Costs money |", "|---|---|---|---|"]
    for f in features:
        out.append(
            f"| {_what(f)} | {_cell(_where(f))} | {_fmt_default(f, _default_of(f))} "
            f"| {'Yes' if f.costs_money else 'No'} |"
        )
    return out


def _sorted(features: list[Feature]) -> list[Feature]:
    return sorted(features, key=lambda f: (f.order, f.key))


# --- document ---------------------------------------------------------------------


def _posture() -> dict[str, int]:
    """Row counts behind the headline, split two ways: app-wide versus per-object, and
    on/off versus a row that holds a value instead of a state.

    Counted rather than asserted. "One app-wide capability ships off" is a claim about
    the registry, so a second one appearing has to change the sentence, not falsify it.
    """
    counts = dict.fromkeys(
        ("global_on", "global_off", "global_value", "object_on", "object_off", "object_value"), 0
    )
    for f in FEATURES:
        scope = "object" if f.scope.startswith("per_") else "global"
        rendered = _fmt_default(f, _default_of(f))
        state = {"On": "on", "Off": "off"}.get(rendered, "value")
        counts[f"{scope}_{state}"] += 1
    return counts


def _object_off_breakdown() -> list[str]:
    """One bullet per object kind that starts life with something switched off, naming
    every row. Derived from the registry so the enumeration cannot drift from the
    tables below it."""
    by_scope: dict[str, list[str]] = {}
    for f in FEATURES:
        if f.scope.startswith("per_") and _fmt_default(f, _default_of(f)) == "Off":
            by_scope.setdefault(f.scope, []).append(f.label)
    return [
        f"- **{len(by_scope[scope])} per {SCOPE_SINGULAR[scope]}** — "
        f"{', '.join(sorted(by_scope[scope]))}."
        for scope in sorted(by_scope, key=lambda s: (-len(by_scope[s]), s))
    ]


def _header(total: int, money: int) -> list[str]:
    n = _posture()
    app_wide = n["global_on"] + n["global_off"] + n["global_value"]
    per_object = n["object_on"] + n["object_off"] + n["object_value"]
    return [
        "# What can be toggled, and where",
        "",
        f"{total} switches. {app_wide} are app-wide. The other {per_object} are the "
        "value one new profile, provider, preset, schedule, trigger, thesis or lesson "
        "starts with, so the same row reads differently for every object you own.",
        "",
        f"**App-wide capabilities: {n['global_on']} of the "
        f"{n['global_on'] + n['global_off']} that are simply on or off ship on.** "
        "Dividend-adjusted return math is the single exception, and the "
        "[reason](#the-one-app-wide-capability-that-ships-off) is that it rewrites "
        "numbers "
        f"already recorded. The remaining {n['global_value']} app-wide rows are not "
        "on/off at all: they hold a value — a retention window, a spend ceiling, a "
        "model id — or state a constant.",
        "",
        f"**Per-object defaults: {n['object_on']} ship on and {n['object_off']} ship "
        "off.** An off here is a starting value, not a capability held back from you:",
        "",
        *_object_off_breakdown(),
        "",
        f"The other {n['object_value']} per-object rows hold a value rather than a "
        "state. Each row below names where it is set, including the ones that are "
        "read-only markers rather than switches.",
        "",
        "**Settings → Features** renders from this same registry, in the same groups, "
        "with the same copy. App-wide switches are edited in place there, bar the "
        "[rows that stay read-only](#not-switchable-from-the-ui-and-why); a switch that lives "
        "on an object shows how many objects currently have it on and links to the "
        "page that owns it.",
        "",
        f"{money} switches bill a model provider when they are on; they are collected "
        "under [Toggles that spend money](#toggles-that-spend-money) as well as listed in "
        "their own group.",
        "",
        "## How to read the tables",
        "",
        "- **Where to change it** names the surface that owns the value. "
        "`Settings → Features` means the switch is editable in place on that page.",
        "- **Default** is what a fresh install runs with. Global switches store nothing "
        "until you change one: an empty override inherits the default, so clearing a "
        "value is how you get back to the column below.",
        "- **Costs money** marks a switch whose purpose is to add provider calls. It is "
        "not the whole cost surface — richer capture sections, more tool rounds and more "
        "watched tickers all change the size of calls you already pay for.",
        "",
    ]


def _group_sections() -> list[str]:
    out: list[str] = []
    for group in sorted(GROUPS, key=lambda g: g.order):
        rows = _sorted([f for f in FEATURES if f.group == group.key])
        out += [f"## {group.label}", "", group.blurb, "", *_rows(rows), ""]
    return out


def _money_section() -> list[str]:
    out = [
        "## Toggles that spend money",
        "",
        "Each of these adds provider calls when it is on. The per-provider daily and "
        "monthly caps bound all of them, and the autonomous daily cap bounds the "
        "unattended ones on top of that; a run over a cap is skipped and recorded as "
        "skipped rather than failing silently.",
        "",
        "| Switch | Where to change it | Default | What it costs |",
        "|---|---|---|---|",
    ]
    for f in _sorted([f for f in FEATURES if f.costs_money]):
        out.append(
            f"| **{_cell(f.label)}** | {_cell(_where(f))} | "
            f"{_fmt_default(f, _default_of(f))} | {_cell(f.cost_note)} |"
        )
    return [*out, ""]


def _off_section() -> list[str]:
    off = [f for f in FEATURES if f.retroactive]
    out = ["## The one app-wide capability that ships off", ""]
    for f in off:
        out += [
            f"**{_cell(f.label)}** (`{setting_name(f)}`) — {_cell(f.summary)} "
            f"Change it in {_cell(_where(f))}.",
            "",
            _cell(f.help),
            "",
            "One recorded history would then carry two methodologies, which is what "
            "makes this a decision to take once rather than a switch to flip and "
            "unflip. Everything else in this document changes what happens next; this "
            "one changes what the record says about what already happened.",
            "",
        ]
    return out


def _not_switchable_section() -> list[str]:
    out = [
        "## Not switchable from the UI, and why",
        "",
        "These appear on the Features page as read-only rows with their reason, rather "
        "than going quietly missing.",
        "",
        "| Knob | Default | Why it stays out of the UI |",
        "|---|---|---|",
    ]
    for f in _sorted([f for f in FEATURES if f.backing == "env_only"]):
        out.append(
            f"| **{_cell(f.label)}** (`{f.env_var}`) | {_fmt_default(f, _default_of(f))} "
            f"| {_cell(f.env_only_reason)} |"
        )
    out += ["", "Two more rows are stated constants rather than switches:", ""]
    for f in _sorted([f for f in FEATURES if f.backing == "informational"]):
        out.append(f"- **{_cell(f.label)}** — {_cell(f.env_only_reason)}")
    out += [
        "",
        "### Deliberately excluded",
        "",
        "- `DJANGO_DEBUG` and `MOCK_EXTERNAL` have no UI switch and a drift gate keeps "
        "them out. A UI-settable `MOCK_EXTERNAL` would make every provider return canned "
        "fixtures while the app looked normal.",
        "- Credentials and connection settings are not features. **Settings → "
        "Connections** owns them: " + ", ".join(f"`{v}`" for v in EXCLUDED_CONNECTION_VARS) + ".",
        "",
    ]
    return out


def _env_appendix() -> list[str]:
    rows = _sorted([f for f in FEATURES if setting_name(f)])
    out = [
        "## Appendix: environment names",
        "",
        "Every global switch also has an environment variable, which sets the default a "
        "cleared override falls back to. A value set in Settings → Features wins over "
        "the environment.",
        "",
        "| Switch | Environment variable | Stored as |",
        "|---|---|---|",
    ]
    stored = {
        "system_settings": "`SystemSettings` override, or the environment default",
        "env_only": "environment only",
    }
    for f in sorted(rows, key=lambda f: setting_name(f)):
        out.append(
            f"| {_cell(f.label)} | `{setting_name(f)}` | "
            f"{stored.get(f.backing, 'environment default')} |"
        )
    return [*out, ""]


def _footer() -> list[str]:
    return [
        "---",
        "",
        "Generated from `backend/apps/core/features.py` by "
        "`manage.py toggles_doc`. Add a toggle to the registry in the same change that "
        "adds the capability: `apps/core/tests/test_feature_registry.py` fails when a "
        "switch has no row, and `apps/core/tests/test_toggles_doc.py` fails when this "
        "file no longer matches the registry.",
        "",
    ]


def render() -> str:
    """The full Markdown document. Deterministic: no database, no environment."""
    lines: list[str] = [
        *_header(len(FEATURES), sum(1 for f in FEATURES if f.costs_money)),
        *_group_sections(),
        *_money_section(),
        *_off_section(),
        *_not_switchable_section(),
        *_env_appendix(),
        *_footer(),
    ]
    return "\n".join(lines).rstrip("\n") + "\n"


class Command(BaseCommand):
    help = "Render the Features registry to Markdown (docs/toggles.md)."

    def add_arguments(self, parser) -> None:
        parser.add_argument(
            "--write",
            action="store_true",
            help="Write docs/toggles.md in place instead of printing (needs the docs "
            "directory; it is not mounted in the web container).",
        )
        parser.add_argument(
            "--check",
            action="store_true",
            help="Exit non-zero when docs/toggles.md differs from the rendered registry.",
        )

    def handle(self, *args, **options) -> None:
        text = render()
        if options["check"]:
            if not DOC_PATH.exists():
                raise CommandError(f"{DOC_PATH} does not exist — run without --check and redirect")
            if DOC_PATH.read_text() != text:
                raise CommandError(
                    f"{DOC_PATH} is stale — regenerate it: "
                    "docker compose exec -T web uv run python manage.py toggles_doc "
                    "> docs/toggles.md"
                )
            self.stdout.write("docs/toggles.md matches the registry")
            return
        if options["write"]:
            if not DOC_PATH.parent.is_dir():
                raise CommandError(
                    f"{DOC_PATH.parent} is not mounted here — print and redirect instead: "
                    "docker compose exec -T web uv run python manage.py toggles_doc "
                    "> docs/toggles.md"
                )
            DOC_PATH.write_text(text)
            self.stdout.write(f"wrote {DOC_PATH}")
            return
        self.stdout.write(text, ending="")
