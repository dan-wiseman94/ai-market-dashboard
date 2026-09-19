"""Every output model handed to ``run_structured`` must survive OpenAI's strict
JSON-schema conversion, sanitized to the keyword subset the API accepts: all
properties required, ``additionalProperties`` off, no keyword strict mode
rejects (``minLength``/``maxLength`` above all). Offline guard for the OpenAI
path."""

from __future__ import annotations

from typing import Any

import pytest
from openai.lib._pydantic import to_strict_json_schema

from apps.ai.providers import openai_structured
from apps.ai.providers.openai_structured import strict_schema_for
from apps.book.services.narrative import BookNarrative
from apps.observer.schemas import ObservationReport
from apps.strategy.coverage.schemas import CoverageRevisionDraft
from apps.strategy.regime.services.narrative import RegimeNarrative
from apps.strategy.warroom.services.verdict import WarRoomVerdict
from apps.thesis.schemas import PostMortemReport

OUTPUT_MODELS = [
    ObservationReport,
    PostMortemReport,
    CoverageRevisionDraft,
    RegimeNarrative,
    BookNarrative,
    WarRoomVerdict,
]


def _walk_keys(node: Any) -> set[str]:
    """Every dict key appearing anywhere in ``node`` (recursing through lists and
    dict values, without regard for schema structure) — used only to check for
    the presence of a specific keyword string, never to enumerate keywords."""
    keys: set[str] = set()
    if isinstance(node, dict):
        keys.update(node.keys())
        for value in node.values():
            keys |= _walk_keys(value)
    elif isinstance(node, list):
        for item in node:
            keys |= _walk_keys(item)
    return keys


def _schema_keys(node: Any) -> set[str]:
    """Every schema-*keyword* key appearing anywhere in a JSON-schema node.

    ``properties`` and ``$defs`` values are name-keyed maps (field/def name →
    schema), not schema nodes themselves, so their keys (arbitrary field/def
    names, never schema keywords) are excluded — only their values recurse.
    """
    keys: set[str] = set()
    if isinstance(node, list):
        for item in node:
            keys |= _schema_keys(item)
        return keys
    if not isinstance(node, dict):
        return keys
    keys.update(node.keys())
    for key, value in node.items():
        if key in ("properties", "$defs") and isinstance(value, dict):
            for sub_schema in value.values():
                keys |= _schema_keys(sub_schema)
        else:
            keys |= _schema_keys(value)
    return keys


@pytest.mark.parametrize("model", OUTPUT_MODELS)
def test_output_model_converts_to_sanitized_strict_schema(model):
    schema = strict_schema_for(model)
    assert schema["type"] == "object"
    assert schema["additionalProperties"] is False
    assert set(schema["required"]) == set(schema["properties"])

    keys = _schema_keys(schema)
    assert keys <= openai_structured._STRICT_KEYWORDS
    assert "minLength" not in keys
    assert "maxLength" not in keys


def test_unsanitized_schema_does_contain_maxlength():
    """Pin that ``ObservationReport`` really does carry ``max_length`` string
    fields, so the sanitizer above is known to be load-bearing rather than a
    no-op that would silently pass if every ``max_length`` field were removed."""
    schema = to_strict_json_schema(ObservationReport)
    assert "maxLength" in _walk_keys(schema)
