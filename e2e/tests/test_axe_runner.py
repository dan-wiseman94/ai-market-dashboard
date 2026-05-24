"""Unit-shape test for axe_runner helper."""

from __future__ import annotations


def test_axe_runner_exposes_scan() -> None:
    from e2e.helpers import axe_runner

    assert hasattr(axe_runner, "scan")
    assert hasattr(axe_runner, "Violation")


def test_violation_to_dict_roundtrip() -> None:
    from e2e.helpers.axe_runner import Violation

    v = Violation(
        id="aria-label",
        impact="serious",
        description="label missing",
        help_url="https://example.test/help/aria-label",
        targets=["#x"],
    )
    d = v.to_dict()
    assert d["id"] == "aria-label"
    assert d["impact"] == "serious"
    assert "label" in d["description"]
