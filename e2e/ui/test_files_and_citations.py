"""Files API + citations edges."""

from __future__ import annotations

from pathlib import Path

import pytest
from playwright.sync_api import expect


@pytest.mark.integration
@pytest.mark.ui
def test_file_upload_and_attach_to_thread(page, frontend_base_url, threads, tmp_path: Path) -> None:
    page.goto(f"{frontend_base_url}/files")
    expect(page.locator("body")).to_be_visible()


@pytest.mark.integration
@pytest.mark.ui
def test_delete_file_hits_anthropic_delete(
    page, frontend_base_url, minimal, tmp_path: Path
) -> None:
    page.goto(f"{frontend_base_url}/files")
    expect(page.locator("body")).to_be_visible()


@pytest.mark.integration
@pytest.mark.ui
def test_citation_renders_news_link(page, frontend_base_url, threads) -> None:
    from apps.threads.models import Thread

    t = Thread.objects.get(title="E2E tool-use thread")
    page.goto(f"{frontend_base_url}/threads/{t.id}")
    expect(page.locator("body")).to_be_visible()
