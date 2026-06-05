# Test fixture for dashboard-safe-empty-dict-default. Run: semgrep --test --config <dir>
def _fixture(_safe, get_theses, get_triggers, get_events):
    # ruleid: dashboard-safe-empty-dict-default
    a = _safe(get_theses, {})
    # ok: dashboard-safe-empty-dict-default
    b = _safe(get_triggers, {"armed_count": 0, "latest_firings": []})
    # ok: dashboard-safe-empty-dict-default
    c = _safe(get_events, [])
    return a, b, c
