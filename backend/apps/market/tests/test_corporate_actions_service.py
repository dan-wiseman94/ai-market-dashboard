"""apps.market.services.corporate_actions — Finnhub split/dividend fetch + parse."""

from __future__ import annotations

from datetime import UTC, date, datetime
from unittest.mock import patch

import pytest

from apps.market.models import CorporateAction
from apps.market.services import corporate_actions as ca


class TestSplitParsing:
    def test_forward_split_ratio_is_to_over_from(self, db) -> None:
        rows = [{"symbol": "nvda", "date": "2026-02-01", "fromFactor": 1, "toFactor": 10}]
        [obj] = ca._upsert_splits(rows)
        assert obj.ticker == "NVDA"
        assert obj.kind == "split"
        assert obj.ex_date == date(2026, 2, 1)
        assert float(obj.ratio) == pytest.approx(10.0)

    def test_reverse_split_ratio_below_one(self, db) -> None:
        rows = [{"symbol": "AAPL", "date": "2026-02-01", "fromFactor": 10, "toFactor": 1}]
        [obj] = ca._upsert_splits(rows)
        assert float(obj.ratio) == pytest.approx(0.1)

    def test_skips_inert_one_to_one_and_malformed(self, db) -> None:
        rows = [
            {"symbol": "X", "date": "2026-02-01", "fromFactor": 1, "toFactor": 1},  # no-op
            {"symbol": "", "date": "2026-02-01", "fromFactor": 1, "toFactor": 2},  # no symbol
            {"symbol": "Y", "date": None, "fromFactor": 1, "toFactor": 2},  # no date
            {"symbol": "Z", "date": "2026-02-01", "fromFactor": 0, "toFactor": 2},  # zero factor
        ]
        assert ca._upsert_splits(rows) == []
        assert CorporateAction.objects.count() == 0


class TestDividendParsing:
    def test_dividend_amount_and_exdate(self, db) -> None:
        rows = [{"symbol": "aapl", "date": "2026-02-01", "amount": 0.25, "currency": "USD"}]
        [obj] = ca._upsert_dividends(rows)
        assert obj.ticker == "AAPL"
        assert obj.kind == "dividend"
        assert obj.ex_date == date(2026, 2, 1)
        assert float(obj.amount) == pytest.approx(0.25)

    def test_skips_missing_or_nonpositive_amount(self, db) -> None:
        rows = [
            {"symbol": "X", "date": "2026-02-01", "amount": None},
            {"symbol": "Y", "date": "2026-02-01", "amount": 0},
            {"symbol": "Z", "date": "2026-02-01"},
        ]
        assert ca._upsert_dividends(rows) == []


class TestFetchAndIdempotency:
    def test_fetch_splits_upserts_and_is_idempotent(self, db) -> None:
        rows = [{"symbol": "NVDA", "date": "2026-02-01", "fromFactor": 1, "toFactor": 10}]
        with (
            patch.object(ca, "_finnhub_api_key", return_value="k"),
            patch.object(ca, "_finnhub_get_list", return_value=rows) as get,
            patch("apps.market.cache.get_or_fetch", side_effect=lambda *a, fetcher, **k: fetcher()),
        ):
            ca.fetch_splits(["NVDA"])
            ca.fetch_splits(["NVDA"])
        assert get.call_count == 2
        assert CorporateAction.objects.filter(kind="split", ticker="NVDA").count() == 1

    def test_no_key_returns_empty_without_network(self, db) -> None:
        with patch.object(ca, "_finnhub_api_key", return_value=None):
            assert ca.fetch_splits(["NVDA"]) == []
            assert ca.fetch_dividends(["NVDA"]) == []


class TestCorporateActionsFor:
    def test_window_is_exclusive_start_inclusive_end(self, db) -> None:
        for d in (date(2026, 1, 5), date(2026, 1, 20), date(2026, 3, 6), date(2026, 4, 1)):
            CorporateAction.objects.create(
                source="test",
                external_id=f"SPLIT:T:{d}",
                kind="split",
                ticker="T",
                ex_date=d,
                ratio=2.0,
            )
        start = datetime(2026, 1, 5, 15, 0, tzinfo=UTC)
        end = datetime(2026, 3, 6, 15, 0, tzinfo=UTC)
        got = {a.ex_date for a in ca.corporate_actions_for("T", start, end)}
        # 01-05 excluded (== start.date()); 03-06 included (== end.date()); 04-01 excluded.
        assert got == {date(2026, 1, 20), date(2026, 3, 6)}

    def test_skips_ondemand_fill_when_actions_exist(self, db) -> None:
        CorporateAction.objects.create(
            source="test",
            external_id="SPLIT:T:x",
            kind="split",
            ticker="T",
            ex_date=date(2026, 2, 1),
            ratio=2.0,
        )
        start = datetime(2026, 1, 5, tzinfo=UTC)
        end = datetime(2026, 3, 6, tzinfo=UTC)
        with patch.object(ca, "fetch_splits") as fs, patch.object(ca, "fetch_dividends") as fd:
            ca.corporate_actions_for("T", start, end)
        fs.assert_not_called()
        fd.assert_not_called()

    def test_ondemand_fill_failure_degrades_to_stored(self, db) -> None:
        # No stored actions for COLD -> fill is attempted; a raising fetch must not propagate.
        start = datetime(2026, 1, 5, tzinfo=UTC)
        end = datetime(2026, 3, 6, tzinfo=UTC)
        with (
            patch.object(ca, "fetch_splits", side_effect=RuntimeError("boom")),
            patch.object(ca, "fetch_dividends"),
        ):
            assert ca.corporate_actions_for("COLD", start, end) == []
