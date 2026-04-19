"""Make target surface tests."""
from __future__ import annotations

from pathlib import Path


def _makefile_text() -> str:
    return Path("/app/Makefile").read_text() if Path("/app/Makefile").exists() else Path("Makefile").read_text()


def test_makefile_has_lane_targets() -> None:
    text = _makefile_text()
    for target in (
        "e2e-ui:", "e2e-api:", "e2e-ws:", "e2e-visual:",
        "e2e-visual-update:", "e2e-a11y:", "e2e-perf:",
        "e2e-up:", "e2e-down:",
    ):
        assert target in text, f"missing Make target: {target}"


def test_makefile_help_includes_lane_targets() -> None:
    """Lane targets must have help comments so `make help` lists them."""
    text = _makefile_text()
    for line_prefix in ("e2e-ui:", "e2e-api:", "e2e-ws:", "e2e-visual:", "e2e-a11y:", "e2e-perf:"):
        for row in text.splitlines():
            if row.startswith(line_prefix):
                assert "## " in row, f"{line_prefix} missing `## description`"
                break
        else:
            raise AssertionError(f"target not found: {line_prefix}")
