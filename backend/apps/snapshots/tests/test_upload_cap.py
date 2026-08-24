"""Drift gate: the client-upload size cap has exactly one knob.

Django's body-buffer guard (DATA_UPLOAD_MAX_MEMORY_SIZE) fires before the view's
own size check can run, so the two limits must be the same value or oversized
PNGs stop producing the structured 413 response.
"""

from django.conf import settings

from apps.snapshots.services.screenshot import MAX_BYTES


def test_upload_cap_matches_django_body_buffer_guard():
    assert MAX_BYTES == settings.DATA_UPLOAD_MAX_MEMORY_SIZE
    assert MAX_BYTES == 5 * 1024 * 1024
