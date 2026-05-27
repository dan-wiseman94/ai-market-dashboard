from apps.snapshots.serializer import _render_events, _title


def test_events_title():
    assert _title("events") == "Upcoming events"


def test_render_events_lists_earnings_and_macro():
    payload = {
        "earnings": [
            {"ticker": "NVDA", "days_until": 2, "when_hint": "amc", "detail": {"eps_est": 0.84}}
        ],
        "macro": [{"title": "CPI", "days_until": 5}],
    }
    out = _render_events(payload)
    assert "NVDA earnings in 2d" in out
    assert "AMC" in out
    assert "est EPS 0.84" in out
    assert "CPI in 5d" in out


def test_render_events_empty():
    assert "_(none" in _render_events({"earnings": [], "macro": []})
