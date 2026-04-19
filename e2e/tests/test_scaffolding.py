"""Scaffolding collection test — asserts new lane dirs are importable."""
from __future__ import annotations


def test_lane_packages_importable() -> None:
    import e2e.ui  # noqa: F401
    import e2e.api  # noqa: F401
    import e2e.ws  # noqa: F401
    import e2e.visual  # noqa: F401
    import e2e.a11y  # noqa: F401
    import e2e.perf  # noqa: F401
    import e2e.mocks  # noqa: F401
    import e2e.helpers  # noqa: F401
