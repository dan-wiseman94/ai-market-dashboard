"""The structured path must never reach a billable endpoint under MOCK_EXTERNAL.

Nine call sites funnel through ``run_structured`` (observer reports and consensus,
the eval harness, post-mortems, coverage revisions, the regime and book narratives,
the War Room verdict). Several of them hang off beat schedules that also run in the
e2e overlay, where ``beat`` is up with ``MOCK_EXTERNAL=true`` — so the guard lives at
the single choke point rather than on each task.
"""

from __future__ import annotations

from typing import Literal

import pytest
from pydantic import BaseModel, Field

from apps.ai.structured import run_structured


class _Nested(BaseModel):
    label: str


class _Report(BaseModel):
    headline: str
    direction: Literal["up", "down"]
    nested: _Nested
    count: int
    ratio: float
    flag: bool
    tags: list[str] = Field(default_factory=list)
    note: str | None = None


@pytest.fixture
def _mock_mode(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("MOCK_EXTERNAL", "true")


@pytest.mark.usefixtures("_mock_mode")
def test_returns_a_valid_instance_without_calling_a_provider() -> None:
    # A bogus key is the proof: any real dispatch would raise on authentication.
    report = run_structured(
        provider="claude",
        api_key="not-a-key",
        model="claude-opus-5",
        system="",
        user="",
        output_model=_Report,
    )

    assert isinstance(report, _Report)
    assert report.headline == ""
    assert report.direction == "up"  # first Literal arg
    assert report.nested.label == ""
    assert (report.count, report.ratio, report.flag) == (0, 0.0, False)
    assert report.tags == []  # declared default survives
    assert report.note is None


@pytest.mark.usefixtures("_mock_mode")
@pytest.mark.parametrize("provider", ["claude", "openai", "local"])
def test_every_provider_short_circuits(provider: str) -> None:
    assert isinstance(
        run_structured(
            provider=provider,
            api_key="not-a-key",
            model="whatever",
            system="",
            user="",
            output_model=_Nested,
        ),
        _Nested,
    )


def test_outside_mock_mode_the_guard_does_not_swallow_the_call(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv("MOCK_EXTERNAL", raising=False)

    with pytest.raises(Exception, match=r".+"):
        run_structured(
            provider="claude",
            api_key="not-a-key",
            model="claude-opus-5",
            system="",
            user="",
            output_model=_Nested,
        )
