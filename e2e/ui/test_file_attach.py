"""File attach flow — the FileAttachPanel inside a thread.

The real file UI (the dead /files route POM is xfail'd elsewhere) is the
"Attach a file" disclosure in the thread detail: it LISTS previously-uploaded
UserFiles and attaches one to the thread (there is no upload control here).
Seed a UserFile, expand the panel, attach it, and assert the resulting user
Message ("Please review this document.") lands in the thread.
"""

from __future__ import annotations

import json

import pytest
from playwright.sync_api import expect

from e2e.pages.thread_detail import ThreadDetailPage


@pytest.mark.integration
@pytest.mark.ui
def test_attach_file_to_thread(page, frontend_base_url, threads) -> None:
    from apps.threads.models import Message, Thread, UserFile

    uf, _ = UserFile.objects.update_or_create(
        anthropic_id="file_e2e_attach",
        defaults={"filename": "e2e-research.pdf", "kind": "research", "mime": "application/pdf"},
    )
    thread = Thread.objects.filter(title="E2E plain thread").first()
    assert thread is not None
    before = Message.objects.filter(thread=thread).count()

    detail = ThreadDetailPage(page, frontend_base_url)
    detail.go(thread.id)
    detail.expect_error_boundary_absent()

    # Expand the "Attach a file" disclosure; the files query then lists the seeded file.
    page.get_by_text("Attach a file").click()
    row = page.get_by_test_id(f"file-row-{uf.id}")
    expect(row).to_be_visible(timeout=10_000)
    with page.expect_response(
        lambda r: "/attach-file/" in r.url and r.request.method == "POST"
    ):
        row.get_by_role("button", name="Attach").click()

    # The UI click (panel + Attach button) drove the attach: a new Message
    # carrying the file + the default prompt ("Please review this document.")
    # landed in the thread. (The thread detail surfaces an attach message as a
    # document attachment rather than rendering the prompt as plain text, so we
    # assert the backend effect of the UI action.)
    assert Message.objects.filter(thread=thread).count() > before
    contents = [json.dumps(m.content) for m in Message.objects.filter(thread=thread)]
    assert any(
        "Please review this document" in c for c in contents
    ), "the attached message carries the prompt"
