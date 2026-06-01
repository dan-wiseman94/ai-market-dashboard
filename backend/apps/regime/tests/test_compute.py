import pytest

from apps.observer.models import Notification
from apps.regime.models import RegimeReading
from apps.regime.services import compute

pytestmark = pytest.mark.django_db

RISK_OFF_INPUTS = {
    "vix_last": 24.0, "vix_percentile": 0.8, "spx_ma_spread": -3.0, "spx_dist_50": -2.0,
    "breadth": {"$ADVN": 700, "$DECN": 2000}, "sector_returns": {}, "t10y2y": -0.2, "tnx_change": 0.05,
}
RISK_ON_INPUTS = {
    "vix_last": 12.0, "vix_percentile": 0.2, "spx_ma_spread": 4.0, "spx_dist_50": 3.0,
    "breadth": {"$ADVN": 2200, "$DECN": 700}, "sector_returns": {}, "t10y2y": 0.5, "tnx_change": -0.03,
}


def test_compute_and_store_persists_classified_reading(monkeypatch):
    monkeypatch.setattr(compute, "gather_inputs", lambda: RISK_OFF_INPUTS)
    monkeypatch.setattr(compute, "regime_narrative", lambda *a, **k: "")
    reading = compute.compute_and_store()
    assert reading.composite == "Risk-Off"
    assert reading.axes["volatility"] == "Elevated"
    assert RegimeReading.objects.count() == 1


def test_change_fires_notification(monkeypatch):
    monkeypatch.setattr(compute, "regime_narrative", lambda *a, **k: "")
    monkeypatch.setattr(compute, "gather_inputs", lambda: RISK_ON_INPUTS)
    compute.compute_and_store()  # first reading: Risk-On, no prior -> no notify
    assert Notification.objects.filter(kind="regime").count() == 0
    monkeypatch.setattr(compute, "gather_inputs", lambda: RISK_OFF_INPUTS)
    second = compute.compute_and_store()  # flip -> notify
    assert second.composite == "Risk-Off"
    notes = Notification.objects.filter(kind="regime")
    assert notes.count() == 1
    assert "Risk-On" in notes.first().title and "Risk-Off" in notes.first().title


def test_no_change_no_notification(monkeypatch):
    monkeypatch.setattr(compute, "regime_narrative", lambda *a, **k: "")
    monkeypatch.setattr(compute, "gather_inputs", lambda: RISK_ON_INPUTS)
    compute.compute_and_store()
    compute.compute_and_store()  # same composite -> no notify
    assert Notification.objects.filter(kind="regime").count() == 0
    assert RegimeReading.objects.count() == 2
