"""The untrusted-content data boundary (prompt-injection defense) is present on every
system prompt build_system_prompt produces — coach on or off, profile or not."""

from datetime import UTC, datetime

from apps.threads.coach import build_system_prompt

_NOW = datetime(2026, 1, 2, 15, 0, tzinfo=UTC)


class _Profile:
    def __init__(self, *, style: str, enable_coach: bool) -> None:
        self.style = style
        self.enable_coach = enable_coach


def test_data_boundary_present_with_coach() -> None:
    system = build_system_prompt(
        _Profile(style="Aggressive intraday.", enable_coach=True), now=_NOW
    )
    assert "Data boundary" in system
    assert "UNTRUSTED CONTENT" in system
    # The style is still carried through, under the boundary.
    assert "Aggressive intraday." in system
    assert system.index("Data boundary") < system.index("Aggressive intraday.")


def test_data_boundary_present_legacy_coach_off() -> None:
    system = build_system_prompt(_Profile(style="Plain style.", enable_coach=False), now=_NOW)
    assert "Data boundary" in system
    assert "Plain style." in system


def test_data_boundary_present_without_profile() -> None:
    assert "Data boundary" in build_system_prompt(None, now=_NOW)
