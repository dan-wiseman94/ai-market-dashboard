"""files-upload-fail scenario actually injects a 500 (and mock mode no longer
hits the live Anthropic Files API)."""

import io
from unittest.mock import patch

import pytest

from apps.core.mocks import reset_scenario, set_scenario


def test_upload_raises_under_files_upload_fail():
    from apps.threads.files_service import upload_to_anthropic

    with patch("apps.core.mocks.is_mock_mode", return_value=True):
        set_scenario("files-upload-fail")
        try:
            with pytest.raises(RuntimeError, match="files_upload_500"):
                upload_to_anthropic(io.BytesIO(b"x"), "f.txt", "text/plain")
        finally:
            reset_scenario()


def test_upload_returns_mock_id_under_default():
    from apps.threads.files_service import upload_to_anthropic

    with patch("apps.core.mocks.is_mock_mode", return_value=True):
        reset_scenario()
        file_id, size = upload_to_anthropic(io.BytesIO(b"hello"), "f.txt", "text/plain")
    assert file_id.startswith("mock-file-")
    assert isinstance(size, int)


def test_delete_is_noop_under_mock():
    from apps.threads.files_service import delete_from_anthropic

    with patch("apps.core.mocks.is_mock_mode", return_value=True):
        reset_scenario()
        # Must not touch the real Anthropic client (no key configured in tests).
        delete_from_anthropic("mock-file-id")
