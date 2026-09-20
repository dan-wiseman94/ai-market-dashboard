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


def test_render_events_shows_detail_and_corporate_actions():
    payload = {
        "earnings": [
            {
                "ticker": "NVDA",
                "days_until": 3,
                "when_hint": "amc",
                "detail": {"eps_est": 1.25, "eps_actual": 1.3, "rev_est": 46_000_000_000},
            }
        ],
        "macro": [
            {
                "title": "CPI YoY",
                "days_until": 5,
                # Producer shape (apps.market.services.events._upsert_macro): forecast/prior/actual.
                "detail": {"forecast": 2.9, "prior": 3.1, "actual": None},
            }
        ],
        "corporate_actions": [
            {
                "ticker": "AAPL",
                "kind": "dividend",
                "ex_date": "2026-09-26",
                "ratio": None,
                "amount": 0.26,
            }
        ],
    }
    out = _render_events(payload)
    assert "est EPS 1.25" in out and "last actual 1.3" in out and "est rev" in out
    assert "CPI YoY in 5d (est 2.9, prev 3.1)" in out
    assert "- AAPL dividend $0.26 ex 2026-09-26" in out


def test_render_events_empty_with_no_corporate_actions_key():
    # corporate_actions is a newer key; payloads captured before this change
    # (or fetcher failures) may omit it entirely — must not raise.
    assert "_(none" in _render_events({"earnings": [], "macro": []})


def test_render_events_all_empty_including_corporate_actions():
    assert "_(none" in _render_events({"earnings": [], "macro": [], "corporate_actions": []})


def test_render_events_split_branch():
    payload = {
        "earnings": [],
        "macro": [],
        "corporate_actions": [
            {
                "ticker": "NVDA",
                "kind": "split",
                "ex_date": "2026-10-01",
                "ratio": 10.0,
                "amount": None,
            },
        ],
    }
    out = _render_events(payload)
    assert "- NVDA split 10.0 ex 2026-10-01" in out


def test_render_events_skips_malformed_corporate_action_row():
    # kind says dividend but amount is missing — must not fabricate "dividend $None".
    payload = {
        "earnings": [],
        "macro": [],
        "corporate_actions": [
            {
                "ticker": "AAPL",
                "kind": "dividend",
                "ex_date": "2026-09-26",
                "ratio": None,
                "amount": None,
            },
        ],
    }
    out = _render_events(payload)
    assert "AAPL" not in out
    assert "None" not in out
