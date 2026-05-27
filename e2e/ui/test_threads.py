"""Threads — the *actual* chat flow: list → open → send → stream → render.

These tests drive the real composer end-to-end against the ``MOCK_EXTERNAL``
overlay. On the **default** scenario the AI provider streams ``"Mocked "`` +
``"response"`` from the worker, so a working send paints ``"Mocked response"``
into the assistant bubble. The two regression tests below would have caught the
bugs the old assertion-free smoke tests let through:

  * **"Send did nothing"** — the typed user turn never reaches the transcript.
  * **"Response never rendered"** — the assistant stream never paints.

Each send-flow test creates its **own** fresh thread so accumulated history in
the shared (non-rolled-back) e2e DB can't produce strict-mode locator clashes
on ``"Mocked response"``.

The mid-stream Stop test uses the ``slow-stream`` scenario, which now reaches the
worker (``run_ai_on_message`` re-applies the request's scenario in the worker
process — see threads/tasks.py + views.py), so there's a real window to click
Stop before the stream completes.
"""

from __future__ import annotations

import pytest
from playwright.sync_api import expect

from e2e.pages.thread_detail import ThreadDetailPage
from e2e.pages.threads import ThreadsListPage


def _fresh_chat_thread(title: str) -> int:
    """Create an isolated chat thread for one test; return its id."""
    from apps.profiles.models import TradingProfile
    from apps.threads.models import Thread

    profile = TradingProfile.objects.filter(name="E2E Default").first()
    t = Thread.objects.create(title=title, profile=profile, kind="chat")
    return t.id


@pytest.mark.integration
@pytest.mark.ui
def test_threads_list_shows_seeded_rows(page, frontend_base_url, threads) -> None:
    """The list renders actual seeded threads — not merely a non-empty <body>."""
    p = ThreadsListPage(page, frontend_base_url)
    p.go()
    expect(page.get_by_text("E2E plain thread")).to_be_visible(timeout=10_000)


@pytest.mark.integration
@pytest.mark.ui
def test_thread_send_renders_user_turn_and_streamed_reply(page, frontend_base_url, threads) -> None:
    """Regression: typing + Send must (1) post the turn and (2) render the reply.

    Guards "Send did nothing" and "Response never rendered" together. The
    user turn is seeded into the transcript by the post-``message_done``
    refetch, so we wait for the assistant reply (the done signal) first, then
    assert the user's text is present.
    """
    tid = _fresh_chat_thread("E2E send-flow happy path")
    detail = ThreadDetailPage(page, frontend_base_url)
    detail.go(tid)

    # Page mounted past "Loading thread…" and the composer is interactive.
    expect(detail.compose).to_be_visible(timeout=10_000)

    detail.send("What do you see in this tape?")

    # (2) Assistant stream reached the UI and painted to completion.
    detail.wait_for_done(timeout=20_000)
    # (1) The user's turn is in the transcript (proves POST /send/ fired + refetch).
    expect(page.get_by_text("What do you see in this tape?")).to_be_visible(timeout=10_000)


@pytest.mark.integration
@pytest.mark.ui
def test_thread_send_via_enter_key_streams_reply(page, frontend_base_url, threads) -> None:
    """The composer is a <form>; pressing Enter must submit it (not just the button)."""
    tid = _fresh_chat_thread("E2E send-flow enter key")
    detail = ThreadDetailPage(page, frontend_base_url)
    detail.go(tid)

    expect(detail.compose).to_be_visible(timeout=10_000)
    detail.compose.fill("ping")
    detail.compose.press("Enter")

    detail.wait_for_done(timeout=20_000)


@pytest.mark.integration
@pytest.mark.ui
def test_thread_pinned_snapshot_context_renders(page, frontend_base_url, threads) -> None:
    """A snapshot-pinned thread renders its synthetic first turn, not a blank/Loading page."""
    from apps.threads.models import Thread

    pinned = Thread.objects.filter(title="E2E pinned thread").first()
    first_msg = pinned.messages.order_by("id").first() if pinned else None
    if first_msg is None:
        pytest.skip("pinned thread has no synthetic message (seed has no ready snapshot)")

    detail = ThreadDetailPage(page, frontend_base_url)
    detail.go(pinned.id)

    # The synthetic snapshot turn must be in the DOM (not stuck on "Loading thread…").
    expect(detail.message(first_msg.id)).to_be_visible(timeout=10_000)
    expect(page.get_by_text("Loading thread")).to_have_count(0)


@pytest.mark.integration
@pytest.mark.ui
def test_thread_stop_midstream_halts(page, frontend_base_url, threads, scenario) -> None:
    """Stop during a live stream flips the message off 'streaming' (Stop button goes away).

    Uses the ``slow-stream`` scenario (12 chunks x 0.4s) so there's a real
    mid-stream window — the X-E2E-Scenario header now reaches the worker, so the
    stream is genuinely slow. The /stop/ endpoint requires the message to still
    be streaming, then broadcasts error/cancelled, which clears the Stop button.
    """
    scenario.use("slow-stream")
    tid = _fresh_chat_thread("E2E stop midstream")
    detail = ThreadDetailPage(page, frontend_base_url)
    detail.go(tid)
    detail.send("stream slowly please")
    expect(detail.stop_btn).to_be_visible(timeout=15_000)
    detail.stop()
    expect(detail.stop_btn).to_be_hidden(timeout=15_000)
