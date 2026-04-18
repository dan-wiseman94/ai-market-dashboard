"""Batch-mode observer schedules submit a Messages Batch for their watchlist
instead of running per-ticker streaming."""
from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from apps.observer.services import batch as batch_service
from apps.profiles.models import TradingProfile
from apps.secrets.models import ProviderConfig


@pytest.fixture
def provider_cfg(db) -> ProviderConfig:
    cfg = ProviderConfig.objects.create(
        provider="claude", enabled=True, default_model="claude-opus-4-7",
    )
    cfg.api_key = "sk-test"
    cfg.save()
    return cfg


@pytest.fixture
def batch_schedule(db, provider_cfg):
    from apps.observer.models import ObserverSchedule
    profile = TradingProfile.objects.create(
        name="p", style="s", default_provider="claude",
    )
    return ObserverSchedule.objects.create(
        name="overnight", profile=profile, objective_template="overnight review",
        use_batch=True, market_hours_only=False,
        default_watchlist_tickers=["AAPL", "MSFT", "NVDA"],
    )


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


def test_poll_batch_writes_results_to_thread(db, batch_schedule) -> None:
    from apps.observer.services.threads import get_or_create_observer_thread
    from apps.threads.models import Message

    fake_aapl_block = MagicMock()
    fake_aapl_block.type = "text"
    fake_aapl_block.text = "AAPL looks OK"
    fake_aapl = MagicMock(custom_id="AAPL")
    fake_aapl.result.type = "succeeded"
    fake_aapl.result.message.content = [fake_aapl_block]

    fake_msft_block = MagicMock()
    fake_msft_block.type = "text"
    fake_msft_block.text = "MSFT flat"
    fake_msft = MagicMock(custom_id="MSFT")
    fake_msft.result.type = "succeeded"
    fake_msft.result.message.content = [fake_msft_block]

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
