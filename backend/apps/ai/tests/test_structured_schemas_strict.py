"""Every output model handed to ``run_structured`` must survive OpenAI's strict
JSON-schema conversion: all properties required, ``additionalProperties`` off,
no Pydantic feature strict mode rejects. Offline guard for the OpenAI path."""

from __future__ import annotations

import pytest
from openai.lib._pydantic import to_strict_json_schema

from apps.book.services.narrative import BookNarrative
from apps.observer.schemas import ObservationReport
from apps.strategy.coverage.schemas import CoverageRevisionDraft
from apps.strategy.regime.services.narrative import RegimeNarrative
from apps.strategy.warroom.services.verdict import WarRoomVerdict
from apps.thesis.schemas import PostMortemReport


@pytest.mark.parametrize(
    "model",
    [
        ObservationReport,
        PostMortemReport,
        CoverageRevisionDraft,
        RegimeNarrative,
        BookNarrative,
        WarRoomVerdict,
    ],
)
def test_output_model_converts_to_strict_schema(model):
    schema = to_strict_json_schema(model)
    assert schema["type"] == "object"
    assert schema["additionalProperties"] is False
    assert set(schema["required"]) == set(schema["properties"])
