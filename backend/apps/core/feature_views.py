"""``GET /api/features/`` — the Features page's single read.

Read-only on purpose. Every write keeps going to the endpoint that already owns the
row (``PATCH /api/settings/`` for the global knobs, ``PATCH /api/briefings/config/``
for the briefing singleton, the existing ViewSets for per-object rows), so the
validation chain in ``apps.core.views._coerce_setting`` stays the only path into
``SystemSettings`` and this endpoint adds no fuzzable write surface.

Rows are built from the static registry, which is pure Python and cannot fail. Only
the live aggregates and the connection probe are wrapped in ``_safe``, and they
degrade to a **full, contract-valid shape** — ``{"on": None, "total": None,
"degraded": True}``, never ``{}`` (which crashes the tile that reads it) and never
``{"on": 0, "total": 0}`` (which renders "0 of 13" — a lie the user would act on).
``SystemSettings.load()`` is deliberately NOT wrapped: if that read fails the page is
not functional, and a degraded render would invite flipping a switch against stale
state.
"""

from __future__ import annotations

import logging
import os
from typing import Any

import sentry_sdk
from django.apps import apps as django_apps
from django.conf import settings as dj_settings
from django.db.models import Count, Q
from drf_spectacular.utils import extend_schema
from rest_framework.request import Request
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.core.features import (
    FEATURES,
    GROUPS,
    SCOPE_NOUN,
    Feature,
    hard_default,
    setting_name,
)
from apps.core.serializers import FeatureRegistrySerializer

log = logging.getLogger(__name__)

_TRADINGVIEW_MANAGE_PATH = "/settings/connections"
_PROFILE_LABEL = "profiles.TradingProfile"


def _safe(fn, default):
    try:
        return fn()
    except Exception as exc:  # pragma: no cover - exercised via the degraded test
        log.warning("features.section_failed: %s", exc)
        sentry_sdk.capture_exception(exc)  # no-op unless SENTRY_DSN is configured
        return default


# --- live aggregates -------------------------------------------------------------


def _bool_fields_for(label: str) -> list[str]:
    return sorted(
        {
            f.model_field
            for f in FEATURES
            if f.model_label == label and f.value_type == "bool" and f.scope.startswith("per_")
        }
    )


def _section_kinds() -> list[str]:
    return [f.key.removeprefix("section.") for f in FEATURES if f.key.startswith("section.")]


def _aggregate(label: str) -> dict[str, int]:
    """One query per model: the row count plus a filtered count per boolean field.

    The snapshot-section rows ride the TradingProfile aggregate — each kind is a
    containment test against the profile's ``default_includes`` list.
    """
    model = django_apps.get_model(label)
    # Aliases are prefixed: Django rejects an aggregate alias that collides with a
    # field name ("Cannot compute Count('enabled'): 'enabled' is an aggregate").
    spec: dict[str, Any] = {"total__": Count("pk")}
    for name in _bool_fields_for(label):
        spec[f"on__{name}"] = Count("pk", filter=Q(**{name: True}))
    if label == _PROFILE_LABEL:
        for kind in _section_kinds():
            if kind == "vix":  # always-on, never stored in default_includes
                continue
            spec[f"section__{kind}"] = Count("pk", filter=Q(default_includes__contains=[kind]))
    return model.objects.aggregate(**spec)


def _rollups() -> dict[str, dict[str, int] | None]:
    labels = sorted({f.model_label for f in FEATURES if f.model_label})
    return {label: _safe(lambda lbl=label: _aggregate(lbl), None) for label in labels}


def _tradingview_satisfied() -> bool | None:
    def probe() -> bool:
        from apps.market.services import tradingview

        return bool(tradingview.is_connected())

    return _safe(probe, None)


# --- row assembly ----------------------------------------------------------------


