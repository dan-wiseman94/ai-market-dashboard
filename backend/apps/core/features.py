"""Authoritative metadata registry for everything the user can switch on or off.

This module is **pure metadata**: frozen dataclass rows describing each toggle's copy,
grouping, storage pointer and honesty flags. It holds no values and reads no database.
``apps.core.feature_views`` resolves the live values; the drift gates in
``apps/core/tests/test_feature_registry.py`` keep it in lockstep with the code.

No module-level ``from apps.<other>`` imports — ``apps/core/tests/test_layering.py``
walks this package and fails on them. Per-object storage is therefore declared as a
**string** model label ("observer.ObserverSchedule") and resolved with
``django.apps.apps.get_model()`` at request time. ``apps.core.runtime_config`` is the
same app, so importing ``_SPEC`` here is allowed (and is how the hard defaults stay
single-sourced: a ``system_settings`` row never repeats its default).

EXCLUSION RULE — do not let the Features page become a .env editor. A row belongs here
only if flipping it **changes app behaviour**. Connection strings, filesystem paths,
identities and secrets never appear: DJANGO_SECRET_KEY, DJANGO_ALLOWED_HOSTS,
POSTGRES_*, REDIS_URL, CELERY_*, ENCRYPTION_SALT_PATH, SNAPSHOT_IMAGE_DIR,
RENDER_BASE_URL, FRONTEND_BASE_URL, SCHWAB_*, TRADINGVIEW_MCP_URL/_CALLBACK_URL,
SEC_EDGAR_USER_AGENT, SENTRY_DSN/_ENVIRONMENT/_TRACES_SAMPLE_RATE, MCP_AUTH_TOKEN and
every *_API_KEY — Settings → Connections owns those.

``DJANGO_DEBUG`` and ``MOCK_EXTERNAL`` are excluded outright and a drift gate keeps them
out forever: a UI switch for either is a security/tests regression (MOCK_EXTERNAL would
make every provider silently return canned fixtures).

Four knobs appear READ-ONLY with a stated reason rather than going silently missing —
see the ``env_only`` rows and their ``env_only_reason``.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

from apps.core.runtime_config import _SPEC

Scope = Literal[
    "global",
    "singleton",
    "per_provider",
    "per_profile",
    "per_preset",
    "per_schedule",
    "per_trigger",
    "per_thesis",
    "per_lesson",
    "per_capture",
]
Backing = Literal["system_settings", "model_field", "env_only", "informational"]
VType = Literal["bool", "int", "float", "str", "choice", "multi", "time", "fk"]

# Plural noun used by the per-object rollup copy ("on for 4 of 13 profiles").
SCOPE_NOUN: dict[str, str] = {
    "per_provider": "providers",
    "per_profile": "profiles",
    "per_preset": "presets",
    "per_schedule": "schedules",
    "per_trigger": "triggers",
    "per_thesis": "theses",
    "per_lesson": "lessons",
    "per_capture": "profiles",
}


@dataclass(frozen=True)
class Feature:
    """One switchable thing. Copy lives here, never in the TSX."""

    key: str
    label: str
    summary: str  # one line, the row subtitle. Gated non-empty.
    help: str  # expander body: what ON does, what OFF costs you. Gated non-empty.
    group: str
    order: int
    scope: Scope
    backing: Backing
    value_type: VType = "bool"
    # backing="system_settings": the runtime_config._SPEC / SystemSettings field name.
    settings_field: str = ""
    # backing="model_field": "observer.ObserverSchedule" + the field on it.
    model_label: str = ""
    model_field: str = ""
    # Where a singleton/per-object row is actually written (the page never invents one).
    write_path: str = ""
    env_var: str = ""
    env_only_reason: str = ""  # REQUIRED when backing="env_only"
    # Declared ONLY for non-system_settings rows; system_settings rows read _SPEC.
    shipped_default: object = None
    choices: tuple[tuple[str, str], ...] = ()
    min_value: float | None = None
    max_value: float | None = None
    max_length: int = 0
    unit: str = ""  # "days" | "seconds" | "USD" | "tokens" | ""
    costs_money: bool = False
    cost_note: str = ""  # REQUIRED when costs_money
    retroactive: bool = False  # flipping it restates numbers already recorded
    requires: tuple[str, ...] = ()  # other feature keys
    requires_connection: str = ""  # "tradingview"
    provider_only: str = ""  # "claude" | "openai" | "local"
    deep_link: str = ""  # SPA route; "" means "no UI surface exists" (honest, not a bug)


@dataclass(frozen=True)
class FeatureGroup:
    key: str
    label: str
    blurb: str
    order: int


GROUPS: list[FeatureGroup] = [
    FeatureGroup(
        "ai",
        "AI capabilities",
        "What the models are allowed to do, and which one answers.",
        1,
    ),
    FeatureGroup(
        "observation",
        "Observation & automation",
        "Everything that runs without you asking: schedules, triggers, the briefing.",
        2,
    ),
    FeatureGroup(
        "spend",
        "Autonomous spend",
        "Background work that bills a provider, and the ceilings that bound it.",
        3,
    ),
    FeatureGroup(
        "data",
        "Data & retention",
        "What each capture collects and how long it is kept.",
        4,
    ),
    FeatureGroup(
        "methodology",
        "Methodology",
        "How recorded performance is computed. Changing it rewrites history.",
        5,
    ),
    FeatureGroup(
        "danger",
        "Danger zone",
        "One switch, and it ships on: the UI may overwrite the live database from a "
        "backup. Turn it off on any machine other people can reach, which leaves the "
        "command-line restore as the only path.",
        6,
    ),
]

_MONEY_INVESTIGATE = (
    "A bounded tool-using investigation costs several model calls per fire instead of "
    "one, capped by the investigation tool-round limit and the autonomous daily cap."
)

# --- helper: compact row builders ------------------------------------------------


def _profile(
    key: str,
    fieldname: str,
    label: str,
    summary: str,
    helptext: str,
    order: int,
    *,
    value_type: VType = "bool",
    group: str = "ai",
    provider_only: str = "",
    costs_money: bool = False,
    cost_note: str = "",
    choices: tuple[tuple[str, str], ...] = (),
) -> Feature:
    return Feature(
        key=key,
        label=label,
        summary=summary,
        help=helptext,
        group=group,
        order=order,
        scope="per_profile",
        backing="model_field",
        value_type=value_type,
        model_label="profiles.TradingProfile",
        model_field=fieldname,
        write_path="/api/profiles/",
        deep_link="/profiles",
        provider_only=provider_only,
        costs_money=costs_money,
        cost_note=cost_note,
        choices=choices,
    )


def _schedule(
    key: str,
    fieldname: str,
    label: str,
    summary: str,
    helptext: str,
    order: int,
    *,
    value_type: VType = "bool",
    provider_only: str = "",
    costs_money: bool = False,
    cost_note: str = "",
    requires: tuple[str, ...] = (),
    choices: tuple[tuple[str, str], ...] = (),
) -> Feature:
    return Feature(
        key=key,
        label=label,
        summary=summary,
        help=helptext,
        group="observation",
        order=order,
        scope="per_schedule",
        backing="model_field",
        value_type=value_type,
        model_label="observer.ObserverSchedule",
        model_field=fieldname,
        write_path="/api/observer/schedules/",
        deep_link="/schedules",
        provider_only=provider_only,
        costs_money=costs_money,
        cost_note=cost_note,
        requires=requires,
        choices=choices,
    )


def _briefing(
    key: str,
    fieldname: str,
    label: str,
    summary: str,
    helptext: str,
    order: int,
    *,
    value_type: VType = "bool",
    shipped_default: object = None,
    backing: Backing = "model_field",
    env_only_reason: str = "",
    costs_money: bool = False,
    cost_note: str = "",
    unit: str = "",
    min_value: float | None = None,
) -> Feature:
    return Feature(
        key=key,
        label=label,
        summary=summary,
        help=helptext,
        group="observation",
        order=order,
        scope="singleton",
        backing=backing,
        value_type=value_type,
        model_label="observer.BriefingConfig",
        model_field=fieldname,
        write_path="" if backing == "informational" else "/api/briefings/config/",
        env_only_reason=env_only_reason,
        shipped_default=shipped_default,
        costs_money=costs_money,
        cost_note=cost_note,
        unit=unit,
        min_value=min_value,
        deep_link="/briefing",
    )


def _section(kind: str, label: str, helptext: str, order: int) -> Feature:
    return Feature(
        key=f"section.{kind}",
        label=label,
        summary=f"Include the {label.lower()} section in a capture's payload.",
        help=helptext,
        group="data",
        order=order,
        scope="per_capture",
        backing="model_field",
        value_type="bool",
        model_label="profiles.TradingProfile",
        model_field="default_includes",
        write_path="/api/profiles/",
        deep_link="/profiles",
    )


def _retention(fieldname: str, label: str, what: str, order: int) -> Feature:
    return Feature(
        key=f"retention.{fieldname.removeprefix('retention_').removesuffix('_days')}",
        label=label,
        summary=f"How long {what} are kept before the nightly purge.",
        help=(
            f"The nightly housekeeping task deletes {what} older than this many days. "
            "Clearing the override inherits the shipped window; there is no 'keep "
            "forever' value — set a large number instead."
        ),
        group="data",
        order=order,
        scope="global",
        backing="system_settings",
        value_type="int",
        settings_field=fieldname,
        write_path="/api/settings/",
        env_var=dict((f, s) for f, s, _ in _SPEC)[fieldname],
        min_value=1,
        unit="days",
    )


# --- the registry ----------------------------------------------------------------

FEATURES: list[Feature] = [
    # ============================ AI capabilities ============================
    Feature(
        key="ai.failover",
        label="Cross-provider failover",
        summary="Retry a failed run once on a secondary provider.",
        help=(
            "When the primary provider errors **before emitting a single token**, the "
            "run is retried once on a secondary. Never after a token has streamed — "
            "that would duplicate the answer and the bill. The toggle alone is enough: "
            "with no failover provider named below, the retry goes to the first other "
            "enabled provider that has a usable key, a default model and room under "
            "its own caps."
        ),
        group="ai",
        order=1,
        scope="global",
        backing="system_settings",
        settings_field="ai_failover_enabled",
        write_path="/api/settings/",
        env_var="AI_FAILOVER_ENABLED",
    ),
    Feature(
        key="ai.failover_provider",
        label="Failover provider",
        summary="Which provider catches a failed run. Empty picks one automatically.",
        help=(
            "Pins the secondary the failover retry goes to. Empty does not disarm "
            "failover: the retry then falls to the first other enabled provider that "
            "can actually run, oldest row first. Name one here to choose that pick "
            "rather than accept it. Either way the provider needs a usable key, a "
            "default model and headroom under its own caps, and it is skipped when it "
            "is the provider that just failed."
        ),
        group="ai",
        order=2,
        scope="global",
        backing="system_settings",
        value_type="choice",
        settings_field="ai_failover_provider",
        write_path="/api/settings/",
        env_var="AI_FAILOVER_PROVIDER",
        choices=(
            ("", "None"),
            ("claude", "Anthropic Claude"),
            ("openai", "OpenAI"),
            ("local", "Local (OpenAI-compatible)"),
        ),
        max_length=32,
        requires=("ai.failover",),
    ),
    Feature(
        key="ai.calibration_routing",
        label="Route by measured calibration",
        summary="The fallback tier picks the best-measured model from recent evals.",
        help=(
            "Only the **fallback** tier is affected: a per-send override or a profile's "
            "pinned model still wins. Below the minimum scored-call floor the "
            "measurement is treated as too thin and the ordinary default is used, so "
            "this no-ops on a fresh install."
        ),
        group="ai",
        order=3,
        scope="global",
        backing="system_settings",
        settings_field="ai_calibration_routing_enabled",
        write_path="/api/settings/",
        env_var="AI_CALIBRATION_ROUTING_ENABLED",
    ),
    Feature(
        key="ai.calibration_routing_min_scored",
        label="Minimum scored calls",
        summary="Below this many scored eval calls, a measurement is ignored.",
        help=(
            "Guards against routing the whole app onto a model that happens to have one "
            "lucky eval. Raising it makes routing more conservative."
        ),
        group="ai",
        order=4,
        scope="global",
        backing="system_settings",
        value_type="int",
        settings_field="ai_calibration_routing_min_scored",
        write_path="/api/settings/",
        env_var="AI_CALIBRATION_ROUTING_MIN_SCORED",
        min_value=0,
        unit="calls",
        requires=("ai.calibration_routing",),
    ),
    Feature(
        key="ai.calibration_routing_max_age_days",
        label="Maximum eval age",
        summary="Evals older than this no longer pin routing.",
        help=(
            "Model behaviour drifts between vendor releases. An eval older than this "
            "window stops counting toward the routing decision."
        ),
        group="ai",
        order=5,
        scope="global",
        backing="system_settings",
        value_type="int",
        settings_field="ai_calibration_routing_max_age_days",
        write_path="/api/settings/",
        env_var="AI_CALIBRATION_ROUTING_MAX_AGE_DAYS",
        min_value=1,
        unit="days",
        requires=("ai.calibration_routing",),
    ),
    Feature(
        key="ai.tradingview_tools",
        label="TradingView tools for the AI",
        summary="Expose the read-only tv_* MCP tools to tool-enabled runs.",
        help=(
            "Adds the 25-name read-only TradingView allowlist to every tool-enabled "
            "profile run (roughly 3-6k extra prompt tokens per run). Requires a "
            "connected TradingView account; with none connected the tools are simply "
            "not offered."
        ),
        group="ai",
        order=6,
        scope="global",
        backing="system_settings",
        settings_field="tradingview_tools_enabled",
        write_path="/api/settings/",
        env_var="TRADINGVIEW_TOOLS_ENABLED",
        requires_connection="tradingview",
    ),
    Feature(
        key="ai.chat_max_tool_iterations",
        label="Chat tool rounds",
        summary="Ceiling on tool calls in one ordinary (non-investigation) run.",
        help=(
            "A hard stop on the tool loop so a confused model cannot spin. 0 would mean "
            "unbounded and is rejected — clear the override to inherit the default."
        ),
        group="ai",
        order=7,
        scope="global",
        backing="system_settings",
        value_type="int",
        settings_field="ai_chat_max_tool_iterations",
        write_path="/api/settings/",
        env_var="AI_CHAT_MAX_TOOL_ITERATIONS",
        min_value=1,
        unit="rounds",
    ),
    Feature(
        key="ai.provider_max_retries",
        label="Provider retry attempts",
        summary="SDK-level retries on a transport error. Environment only.",
        help=(
            "Read at provider construction, which can happen inside the async streaming "
            "loop where a database read would raise SynchronousOnlyOperation. It stays "
            "an environment variable on purpose."
        ),
        group="ai",
        order=8,
        scope="global",
        backing="env_only",
        value_type="int",
        env_var="AI_PROVIDER_MAX_RETRIES",
        env_only_reason=(
            "Read at provider __init__, which runs inside the async streaming loop — a "
            "database-backed override there would raise SynchronousOnlyOperation. Set "
            "AI_PROVIDER_MAX_RETRIES in the environment and restart."
        ),
        shipped_default=2,
        unit="attempts",
    ),
    Feature(
        key="ai.provider_timeout_seconds",
        label="Provider request timeout",
        summary="How long a provider call may hang before it is abandoned. Environment only.",
        help=(
            "Same constraint as the retry count: it is consumed when the provider client "
            "is constructed, on the async path, so it cannot be a database override."
        ),
        group="ai",
        order=9,
        scope="global",
        backing="env_only",
        value_type="float",
        env_var="AI_PROVIDER_TIMEOUT_SECONDS",
        env_only_reason=(
            "Read at provider __init__ on the async streaming path — a database read "
            "there would raise SynchronousOnlyOperation. Set "
            "AI_PROVIDER_TIMEOUT_SECONDS in the environment and restart."
        ),
        shipped_default=60.0,
        unit="seconds",
    ),
    _profile(
        "profile.enable_tools",
        "enable_tools",
        "AI tools (function calling)",
        "Let this profile's runs call quote, OHLC, news, chain and indicator tools.",
        "Off, the model answers only from the captured payload. On, it can fetch what "
        "the payload omitted — more accurate, a little slower, and each tool round is "
        "another billed model call.",
        10,
    ),
    _profile(
        "profile.enable_thinking",
        "enable_thinking",
        "Extended thinking",
        "Give Claude a private reasoning budget before it answers.",
        "Claude-only. Thinking tokens are billed as output, so the budget below is a "
        "direct cost lever.",
        11,
        provider_only="claude",
        costs_money=True,
        cost_note="Thinking tokens bill as output tokens on every run of this profile.",
    ),
    _profile(
        "profile.thinking_budget",
        "thinking_budget",
        "Thinking budget",
        "Token ceiling for extended thinking on this profile.",
        "Only consumed when extended thinking is on. Billed as output tokens.",
        12,
        value_type="int",
        provider_only="claude",
    ),
    _profile(
        "profile.effort",
        "effort",
        "Reasoning effort",
        "How hard the model works on this profile's runs.",
        "Claude-only. Higher effort spends more tokens for a more considered answer, "
        "and a level the chosen model does not expose steps down to the nearest one it "
        "does. The request builder drops it for every other provider, so a profile "
        "pointed at OpenAI or a local endpoint never sends it.",
        13,
        value_type="choice",
        provider_only="claude",
        choices=(
            ("low", "Low"),
            ("medium", "Medium"),
            ("high", "High"),
            ("xhigh", "Extra high"),
            ("max", "Max"),
        ),
    ),
    _profile(
        "profile.enable_memory",
        "enable_memory",
        "Memory tool",
        "A per-profile scratchpad the model can write to and read back.",
        "Claude-only. Gives the profile continuity across runs; off, every run starts cold.",
        14,
        provider_only="claude",
    ),
    _profile(
        "profile.enable_coach",
        "enable_coach",
        "Decision Coach context",
        "Inject prior theses, your track record and recalled notes into the prompt.",
        "Off, the system prompt is just the trading style — cheaper and more neutral. "
        "On, the model sees your calibration and past mistakes, which is what makes the "
        "observations personal.",
        15,
    ),
    _profile(
        "profile.active",
        "active",
        "Profile active",
        "Whether the profile is offered when capturing.",
        "Deactivating hides a profile from the pickers without deleting it or its history.",
        16,
    ),
    _profile(
        "profile.default_provider",
        "default_provider",
        "Default provider",
        "Which provider this profile's runs go to by default.",
        "A per-send override still wins. A model id belonging to a different provider "
        "is ignored with a warning and the provider's own default is used.",
        17,
        value_type="str",
    ),
    _profile(
        "profile.default_model",
        "default_model",
        "Default model",
        "The model id this profile pins.",
        "Must be a catalog row of the profile's provider. An unknown id falls back to a "
        "40k payload budget and is billed at the provider's priciest row.",
        18,
        value_type="str",
    ),
    _profile(
        "profile.default_includes",
        "default_includes",
        "Default capture sections",
        "Which snapshot sections a capture with this profile collects.",
        "The per-section rows under Data & retention show how many profiles currently "
        "include each kind.",
        19,
        value_type="multi",
    ),
    Feature(
        key="provider.enabled",
        label="Provider enabled",
        summary="Whether a configured provider may be selected at all.",
        help=(
            "Disabling a provider takes it out of routing, failover and the compare "
            "fan-out without deleting its key."
        ),
        group="ai",
        order=20,
        scope="per_provider",
        backing="model_field",
        model_label="secrets_app.ProviderConfig",
        model_field="enabled",
        write_path="/api/schwab/providers/",
        deep_link="/settings",
    ),
    Feature(
        key="provider.supports_vision",
        label="Provider accepts images",
        summary="Whether chart images may be attached to this provider's runs.",
        help=(
            "Turn off for an endpoint that has no vision head: the request builder then "
            "leaves the snapshot's chart images out and the run posts a notice in the "
            "thread saying so, instead of the provider rejecting the whole call."
        ),
        group="ai",
        order=21,
        scope="per_provider",
        backing="model_field",
        model_label="secrets_app.ProviderConfig",
        model_field="supports_vision",
        write_path="/api/schwab/providers/",
        deep_link="/settings",
    ),
    Feature(
        key="provider.supports_tools",
        label="Provider accepts tools",
        summary="Gates tool use for OpenAI and local endpoints.",
        help=(
            "Tool use is opted into per profile, and for OpenAI/local it is additionally "
            "gated here — many local servers advertise an OpenAI-compatible API without "
            "implementing tool calls."
        ),
        group="ai",
        order=22,
        scope="per_provider",
        backing="model_field",
        model_label="secrets_app.ProviderConfig",
        model_field="supports_tools",
        write_path="/api/schwab/providers/",
        deep_link="/settings",
    ),
    Feature(
        key="preset.active",
        label="Preset offered in the composer",
        summary="Whether a capture preset appears in the objective picker.",
        help=(
            "Deactivating hides a preset without deleting it. The composer's objective "
            "picker lists only active presets; the checkbox that sets this is on the "
            "Profiles page, beside the preset list."
        ),
        group="ai",
        order=24,
        scope="per_preset",
        backing="model_field",
        model_label="profiles.AgentPreset",
        model_field="active",
        write_path="/api/presets/",
        deep_link="/profiles",
    ),
    Feature(
        key="preset.builtin",
        label="Built-in preset",
        summary="Marks a preset that shipped with the app. Read-only by design.",
        help=(
            "A data migration seeds these presets and sets the flag; the API rejects "
            "any attempt to change it, which is what makes this row a status marker "
            "rather than a switch. It records provenance, not protection: a built-in "
            "preset's name, description, objective text and active state are editable "
            "like any other, and it can be deleted. The seeding migration runs once "
            "per database, so a deleted built-in does not come back — duplicate one "
            "instead when you want a variant and the original kept."
        ),
        group="ai",
        order=25,
        scope="per_preset",
        backing="model_field",
        model_label="profiles.AgentPreset",
        model_field="builtin",
        write_path="",
        deep_link="/profiles",
    ),
    Feature(
        key="lesson.pinned",
        label="Lesson pinned",
        summary="A pinned lesson reaches the Coach regardless of how thin its evidence is.",
        help=(
            "Hand-written lessons carry no post-mortem evidence, so pinning is what "
            "makes them visible to the Coach at all — the Lessons page creates every "
            "hand-written lesson pinned for that reason. Pin or unpin any lesson from "
            "its row there."
        ),
        group="ai",
        order=26,
        scope="per_lesson",
        backing="model_field",
        model_label="thesis.Lesson",
        model_field="pinned",
        write_path="/api/lessons/",
        deep_link="/lessons",
    ),
    Feature(
        key="lesson.muted",
        label="Lesson muted",
        summary="A muted lesson is withheld from the Coach.",
        help=(
            "Use it to silence a distilled lesson that turned out to be noise. A muted "
            "lesson still sits in the clustering pool, so later post-mortems saying "
            "the same thing merge into it instead of rebuilding it — which is what "
            "deleting the cluster would invite. Mute and unmute from the lesson's row "
            "on the Lessons page."
        ),
        group="ai",
        order=27,
        scope="per_lesson",
        backing="model_field",
        model_label="thesis.Lesson",
        model_field="muted",
        write_path="/api/lessons/",
        deep_link="/lessons",
    ),
    # ======================= Observation & automation ========================
    Feature(
        key="observer.response_cache",
        label="Observer response cache",
        summary="Reuse a recent observation when the prompt is byte-identical.",
        help=(
            "A plain scheduled fire whose assembled prompt matches a recent one exactly "
            "reuses that answer instead of paying for another call. Live quote lines "
            "make exact matches rare, so the saving is real but modest. Plain fires "
            "only — structured, batch and consensus fires always call the model."
        ),
        group="observation",
        order=1,
        scope="global",
        backing="system_settings",
        settings_field="observer_response_cache_enabled",
        write_path="/api/settings/",
        env_var="OBSERVER_RESPONSE_CACHE_ENABLED",
    ),
    Feature(
        key="observer.response_cache_ttl",
        label="Response cache lifetime",
        summary="How long a cached observation stays reusable.",
        help=(
            "Longer saves more money and risks answering from a staler market. Only "
            "consulted while the response cache is on."
        ),
        group="observation",
        order=2,
        scope="global",
        backing="system_settings",
        value_type="int",
        settings_field="observer_response_cache_ttl_seconds",
        write_path="/api/settings/",
        env_var="OBSERVER_RESPONSE_CACHE_TTL_SECONDS",
        min_value=0,
        unit="seconds",
        requires=("observer.response_cache",),
    ),
    Feature(
        key="analytics.calibration_drift_sentinel",
        label="Calibration drift alerts",
        summary="Notify when a model becomes measurably over- or under-confident.",
        help=(
            "A daily pass over stored eval runs that raises one notification per drift "
            "episode. It reads already-recorded data — no model is called, so it costs "
            "nothing."
        ),
        group="observation",
        order=3,
        scope="global",
        backing="system_settings",
        settings_field="calibration_drift_sentinel_enabled",
        write_path="/api/settings/",
        env_var="CALIBRATION_DRIFT_SENTINEL_ENABLED",
    ),
    Feature(
        key="strategy.regime_narrative",
        label="Regime narrative",
        summary="Layer an AI paragraph onto each market-regime reading.",
        help=(
            "Off keeps every computed regime axis and drops only the prose. The numbers "
            "never depend on the model."
        ),
        group="observation",
        order=4,
        scope="global",
        backing="system_settings",
        settings_field="regime_narrative_enabled",
        write_path="/api/settings/",
        env_var="REGIME_NARRATIVE_ENABLED",
        costs_money=True,
        cost_note="One short model call per regime refresh.",
    ),
    Feature(
        key="book.narrative",
        label="Book narrative",
        summary="Layer an AI paragraph onto the daily whole-book risk reading.",
        help=(
            "Off keeps the computed exposure and concentration numbers and drops only "
            "the paragraph."
        ),
        group="observation",
        order=5,
        scope="global",
        backing="system_settings",
        settings_field="book_narrative_enabled",
        write_path="/api/settings/",
        env_var="BOOK_NARRATIVE_ENABLED",
        costs_money=True,
        cost_note="One short model call per daily book snapshot.",
    ),
    Feature(
        key="observer.beat_timezone",
        label="Schedule timezone",
        summary="The timezone cron expressions are evaluated in. Environment only.",
        help=(
            "Deliberately not UI-editable. The value is copied onto each schedule's beat "
            "row when that schedule is saved, so changing it later would leave every "
            "existing schedule on the old timezone while the UI claimed otherwise — a "
            "schedule reading '09:30 ET' would keep firing at 09:30 UTC."
        ),
        group="observation",
        order=6,
        scope="global",
        backing="env_only",
        value_type="str",
        env_var="OBSERVER_BEAT_TIMEZONE",
        env_only_reason=(
            "Stamped onto each schedule's beat row at save time. Changing it in the "
            "database would silently leave existing schedules on the old timezone. Set "
            "OBSERVER_BEAT_TIMEZONE in the environment before creating schedules."
        ),
        shipped_default="UTC",
    ),
    Feature(
        key="triggers.tick_seconds",
        label="Trigger evaluation interval",
        summary="How often armed triggers are evaluated. Environment only.",
        help=(
            "The live value is a beat interval row written once, at first migration. "
            "Editing the environment variable afterwards does nothing, so showing it as "
            "editable would be a lie — change the interval on the beat schedule itself."
        ),
        group="observation",
        order=7,
        scope="global",
        backing="env_only",
        value_type="int",
        env_var="TRIGGER_TICK_SECONDS",
        env_only_reason=(
            "Consumed once by a migration to create the beat interval row. The live "
            "value lives in that row, so editing the environment variable later has no "
            "effect."
        ),
        shipped_default=10,
        unit="seconds",
    ),
    _schedule(
        "schedule.enabled",
        "enabled",
        "Schedule armed",
        "Whether a scheduled observation fires at all.",
        "Disarming keeps the schedule and its history but stops the beat entry from firing.",
        8,
    ),
    _schedule(
        "schedule.market_hours_only",
        "market_hours_only",
        "Market hours only",
        "Skip fires outside the NYSE session.",
        "Uses the real exchange calendar, so holidays and half-days are respected. Off, "
        "the schedule also fires overnight and at weekends — useful for futures work, "
        "expensive otherwise.",
        9,
    ),
    _schedule(
        "schedule.mode",
        "mode",
        "Payload mode",
        "Send the full capture, or only what changed since the last one.",
        "Diff mode feeds the model just the delta versus the previous ready snapshot: "
        "far cheaper per fire, but the model loses the standing context.",
        10,
        value_type="choice",
        choices=(("full", "Full payload"), ("diff", "Diff vs previous capture")),
    ),
    _schedule(
        "schedule.structured",
        "structured",
        "Structured observation",
        "Return a validated report object instead of streamed prose.",
        "Structured fires are what the Prediction Ledger extracts directional calls "
        "from, at no extra cost. They do not stream.",
        11,
    ),
    _schedule(
        "schedule.use_batch",
        "use_batch",
        "Batch submission",
        "Submit fires as a Messages Batch — about half price, not interactive.",
        "Claude-only. Results arrive when the batch completes (polled every minute) "
        "rather than streaming, so it suits overnight and end-of-day schedules.",
        12,
        provider_only="claude",
    ),
    _schedule(
        "schedule.consensus",
        "consensus",
        "Cross-model consensus",
        "Run the same structured report on every usable provider and compare.",
        "Roughly multiplies the cost of a fire by the number of usable providers. With "
        "fewer than two it honestly records a single-provider shape instead of "
        "pretending to agree with itself. Requires structured observation.",
        13,
        costs_money=True,
        cost_note="Multiplies each fire's cost by the number of usable providers.",
        requires=("schedule.structured",),
    ),
    _schedule(
        "schedule.investigate",
        "investigate",
        "Investigate on fire",
        "Run a bounded tool-using investigation instead of a single observation.",
        "Plain mode only. " + _MONEY_INVESTIGATE,
        14,
        costs_money=True,
        cost_note=_MONEY_INVESTIGATE,
    ),
    _schedule(
        "schedule.fire_mode",
        "fire_mode",
        "Fire mode",
        "Fire on a cron expression, or relative to the real session close.",
        "Relative-to-close follows the exchange calendar, so it lands correctly on "
        "half-days where a fixed cron would not.",
        15,
        value_type="choice",
        choices=(("cron", "Cron"), ("relative_to_close", "Relative to close")),
    ),
    _schedule(
        "schedule.close_offset_minutes",
        "close_offset_minutes",
        "Minutes before close",
        "How far ahead of the real close a relative schedule fires.",
        "Only used in relative-to-close fire mode.",
        16,
        value_type="int",
    ),
    _schedule(
        "schedule.override_provider",
        "override_provider",
        "Provider override",
        "Send this schedule's fires to a provider other than the profile's.",
        "Empty inherits the profile. Useful for running an expensive profile's "
        "observations on a cheaper model.",
        17,
        value_type="str",
    ),
    _schedule(
        "schedule.override_model",
        "override_model",
        "Model override",
        "Pin a specific model for this schedule's fires.",
        "Empty inherits the profile's model. Must belong to the resolved provider.",
        18,
        value_type="str",
    ),
    _schedule(
        "schedule.default_includes",
        "default_includes",
        "Schedule capture sections",
        "Override which sections this schedule's captures collect.",
        "This is the main lever on scheduled-fire cost: rich defaults multiply input "
        "tokens on every fire, all day.",
        19,
        value_type="multi",
    ),
    _schedule(
        "schedule.default_watchlist_tickers",
        "default_watchlist_tickers",
        "Schedule tickers",
        "Restrict this schedule's captures to specific tickers.",
        "Empty uses the profile's watchlist.",
        20,
        value_type="multi",
    ),
    Feature(
        key="trigger.enabled",
        label="Trigger armed",
        summary="Whether a condition rule is evaluated on the tick.",
        help=(
            "Disarming keeps the rule and its firing history but takes it out of the "
            "evaluation pass."
        ),
        group="observation",
        order=21,
        scope="per_trigger",
        backing="model_field",
        model_label="observer.EventTrigger",
        model_field="enabled",
        write_path="/api/triggers/",
        deep_link="/triggers",
    ),
    Feature(
        key="trigger.investigate",
        label="Investigate on trigger fire",
        summary="A fire runs a bounded tool-using investigation, not one observation.",
        help=_MONEY_INVESTIGATE,
        group="observation",
        order=22,
        scope="per_trigger",
        backing="model_field",
        model_label="observer.EventTrigger",
        model_field="investigate",
        write_path="/api/triggers/",
        deep_link="/triggers",
        costs_money=True,
        cost_note=_MONEY_INVESTIGATE,
    ),
    Feature(
        key="trigger.cooldown_seconds",
        label="Trigger cooldown",
        summary="Minimum quiet period between two fires of the same rule.",
        help=(
            "The brake that stops a flapping condition from firing — and billing — on every tick."
        ),
        group="observation",
        order=23,
        scope="per_trigger",
        backing="model_field",
        value_type="int",
        model_label="observer.EventTrigger",
        model_field="cooldown_seconds",
        write_path="/api/triggers/",
        deep_link="/triggers",
        unit="seconds",
    ),
    _briefing(
        "briefing.enabled",
        "enabled",
        "Morning briefing",
        "Assemble and post one briefing per local day.",
        "The deterministic sections — theses, events, fired triggers, news, market — "
        "render with no AI key at all. Off stops the daily job; you can still run a "
        "briefing on demand.",
        24,
        shipped_default=True,
    ),
    _briefing(
        "briefing.synthesis_enabled",
        "synthesis_enabled",
        "Briefing AI synthesis",
        "Pay for one model pass that reads the assembled briefing.",
        "Off, every data section still renders; only the written summary is skipped. "
        "This is the one part of the briefing that costs money.",
        25,
        shipped_default=True,
        costs_money=True,
        cost_note="One model call per briefing, once per day.",
    ),
    _briefing(
        "briefing.send_at_local",
        "send_at_local",
        "Briefing time",
        "Local time after which the day's briefing is assembled.",
        "The scheduler checks every 15 minutes and posts once the time has passed, so "
        "the briefing appears at or shortly after this time.",
        26,
        value_type="time",
        shipped_default="08:30:00",
    ),
    _briefing(
        "briefing.news_lookback_hours",
        "news_lookback_hours",
        "Briefing news window",
        "How far back the briefing gathers headlines.",
        "Long enough to span the overnight session by default.",
        27,
        value_type="int",
        shipped_default=14,
        unit="hours",
        min_value=1,
    ),
    _briefing(
        "briefing.events_within_days",
        "events_within_days",
        "Briefing event horizon",
        "How far forward the briefing looks for earnings and macro events.",
        "Widening it surfaces more of the calendar and makes the briefing longer.",
        28,
        value_type="int",
        shipped_default=7,
        unit="days",
        min_value=1,
    ),
    _briefing(
        "briefing.profile",
        "profile",
        "Briefing trading profile",
        "Which trading style frames the briefing. Object reference, not a switch.",
        "Empty uses the first active profile. This points at a row rather than holding "
        "a value, so it is set through the briefing config API rather than toggled "
        "here.",
        29,
        value_type="fk",
        shipped_default="",
        backing="informational",
        env_only_reason=(
            "A reference to a trading profile, not an on/off value. Set it with PATCH "
            "/api/briefings/config/."
        ),
    ),
    Feature(
        key="thesis.guard_enabled",
        label="Thesis invalidation guard",
        summary="Auto-create a trigger that watches a thesis's invalidation level.",
        help=(
            "Arming the guard on a thesis creates a condition rule tied to it, so the "
            "app tells you when your own stop is hit instead of you remembering to look."
        ),
        group="observation",
        order=30,
        scope="per_thesis",
        backing="model_field",
        model_label="thesis.Thesis",
        model_field="guard_enabled",
        write_path="/api/theses/",
        deep_link="/theses",
    ),
    # ============================ Autonomous spend ===========================
    Feature(
        key="spend.autonomous_daily_cap_usd",
        label="Autonomous daily cap",
        summary="Stops unattended investigations once the provider's day reaches this.",
        help=(
            "It gates the runs nobody asked for — a scheduled or trigger fire with "
            "Investigate on, a Desk sweep's investigations, a tool-grounded war-room "
            "persona — but what it measures is the provider's **total** recorded spend "
            "for the UTC day, interactive chat included. So a heavy day of chat can "
            "close the background work down, while chat itself is never blocked by "
            "this number: only the per-provider caps stop that. Read it as 'stop "
            "spending unattended once the day reaches $X', not as a separate budget. "
            "The one-shot model calls behind post-mortems, coverage revisions and the "
            "regime and book narratives are checked against the per-provider caps "
            "only. **0 removes the ceiling.** This is the single most important number "
            "on this page if you arm anything below."
        ),
        group="spend",
        order=1,
        scope="global",
        backing="system_settings",
        value_type="float",
        settings_field="ai_autonomous_daily_cap_usd",
        write_path="/api/settings/",
        env_var="AI_AUTONOMOUS_DAILY_CAP_USD",
        min_value=0,
        unit="USD",
    ),
    Feature(
        key="ai.investigation_max_iterations",
        label="Investigation tool rounds",
        summary="Ceiling on tool calls inside one autonomous investigation.",
        help=(
            "Each round is another billed model call, so this multiplies the cost of "
            "every investigation. 0 would be unbounded and is rejected."
        ),
        group="spend",
        order=2,
        scope="global",
        backing="system_settings",
        value_type="int",
        settings_field="ai_investigation_max_iterations",
        write_path="/api/settings/",
        env_var="AI_INVESTIGATION_MAX_ITERATIONS",
        min_value=1,
        unit="rounds",
    ),
    Feature(
        key="strategy.anomaly_sweep",
        label="Scheduled anomaly sweep",
        summary="Scan watched tickers on a schedule and open Desk investigations unasked.",
        help=(
            "Every 30 minutes the sweep looks for anomalies across watched tickers and "
            "**originates AI investigations on its own**. It is the most autonomous "
            "thing the app does; bound it with the autonomous daily cap above. Running "
            "a sweep by hand from the Desk page always works and ignores this switch."
        ),
        group="spend",
        order=3,
        scope="global",
        backing="system_settings",
        settings_field="anomaly_sweep_enabled",
        write_path="/api/settings/",
        env_var="ANOMALY_SWEEP_ENABLED",
        costs_money=True,
        cost_note=("Runs unattended every 30 minutes and can start investigations without you."),
    ),
    Feature(
        key="analytics.aieval_scheduled",
        label="Scheduled calibration eval",
        summary="Replay decided theses against a model on a schedule to score it.",
        help=(
            "Replays frozen source snapshots through a candidate model and records how "
            "well it called them. There is no mock short-circuit on this path: an armed "
            "schedule calls the real model and bills for it. Running an eval by hand "
            "from the command line always works."
        ),
        group="spend",
        order=4,
        scope="global",
        backing="system_settings",
        settings_field="aieval_scheduled_enabled",
        write_path="/api/settings/",
        env_var="AIEVAL_SCHEDULED_ENABLED",
        costs_money=True,
        cost_note="Each scheduled run replays up to the row limit below against a real model.",
    ),
    Feature(
        key="analytics.aieval_model",
        label="Eval model",
        summary="Which model the scheduled eval scores.",
        help="Any catalog model id. The vendor is inferred from the id.",
        group="spend",
        order=5,
        scope="global",
        backing="system_settings",
        value_type="str",
        settings_field="aieval_scheduled_model",
        write_path="/api/settings/",
        env_var="AIEVAL_SCHEDULED_MODEL",
        max_length=100,
        requires=("analytics.aieval_scheduled",),
    ),
    Feature(
        key="analytics.aieval_horizon",
        label="Eval horizon",
        summary="Which post-mortem horizon the eval scores against.",
        help="Matches the post-mortem horizons the app computes (7, 30 or 90 days).",
        group="spend",
        order=6,
        scope="global",
        backing="system_settings",
        value_type="int",
        settings_field="aieval_scheduled_horizon",
        write_path="/api/settings/",
        env_var="AIEVAL_SCHEDULED_HORIZON",
        min_value=1,
        unit="days",
        requires=("analytics.aieval_scheduled",),
    ),
    Feature(
        key="analytics.aieval_limit",
        label="Eval row limit",
        summary="How many theses one scheduled eval replays.",
        help="The direct cost lever on a scheduled eval: one model call per replayed row.",
        group="spend",
        order=7,
        scope="global",
        backing="system_settings",
        value_type="int",
        settings_field="aieval_scheduled_limit",
        write_path="/api/settings/",
        env_var="AIEVAL_SCHEDULED_LIMIT",
        min_value=1,
        unit="rows",
        requires=("analytics.aieval_scheduled",),
    ),
    Feature(
        key="provider.daily_cost_cap_usd",
        label="Provider daily cap",
        summary="Hard daily spend ceiling per provider.",
        help=(
            "Checked before a run starts. Over the cap, the run is skipped and recorded "
            "as skipped rather than failing silently."
        ),
        group="spend",
        order=8,
        scope="per_provider",
        backing="model_field",
        value_type="float",
        model_label="secrets_app.ProviderConfig",
        model_field="daily_cost_cap_usd",
        write_path="/api/schwab/providers/",
        deep_link="/settings",
        unit="USD",
    ),
    Feature(
        key="provider.monthly_cost_cap_usd",
        label="Provider monthly cap",
        summary="Rolling 30-day spend ceiling per provider. Empty means none.",
        help=(
            "Sums the last 30 days of recorded run cost. An empty cap is a genuine no-op, not zero."
        ),
        group="spend",
        order=9,
        scope="per_provider",
        backing="model_field",
        value_type="float",
        model_label="secrets_app.ProviderConfig",
        model_field="monthly_cost_cap_usd",
        write_path="/api/schwab/providers/",
        deep_link="/settings",
        unit="USD",
    ),
    # =========================== Data & retention ============================
    _retention("retention_ohlc_days", "OHLC bars", "price bars", 1),
    _retention("retention_chain_days", "Option chains", "captured option chains", 2),
    _retention("retention_notification_days", "Notifications", "notifications", 3),
    _retention("retention_error_days", "Resolved errors", "resolved error events", 4),
    _retention("retention_regime_days", "Regime readings", "market-regime readings", 5),
    _retention("retention_desk_days", "Desk findings", "desk findings", 6),
    _retention("retention_book_days", "Book snapshots", "whole-book risk snapshots", 7),
    _section(
        "quotes",
        "Quotes",
        "Live quote lines for the watchlist. The cheapest section and the one most "
        "objectives assume is present.",
        20,
    ),
    _section(
        "ohlc",
        "OHLC",
        "Intraday and daily bars, plus per-watchlist daily history and a long-horizon "
        "summary. One of the two largest sections by tokens.",
        21,
    ),
    _section(
        "chain",
        "Option chain",
        "Strikes around the money with greeks, plus a computed analytics block: "
        "put/call ratios, max pain, skew, dealer gamma and expected move. The largest "
        "section, and the first one dropped under token pressure.",
        22,
    ),
    _section(
        "positions",
        "Positions",
        "Your brokerage positions. Requires a connected broker; degrades to empty otherwise.",
        23,
    ),
    _section(
        "breadth",
        "Market breadth",
        "Index and sector quotes, advance/decline internals, relative strength, sector "
        "rotation and factor spreads. The section that lets the model say what kind of "
        "day it is.",
        24,
    ),
    _section(
        "news",
        "News",
        "Recent headlines for the watchlist, attached as citable search results.",
        25,
    ),
    _section(
        "events",
        "Upcoming events",
        "Forward earnings and macro calendar. Not the session calendar.",
        26,
    ),
    _section(
        "macro",
        "Macro",
        "FRED series including credit spreads, paired with live yield-index quotes. "
        "The published series lag about a business day; that lag is noted in the "
        "payload.",
        27,
    ),
    _section(
        "fundamentals",
        "Company fundamentals",
        "Company financials for equity-like symbols. Skipped for indices and futures, "
        "which are not filers.",
        28,
    ),
    _section(
        "filings",
        "SEC filings",
        "Recent EDGAR filings for equity-like symbols only.",
        29,
    ),
    _section("treasury", "Treasury", "The Treasury yield curve.", 30),
    _section(
        "overnight",
        "Overnight board",
        "What moved while the cash session was closed.",
        31,
    ),
    _section(
        "image",
        "Chart image",
        "A deterministically rendered chart attached to the run. Needs a vision-capable provider.",
        32,
    ),
    _section(
        "notes",
        "Notes",
        "Your own free text, carried into the payload as its own section. Nothing is fetched.",
        33,
    ),
    _section("fed", "Fed communication", "Recent Federal Reserve communication.", 34),
    _section(
        "flowlite",
        "Flow proxy (volume-based)",
        "A volume-derived flow proxy. A reasoning aid, not order-flow data.",
        35,
    ),
    Feature(
        key="section.vix",
        label="VIX term structure",
        summary="Always on. Every capture path appends it, and it is never pruned.",
        help=(
            "Spot VIX and VVIX with their ratio, plus the front and second-month "
            "futures with basis and contango. It is deliberately not user-selectable: "
            "volatility context changes the reading of every other section, so it "
            "cannot be dropped by a profile or by the token budget. Without a broker "
            "connection the futures leg degrades to spot-only with an explicit note "
            "rather than going missing."
        ),
        group="data",
        order=36,
        scope="global",
        backing="informational",
        env_only_reason=(
            "Always on by design: every capture path appends it and the token budget "
            "may not prune it."
        ),
        shipped_default=True,
    ),
    # ============================== Methodology ==============================
    Feature(
        key="methodology.returns_adjust_dividends",
        label="Dividend-adjusted (total-return) math",
        summary="Compute forward returns on a total-return basis instead of price-return.",
        help=(
            "**Retroactive.** Splits are always adjusted; dividends are the methodology "
            "choice. Turning this on restates every post-mortem, Scorecard and Mirror "
            "number already computed under price-return, because they are all derived "
            "from the same stored bars on read. Nothing is recomputed and stored — the "
            "numbers simply change. This is the one app-wide capability that ships off."
        ),
        group="methodology",
        order=1,
        scope="global",
        backing="system_settings",
        settings_field="returns_adjust_dividends",
        write_path="/api/settings/",
        env_var="RETURNS_ADJUST_DIVIDENDS",
        retroactive=True,
    ),
    # ============================== Danger zone ==============================
    Feature(
        key="danger.restore_from_ui",
        label="Restore from backup in the UI",
        summary="Allow overwriting the live database from a backup without a shell.",
        help=(
            "A restore replaces the entire database with the contents of a dump — the "
            "one irreversible action in the app. Off leaves the command-line restore as "
            "the only path, which is the safe posture for a machine you share."
        ),
        group="danger",
        order=1,
        scope="global",
        backing="system_settings",
        settings_field="restore_from_ui_enabled",
        write_path="/api/settings/",
        env_var="RESTORE_FROM_UI_ENABLED",
    ),
]


# --- helpers ---------------------------------------------------------------------

_SPEC_DEFAULTS: dict[str, object] = {f: d for f, _, d in _SPEC}
_SPEC_ENV: dict[str, str] = {f: s for f, s, _ in _SPEC}


def feature_keys() -> set[str]:
    return {f.key for f in FEATURES}


def system_settings_fields() -> set[str]:
    """SystemSettings/_SPEC field names the registry claims to cover."""
    return {f.settings_field for f in FEATURES if f.backing == "system_settings"}


def model_field_pairs() -> set[tuple[str, str]]:
    """(model_label, field) pairs the registry covers — the per-object drift gate's side."""
    return {
        (f.model_label, f.model_field)
        for f in FEATURES
        if f.backing == "model_field" and f.model_label
    }


