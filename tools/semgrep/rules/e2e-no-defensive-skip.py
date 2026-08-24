# Test fixture for e2e-no-defensive-skip. Run: semgrep --test --config <dir>
import pytest


def test_reconnect_replays_buffered_events(events):
    if not events:
        # ruleid: e2e-no-defensive-skip
        pytest.skip("no events buffered yet")


def test_notification_fires(fired, reason):
    if not fired:
        # ruleid: e2e-no-defensive-skip
        pytest.skip(reason=reason)


def test_reconnect_asserts_instead(events):
    # ok: e2e-no-defensive-skip
    assert events, "expected buffered events after reconnect"


def test_hard_failure_is_fine(fired):
    if not fired:
        # ok: e2e-no-defensive-skip
        pytest.fail("notification never fired")
