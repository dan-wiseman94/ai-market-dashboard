from unittest.mock import patch

import pytest
from django.test import override_settings

from apps.profiles.models import TradingProfile
from apps.snapshots.services import capture


@pytest.mark.django_db
@override_settings(CELERY_TASK_ALWAYS_EAGER=True, CELERY_TASK_EAGER_PROPAGATES=True)
def test_capture_scrubs_credentials_from_section_error():
    p = TradingProfile.objects.create(name="P", style="x")
    leaky = RuntimeError(
        "403 Client Error for url: https://finnhub.io/api/v1/news?symbol=SPY&token=SECRETKEY99"
    )

    with patch("apps.snapshots.services.fetch_quotes", side_effect=leaky):
        snap = capture(
            profile=p,
            objective="",
            includes=["quotes"],
            notes="",
            source="manual",
            watchlist_tickers=["SPY"],
        )

    err = snap.sections.get(kind="quotes").error
    assert "SECRETKEY99" not in err
    assert "token=***" in err
    assert "403 Client Error" in err  # diagnostics survive the scrub