def env_vars() -> set[str]:
    return {f.env_var for f in FEATURES if f.env_var}


def hard_default(f: Feature) -> object:
    """The default baked into the source: _SPEC for system_settings rows (single source
    of truth), the declared ``shipped_default`` otherwise."""
    if f.backing == "system_settings":
        return _SPEC_DEFAULTS.get(f.settings_field)
    return f.shipped_default


def setting_name(f: Feature) -> str:
    """The Django settings / env name behind a row."""
    if f.backing == "system_settings":
        return _SPEC_ENV.get(f.settings_field, "")
    return f.env_var


def groups_by_key() -> dict[str, FeatureGroup]:
    return {g.key: g for g in GROUPS}


# Models the per-object drift gate walks. A BooleanField on one of these without a
# registry row reds CI — that is what keeps this page from going stale.
GATED_MODELS: tuple[str, ...] = (
    "profiles.TradingProfile",
    "profiles.AgentPreset",
    "observer.ObserverSchedule",
    "observer.EventTrigger",
    "observer.BriefingConfig",
    "thesis.Thesis",
    "thesis.Lesson",
    "secrets_app.ProviderConfig",
)

# State-not-switch BooleanFields: recorded outcomes, not things a user turns on.
# Format: "<app_label>.<Model>.<field>". Keep one comment per exemption.
EXEMPT_MODEL_FIELDS: frozenset[str] = frozenset(
    {
        # A preset is composer metadata: the objective picker copies its
        # objective_template into the textarea and nothing else about it travels
        # with the capture, so no run can know which preset it came from. This
        # field records how its author describes the objective; it routes nothing.
        # The switch that really runs a parsed report is schedule.structured on an
        # ObserverSchedule, which the fire path reads.
        "profiles.AgentPreset.structured",
        # Models deliberately NOT gated for the same reason (their booleans record
        # what happened, they do not configure anything): core.ErrorEvent.resolved,
        # threads.ToolCall.ok, observer.TriggerFiring.cost_capped.
    }
)

__all__ = [
    "EXEMPT_MODEL_FIELDS",
    "FEATURES",
    "GATED_MODELS",
    "GROUPS",
    "SCOPE_NOUN",
    "Feature",
    "FeatureGroup",
    "env_vars",
    "feature_keys",
    "groups_by_key",
    "hard_default",
    "model_field_pairs",
    "setting_name",
    "system_settings_fields",
]
