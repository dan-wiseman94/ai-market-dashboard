import datetime as dt

import pytest
from rest_framework.test import APIClient

from apps.book.models import BookSnapshot

pytestmark = pytest.mark.django_db


def test_current_empty_null():
    assert APIClient().get("/api/book/current/").json() is None


def test_current_returns_latest():
    BookSnapshot.objects.create(as_of_date=dt.date(2026, 6, 1), concentration={"hhi": 0.4})
    body = APIClient().get("/api/book/current/").json()
    assert body["concentration"]["hhi"] == 0.4
    assert "id" in body


def test_recompute_invokes_compute(monkeypatch):
    from apps.book import views

    monkeypatch.setattr(
        views,
        "compute_and_store_book",
        lambda: BookSnapshot.objects.create(as_of_date=dt.date(2026, 6, 2)),
    )
    resp = APIClient().post("/api/book/recompute/")
    assert resp.status_code == 200
    # The stub ran (its row exists) and the response serializes that snapshot.
    assert BookSnapshot.objects.filter(as_of_date=dt.date(2026, 6, 2)).exists()
    assert resp.json()["as_of_date"] == "2026-06-02"


class TestHistoryList:
    """GET /api/book/ feeds the trend view: light rows, bounded, orderable."""

    @staticmethod
    def _seed(n: int) -> None:
        for i in range(n):
            BookSnapshot.objects.create(
                as_of_date=dt.date(2026, 6, 1) + dt.timedelta(days=i),
                exposures=[{"ticker": "SPY"}, {"ticker": "QQQ"}],
                concentration={"hhi": 0.1 * i, "top_n_share": 0.5, "net_long": 1.0},
                clusters=[{"members": ["SPY", "QQQ"]}],
                near_invalidation=[{"ticker": "SPY"}],
                regime_fit={"regime": "Risk-On", "alignment": "aligned"},
                var_beta={"available": True, "portfolio": {"diversified_var_usd": 100.0 + i}},
                narrative="a long narrative that a sparkline never needs",
            )

    def test_row_carries_the_sparkline_scalars_and_not_the_arrays(self, db):
        self._seed(1)
        row = APIClient().get("/api/book/").json()[0]
        assert row["hhi"] == 0.0
        assert row["diversified_var_usd"] == 100.0
        assert row["alignment"] == "aligned"
        assert row["position_count"] == 2
        assert row["cluster_count"] == 1
        assert row["near_invalidation_count"] == 1
        assert "exposures" not in row
        assert "narrative" not in row

    def test_metrics_absent_from_the_stored_blob_are_null_not_zero(self, db):
        BookSnapshot.objects.create(as_of_date=dt.date(2026, 7, 1))
        row = APIClient().get("/api/book/").json()[0]
        assert row["hhi"] is None
        assert row["diversified_var_usd"] is None
        assert row["regime"] is None

    def test_default_order_is_newest_first(self, db):
        self._seed(3)
        dates = [r["as_of_date"] for r in APIClient().get("/api/book/").json()]
        assert dates == sorted(dates, reverse=True)

    def test_order_asc_returns_oldest_first(self, db):
        self._seed(3)
        dates = [r["as_of_date"] for r in APIClient().get("/api/book/?order=asc").json()]
        assert dates == sorted(dates)

    def test_limit_caps_the_window(self, db):
        self._seed(5)
        assert len(APIClient().get("/api/book/?limit=2").json()) == 2

    def test_non_numeric_limit_falls_back_to_the_default(self, db):
        self._seed(3)
        assert len(APIClient().get("/api/book/?limit=abc").json()) == 3

    def test_since_and_until_filter_on_as_of_date(self, db):
        self._seed(5)  # 2026-06-01 .. 2026-06-05
        rows = APIClient().get("/api/book/?since=2026-06-02&until=2026-06-04").json()
        assert [r["as_of_date"] for r in rows] == ["2026-06-04", "2026-06-03", "2026-06-02"]

    def test_detail_still_carries_the_full_xray(self, db):
        self._seed(1)
        snap_id = APIClient().get("/api/book/").json()[0]["id"]
        body = APIClient().get(f"/api/book/{snap_id}/").json()
        assert body["exposures"]
        assert body["narrative"]