def _source(has_override: bool, env_name: str) -> str:
    """Provenance tri-state. Environment presence only — the value is never read here.

    Caveat worth knowing: ``override_settings`` in a test changes ``settings.X``
    without touching ``os.environ``, so such a value honestly reports "default".
    """
    if has_override:
        return "override"
    return "env" if env_name and os.environ.get(env_name) is not None else "default"


def _requirement(f: Feature, tv_satisfied: bool | None) -> dict[str, object] | None:
    if f.requires_connection != "tradingview":
        return None
    return {
        "id": "tradingview",
        "label": "TradingView",
        "satisfied": tv_satisfied,
        "manage_path": _TRADINGVIEW_MANAGE_PATH,
    }


def _editable(f: Feature) -> bool:
    if f.backing == "system_settings":
        return True
    if f.backing == "model_field" and f.scope == "singleton":
        return bool(f.write_path)
    return False


def _base(f: Feature, tv_satisfied: bool | None) -> dict[str, object]:
    editable = _editable(f)
    return {
        "key": f.key,
        "label": f.label,
        "summary": f.summary,
        "help": f.help,
        "group": f.group,
        "order": f.order,
        "scope": f.scope,
        "backing": f.backing,
        "value_type": f.value_type,
        "editable": editable,
        "write_path": f.write_path if editable else "",
        "field": f.settings_field or f.model_field,
        "env_var": f.env_var or setting_name(f),
        "env_only_reason": f.env_only_reason,
        "costs_money": f.costs_money,
        "cost_note": f.cost_note,
        "retroactive": f.retroactive,
        "requires": list(f.requires),
        "requirement": _requirement(f, tv_satisfied),
        "provider_only": f.provider_only,
        "deep_link": f.deep_link,
    }


def _resolved_global(f: Feature, cfg: object, rc: object) -> dict[str, object]:
    """A SystemSettings-backed row: effective value, raw override, provenance."""
    override = getattr(cfg, f.settings_field)
    name = setting_name(f)
    hard = hard_default(f)
    return {
        "value": getattr(rc, f.settings_field),
        "default_value": getattr(dj_settings, name, hard),
        "shipped_default": hard,
        "override": override,
        "source": _source(override is not None, name),
    }


def _resolved_singleton(f: Feature, briefing: object) -> dict[str, object]:
    """A non-nullable singleton column: there is no NULL, so "overridden" means
    "differs from the shipped default"."""
    default = f.shipped_default
    if briefing is None:  # degraded read — report the shipped default, not a fake False
        return {
            "value": default,
            "default_value": default,
            "shipped_default": default,
            "override": None,
            "source": "default",
        }
    raw = getattr(briefing, f.model_field, None)
    if f.value_type in ("time", "fk"):
        raw = "" if raw is None else str(getattr(raw, "pk", raw))
    return {
        "value": raw,
        "default_value": default,
        "shipped_default": default,
        "override": raw,
        "source": "override" if raw != default else "default",
    }


def _resolved_env(f: Feature) -> dict[str, object]:
    hard = hard_default(f)
    value = getattr(dj_settings, f.env_var, hard) if f.env_var else hard
    return {
        "value": value,
        "default_value": value,
        "shipped_default": hard,
        "override": None,
        "source": _source(False, f.env_var),
    }


def _values_for(f: Feature, cfg: object, rc: object, briefing: object) -> dict[str, object]:
    if f.backing == "system_settings":
        return _resolved_global(f, cfg, rc)
    if f.scope == "singleton" and f.model_label:
        return _resolved_singleton(f, briefing)
    if f.backing == "env_only":
        return _resolved_env(f)
    # informational: a stated constant (always-on VIX, an object reference)
    hard = hard_default(f)
    return {
        "value": hard,
        "default_value": hard,
        "shipped_default": hard,
        "override": None,
        "source": "default",
    }


