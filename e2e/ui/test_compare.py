"""Compare — multi-branch parallel consultation: fan-out + per-branch cost routing.

Each branch streams independently into its own tab; a ``cost`` WS event lands per
branch after ``message_done`` and is routed to that branch's tab (the
``branch-cost-<id>`` pill). Under the e2e ``MOCK_EXTERNAL`` overlay all three
providers short-circuit to a canned stream, so a real fan-out is exercisable.
"""

from __future__ import annotations

import pytest
from playwright.sync_api import expect

from e2e.pages.compare import CompareDialog
from e2e.pages.thread_detail import ThreadDetailPage


def _fresh_chat_thread(title: str) -> int:
    from apps.profiles.models import TradingProfile
    from apps.threads.models import Thread

    profile = TradingProfile.objects.filter(name="E2E Default").first()
    return Thread.objects.create(title=title, profile=profile, kind="chat").id


@pytest.mark.integration
@pytest.mark.ui
def test_compare_two_branches_stream_and_cost(page, frontend_base_url, minimal) -> None:
    """The default two branches (claude + openai) both stream and resolve a cost."""
    tid = _fresh_chat_thread("E2E compare two branches")
    detail = ThreadDetailPage(page, frontend_base_url)
    detail.go(tid)
    detail.expect_error_boundary_absent()

    c = CompareDialog(page, frontend_base_url)
    c.open()
    c.dispatch("What do you see in this tape?")

    # Both branch tabs appear and each resolves a cost (pending → resolved).
    expect(c.branch_costs).to_have_count(2, timeout=20_000)
    expect(c.pending_costs).to_have_count(0, timeout=45_000)


@pytest.mark.integration
@pytest.mark.ui
def test_compare_three_branches_route_costs(page, frontend_base_url, minimal) -> None:
    """A third branch fans out and routes its own cost to its own tab.

    The provider <select> only offers providers that have catalog models; under
    e2e that's claude + openai (no ``local`` models are seeded), so we exercise
    three-way fan-out + cost routing across the available providers rather than a
    literal three-provider spread.
    """
    tid = _fresh_chat_thread("E2E compare three branches")
    detail = ThreadDetailPage(page, frontend_base_url)
    detail.go(tid)
    detail.expect_error_boundary_absent()

    c = CompareDialog(page, frontend_base_url)
    c.open()
    # Default branches: [claude, openai]; add a third (claude) → three-way fan-out.
    c.add_branch()
    c.dispatch("Three-way read on this tape?")

    expect(c.branch_costs).to_have_count(3, timeout=20_000)
    expect(c.pending_costs).to_have_count(0, timeout=60_000)
