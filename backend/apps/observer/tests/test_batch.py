"""Batch-mode observer schedules submit a Messages Batch for their watchlist
instead of running per-ticker streaming. Batch results must land in the cost
ledger (AIRun at the discounted batch rate) and batch requests must carry the
captured snapshot's per-ticker market data."""

from __future__ import annotations

from decimal import Decimal
from unittest.mock import MagicMock, patch

import pytest

from apps.observer.services import batch as batch_service
from apps.profiles.models import TradingProfile
from apps.secrets.models import ProviderConfig


@pytest.fixture
def provider_cfg(db) -> ProviderConfig:
    cfg = ProviderConfig.objects.create(
        provider="claude",
        enabled=True,
        default_model="claude-opus-4-8",
    )
    cfg.api_key = "sk-test"
    cfg.save()
    return cfg


@pytest.fixture
def batch_schedule(db, provider_cfg):
    from apps.observer.models import ObserverSchedule

    profile = TradingProfile.objects.create(
        name="p",
        style="s",
        default_provider="claude",
    )
    return ObserverSchedule.objects.create(
        name="overnight",
        profile=profile,
        objective_template="overnight review",
        use_batch=True,
        market_hours_only=False,
        default_watchlist_tickers=["AAPL", "MSFT", "NVDA"],
    )


def _succeeded_result(ticker: str, text: str, *, input_tokens: int, output_tokens: int):
    block = MagicMock()
    block.type = "text"
    block.text = text
    result = MagicMock(custom_id=ticker)
    result.result.type = "succeeded"
    result.result.message.content = [block]
    result.result.message.model = "claude-opus-4-8"
    result.result.message.usage = MagicMock(
        input_tokens=input_tokens,
        output_tokens=output_tokens,
        cache_read_input_tokens=0,
        cache_creation_input_tokens=0,
    )
    return result


def test_submit_batch_creates_one_request_per_ticker(db, batch_schedule) -> None:
    fake = MagicMock(id="batch_abc123")
    with patch.object(batch_service, "_anthropic_client") as c:
        c.return_value.messages.batches.create.return_value = fake
        batch_id = batch_service.submit_watchlist_batch(batch_schedule.id)
    assert batch_id == "batch_abc123"
    call = c.return_value.messages.batches.create.call_args
    reqs = call.kwargs["requests"]
    assert len(reqs) == 3
    assert {r["custom_id"] for r in reqs} == {"AAPL", "MSFT", "NVDA"}


def test_submit_batch_grounds_requests_in_snapshot_data(db, batch_schedule) -> None:
    """Each request must carry the ticker's captured market data — otherwise the
    'observations' come from training data, ungrounded in the capture paid for."""
    from apps.snapshots.models import Snapshot, SnapshotSection

    snap = Snapshot.objects.create(profile=batch_schedule.profile, status="ready")
    SnapshotSection.objects.create(
        snapshot=snap,
        kind="quotes",
        status="done",
        payload={"data": {"AAPL": {"last": 180.5, "pct_change": 1.2}}},
    )
    SnapshotSection.objects.create(
        snapshot=snap,
        kind="ohlc",
        status="done",
        payload={
            "data": {
                "ticker": "AAPL",
                "timeframe": "1d",
                "bars": [{"open": 178, "close": 180.5}],
            }
        },
    )

    fake = MagicMock(id="batch_xyz")
    with patch.object(batch_service, "_anthropic_client") as c:
        c.return_value.messages.batches.create.return_value = fake
        batch_service.submit_watchlist_batch(batch_schedule.id, snapshot_id=snap.id)

    reqs = c.return_value.messages.batches.create.call_args.kwargs["requests"]
    by_ticker = {r["custom_id"]: r["params"]["messages"][0]["content"] for r in reqs}
    assert "180.5" in by_ticker["AAPL"]
    assert "Market data" in by_ticker["AAPL"]
    assert "Recent OHLC" in by_ticker["AAPL"]
    # No captured data for MSFT — its request degrades to the bare prompt.
    assert "Market data" not in by_ticker["MSFT"]


def test_submit_batch_rejects_non_claude_provider(db, batch_schedule) -> None:
    ProviderConfig.objects.create(provider="openai", enabled=True)
    batch_schedule.override_provider = "openai"
    batch_schedule.save(update_fields=["override_provider"])
    with pytest.raises(ValueError, match="requires a Claude provider"):
        batch_service.submit_watchlist_batch(batch_schedule.id)