def _rollup_for(f: Feature, rollups: dict[str, dict[str, int] | None]) -> dict[str, object]:
    agg = rollups.get(f.model_label)
    if agg is None:
        return {"on": None, "total": None, "degraded": True}
    if f.key.startswith("section."):
        return {
            "on": agg.get(f"section__{f.key.removeprefix('section.')}"),
            "total": agg.get("total__"),
            "degraded": False,
        }
    # A non-boolean per-object field has no meaningful "how many are on".
    on = agg.get(f"on__{f.model_field}") if f.value_type == "bool" else None
    return {"on": on, "total": agg.get("total__"), "degraded": False}


def _as_bool_row(base: dict, vals: dict) -> dict:
    return {
        **base,
        "value": bool(vals["value"]),
        "default_value": bool(vals["default_value"]),
        "shipped_default": None
        if vals["shipped_default"] is None
        else bool(vals["shipped_default"]),
        "override": None if vals["override"] is None else bool(vals["override"]),
        "source": vals["source"],
    }


def _as_number_row(f: Feature, base: dict, vals: dict) -> dict:
    def num(v: object) -> float | None:
        return None if v is None else float(v)  # type: ignore[arg-type]

    return {
        **base,
        "value": num(vals["value"]) or 0.0,
        "default_value": num(vals["default_value"]) or 0.0,
        "shipped_default": num(vals["shipped_default"]),
        "override": num(vals["override"]),
        "source": vals["source"],
        "min_value": f.min_value,
        "max_value": f.max_value,
        "unit": f.unit,
        "is_float": f.value_type == "float",
    }


def _as_text_row(f: Feature, base: dict, vals: dict) -> dict:
    def text(v: object) -> str | None:
        return None if v is None else str(v)

    return {
        **base,
        "value": text(vals["value"]) or "",
        "default_value": text(vals["default_value"]) or "",
        "shipped_default": text(vals["shipped_default"]),
        "override": text(vals["override"]),
        "source": vals["source"],
        "choices": [{"value": v, "label": lbl} for v, lbl in f.choices],
        "max_length": f.max_length,
    }


class FeatureRegistryView(APIView):
    """GET /api/features/ — every switchable capability, with its live value.

    Four typed arrays keyed off ``value_type`` rather than one polymorphic list, so
    the generated TypeScript stays concrete. Per-object rows are their own array:
    they carry a rollup and a deep link, never a value.
    """

    @extend_schema(
        responses=FeatureRegistrySerializer,
        description=(
            "Read-only inventory of every user-switchable capability: copy, grouping, "
            "effective value, provenance and per-object rollups. Writes go to the "
            "endpoint named by each row's write_path."
        ),
    )
    def get(self, _request: Request) -> Response:
        from apps.core.models import SystemSettings
        from apps.core.runtime_config import runtime_config

        cfg = SystemSettings.load()  # NOT _safe-wrapped: see the module docstring.
        rc = runtime_config()
        briefing = _safe(_load_briefing, None)
        rollups = _rollups()
        tv = _tradingview_satisfied()

        out: dict[str, list[dict]] = {
            "toggles": [],
            "numbers": [],
            "texts": [],
            "per_object": [],
        }
        for f in sorted(FEATURES, key=lambda r: (r.group, r.order, r.key)):
            base = _base(f, tv)
            if f.scope.startswith("per_"):
                out["per_object"].append(
                    {**base, **_rollup_for(f, rollups), "noun": SCOPE_NOUN.get(f.scope, "items")}
                )
                continue
            vals = _values_for(f, cfg, rc, briefing)
            if f.value_type == "bool":
                out["toggles"].append(_as_bool_row(base, vals))
            elif f.value_type in ("int", "float"):
                out["numbers"].append(_as_number_row(f, base, vals))
            else:
                out["texts"].append(_as_text_row(f, base, vals))

        return Response(
            {
                "groups": [
                    {"key": g.key, "label": g.label, "blurb": g.blurb, "order": g.order}
                    for g in sorted(GROUPS, key=lambda g: g.order)
                ],
                **out,
            }
        )


def _load_briefing():
    model = django_apps.get_model("observer.BriefingConfig")
    return model.load()
