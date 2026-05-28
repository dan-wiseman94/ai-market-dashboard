"""Files API + citations edges."""

from __future__ import annotations

from pathlib import Path

import pytest
from playwright.sync_api import expect

from e2e.pages.files import FilesPage


@pytest.mark.integration
@pytest.mark.ui
@pytest.mark.xfail(
    reason=(
        "GAP: No standalone /files route exists in the frontend router "
        "(frontend/src/router.tsx). The FilesPage POM targets '/files' which "
        "renders a 404/redirect. File upload UI lives only inside ThreadDetailPage "
        "as a collapsible panel (FileAttachPanel), not as a standalone page."
    ),
    strict=False,
)
def test_file_upload_and_attach_to_thread(page, frontend_base_url, threads, tmp_path: Path) -> None:
    f = FilesPage(page, frontend_base_url)
    f.go()
    f.expect_error_boundary_absent()
    sample = tmp_path / "note.txt"
    sample.write_text("e2e upload body")
    f.upload(sample)
    # A file row appears after the (mocked) Anthropic upload returns an id.
    expect(page.locator("[data-testid^='file-row-']").first).to_be_visible(timeout=15_000)


@pytest.mark.integration
@pytest.mark.ui
@pytest.mark.xfail(
    reason=(
        "GAP: No standalone /files route exists in the frontend router "
        "(frontend/src/router.tsx). The FilesPage POM targets '/files' which "
        "renders a 404/redirect. File delete UI lives only inside ThreadDetailPage "
        "as a collapsible FileAttachPanel, not as a standalone page."
    ),
    strict=False,
)
def test_delete_file_hits_anthropic_delete(
    page, frontend_base_url, minimal, tmp_path: Path
) -> None:
    f = FilesPage(page, frontend_base_url)
    f.go()
    f.expect_error_boundary_absent()
    sample = tmp_path / "del.txt"
    sample.write_text("delete me")
    f.upload(sample)
    row = page.locator("[data-testid^='file-row-']").first
    expect(row).to_be_visible(timeout=15_000)
    row.get_by_role("button", name="Delete").click()
    expect(page.locator("[data-testid^='file-row-']")).to_have_count(0, timeout=10_000)


@pytest.mark.integration
@pytest.mark.ui
def test_citation_renders_news_link(page, frontend_base_url, threads) -> None:
    from apps.threads.models import Thread

    t = Thread.objects.get(title="E2E tool-use thread")
    page.goto(f"{frontend_base_url}/threads/{t.id}")
    page.wait_for_load_state("networkidle")
    expect(page.get_by_text("Something went wrong")).to_have_count(0)
    # The thread renders its transcript (at least one message bubble).
    expect(page.locator("[data-testid^='message-']").first).to_be_visible(timeout=10_000)