def test_poll_batch_rejects_non_claude_provider(db, batch_schedule) -> None:
    ProviderConfig.objects.create(provider="local", enabled=True)
    batch_schedule.override_provider = "local"
    batch_schedule.save(update_fields=["override_provider"])
    with pytest.raises(ValueError, match="requires a Claude provider"):
        batch_service.poll_batch(batch_schedule.id, "batch_abc123")


def test_poll_batch_writes_results_to_thread(db, batch_schedule) -> None:
    from apps.observer.services.threads import get_or_create_observer_thread
    from apps.threads.models import Message

    fake_aapl = _succeeded_result("AAPL", "AAPL looks OK", input_tokens=1000, output_tokens=500)
    fake_msft = _succeeded_result("MSFT", "MSFT flat", input_tokens=900, output_tokens=400)

    fake_nvda = MagicMock(custom_id="NVDA")
    fake_nvda.result.type = "errored"
    fake_nvda.result.error.message = "rate_limit"

    results = [fake_aapl, fake_msft, fake_nvda]

    with patch.object(batch_service, "_anthropic_client") as c:
        c.return_value.messages.batches.retrieve.return_value = MagicMock(
            processing_status="ended",
        )
        c.return_value.messages.batches.results.return_value = iter(results)
        moved = batch_service.poll_batch(batch_schedule.id, "batch_abc123")

    assert moved == 3
    thread = get_or_create_observer_thread(batch_schedule.profile)
    msgs = list(Message.objects.filter(thread=thread, role="assistant").order_by("id"))
    assert len(msgs) == 3
    assert "AAPL" in msgs[0].content["text"]
    assert msgs[2].status == "failed"


def test_poll_batch_records_airun_per_result_at_batch_rate(db, batch_schedule) -> None:
    """Batch spend must land in the AIRun ledger (it is what check_daily_cap /
    check_monthly_cap and /api/costs sum) at the 50%-discounted batch rate."""
    from apps.ai.cost import cost_usd_for
    from apps.ai.types import TokenUsage
    from apps.threads.models import AIRun

    fake_aapl = _succeeded_result("AAPL", "AAPL looks OK", input_tokens=1000, output_tokens=500)
    fake_nvda = MagicMock(custom_id="NVDA")
    fake_nvda.result.type = "errored"
    fake_nvda.result.error.message = "rate_limit"

    with patch.object(batch_service, "_anthropic_client") as c:
        c.return_value.messages.batches.retrieve.return_value = MagicMock(
            processing_status="ended",
        )
        c.return_value.messages.batches.results.return_value = iter([fake_aapl, fake_nvda])
        batch_service.poll_batch(batch_schedule.id, "batch_abc123")

    runs = list(AIRun.objects.order_by("id"))
    assert len(runs) == 2

    done = runs[0]
    assert done.status == "done"
    assert done.provider == "claude"
    assert done.model == "claude-opus-4-8"
    assert done.input_tokens == 1000
    assert done.output_tokens == 500
    expected = (
        cost_usd_for(
            "claude",
            "claude-opus-4-8",
            TokenUsage(input_tokens=1000, output_tokens=500),
        )
        * Decimal("0.5")
    ).quantize(Decimal("0.000001"))
    assert done.cost_usd == expected
    assert done.cost_usd > 0
    assert done.message is not None  # linked to the observation Message

    failed = runs[1]
    assert failed.status == "failed"
    assert failed.error == "rate_limit"
    assert failed.input_tokens == 0
    assert not failed.cost_usd


@pytest.mark.django_db
def test_batch_client_applies_resilience_kwargs(provider_cfg) -> None:
    """The batch client must apply the shared env-configured retry/timeout
    (AI_PROVIDER_MAX_RETRIES / AI_PROVIDER_TIMEOUT_SECONDS), not SDK defaults."""
    from django.test import override_settings

    captured: dict = {}

    class _FakeAnthropic:
        def __init__(self, **kw):
            captured.update(kw)

    with (
        override_settings(AI_PROVIDER_MAX_RETRIES=4, AI_PROVIDER_TIMEOUT_SECONDS=30.0),
        patch("apps.observer.services.batch.Anthropic", _FakeAnthropic),
    ):
        batch_service._anthropic_client("claude")

    assert captured["max_retries"] == 4
    assert captured["timeout"] == 30.0
