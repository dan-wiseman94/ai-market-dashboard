# M16 P2 — Snapshot `signals` Section + `strategy_tags` Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Give `TradingProfile` a validated `strategy_tags` field and add a new snapshot section kind `signals` whose fetcher routes the P1 signal engine's families by those tags, with full renderer/prune/diff support and FE profile-form + picker wiring.

**Architecture:** Routing lives entirely in the new section fetcher (`fetch_signals_section` in `_FETCHERS`): it loads `snap.profile.strategy_tags` and computes only the tagged families via the P1 engine — the three independent includes-resolution call sites and the briefing's hard-coded list stay untouched, so trigger-/observer-fired snapshots pick the section up through the existing `default_includes` flow. The section then plugs into the four existing per-kind registries: `_RENDERERS`/`_title` (AI markdown), `token_budget._PRUNE_ORDER` (budget trimming), and `diff.py::_diff_one` (diff-mode observers + coverage). FE work is pure threading: the hand-written profile type/draft/form (four hand-maintained spots) plus the two hand-coded section-kind picker lists.

**Tech Stack:** Django 6 + DRF (JSONField, ModelSerializer validation), Celery worker (capture loop), pytest + pytest-django + unittest.mock, React + TanStack Query, vitest + @testing-library/react.

**Spec:** docs/superpowers/specs/2026-07-05-strategy-signals-design.md (§4, §8.1, profile parts of §8.2)
**Interface contract (names are law):** the M16 pinned cross-plan interface contract — engine/bundle names reproduced verbatim in each task's Interfaces block below.

**P1 is merged.** `apps/market/services/signals/` (engine.py, bundles.py, family modules) exists on `main` with exactly the contract signatures. Do NOT stub or re-implement any of it; import it.

## Global Constraints

Repo global constraints (from the pinned contract):

- Everything runs in Docker. One backend test:
  `docker compose exec web pytest apps/<app>/tests/test_<x>.py::<name> -v` (WORKDIR /app/backend).
  One FE test: `docker compose exec frontend pnpm exec vitest run <path> -t "name"`. Lint: `make lint`.
- Never set MOCK_EXTERNAL on the dev stack.
- Migrations gated by `make check-migrations`; beat tasks inventoried in `apps/core/scheduled_tasks.py`
  in the SAME commit (drift gate); worker/beat need `docker compose restart worker beat` after task changes.
- OpenAPI: `make schema` regenerates backend/schema.yml (commit it); `pnpm gen:api` runs on the HOST
  (broken inside the frontend container).
- DRF exposes FK ids as `*_id`. Section terminal state "done"; parent Snapshot "ready".
- Never log provider exceptions raw when the key rides in the URL — use `safe_err`.
- New FE components ship with co-located `*.stories.tsx` (storyless ratchet at ceiling) and a vitest test.
- Conventional commits (`feat(market):`, `feat(observer):`, `feat(frontend):`, `test:`, `docs:`); frequent.
- CI gate runs pytest `-p no:randomly`; coverage floors backend 86 branch, FE 80/74/77/82; ruff C901 ≤15.

P2 phase-specific constraints:

- `TradingProfileSerializer.Meta.fields` is an **explicit list** — the new field MUST be appended there by hand or it is silently absent from the API (the model-only `skills` field is standing proof).
- Do NOT add a `save()` backfill for `strategy_tags` (unlike `default_includes`): **empty tags = all four families** is a meaningful state, not a missing one.
- Section kind string is `"signals"` (7 chars; `SnapshotSection.kind` is varchar(16)). Never duplicate a kind inside any includes list — the `(snapshot, kind)` unique constraint aborts the whole capture with an IntegrityError.
- `"_market"` is a **reserved payload key** — never a ticker, never used for primary-ticker derivation (primary derivation reads only the quotes section, `apps/snapshots/primary.py`; keep it that way).
- The renderer must be **deterministic** (byte-stable for identical payloads): the observer response cache keys on prompt bytes, and Postgres jsonb round-trips do NOT preserve key order — sort every level explicitly. No now-relative text.
- `"signals"` MUST be inserted in `token_budget._PRUNE_ORDER` after `"breadth"`, before `"quotes"` (an unlisted kind is un-prunable and squeezes listed kinds out), and MUST get a `diff.py::_diff_one` branch (unregistered kinds return `""` — invisible to diff-mode observers and coverage revisions).
- Fetcher error philosophy: the fetcher does NOT catch engine errors — a raising fetcher marks only that section `failed` via the existing capture-loop semantics (no retry), and the snapshot still goes `ready` if any other section succeeded.
- Do NOT touch `observer/services/run.py`, `observer/triggers/tasks.py`, `snapshots/views.py` includes resolution, or the briefing's hard-coded `["breadth"]` list — routing is fetcher-side by design (spec §4).
- Deliberately out of P2 scope: `apps/export/serializers.py::profiles_to_json` is NOT extended (matches the existing precedent — it already omits `style`/`default_includes`/`enable_*`); no dashboard rollup section; no analytics endpoint (P4); no trigger metrics (P3).
- No new beat tasks and no new feature flags in P2 — `apps/core/scheduled_tasks.py` and `apps/core/feature_flags.py` stay untouched.
- Backend patch targets: `_FETCHERS` entries close over names imported INTO `apps.snapshots.services` — always patch `apps.snapshots.services.compute_signals` etc., never the engine module (see the rationale comment in `backend/apps/snapshots/tests/test_capture_all_sections.py:46-47`).

---

### Task 1: `TradingProfile.strategy_tags` model field + migration

**Files:**
- Modify: `backend/apps/profiles/models.py` (insert field after `skills`, which ends at line 79, before `created_at` at line 80)
- Create: `backend/apps/profiles/migrations/0011_tradingprofile_strategy_tags.py` (generated)
- Test: `backend/apps/profiles/tests/test_strategy_tags.py` (new)

**Interfaces:**
- Consumes: nothing new — `TradingProfile` as it exists (fields through `skills`, migration chain ends at `0010_alter_tradingprofile_enable_coach`).
- Produces: `TradingProfile.strategy_tags: models.JSONField(default=list, blank=True)` — Tasks 2, 4 and the FE tasks rely on this exact field name and the list-of-strings shape. Valid values are the four tags `momentum` / `mean_reversion` / `vol_options` / `positioning` (enforced at the API layer in Task 2, NOT at the model layer — ORM writes bypass validation by design, mirroring `ThesisSerializer`).

**Steps:**

- [ ] Write the failing test — create `backend/apps/profiles/tests/test_strategy_tags.py`:

```python
import pytest

from apps.profiles.models import TradingProfile


@pytest.mark.django_db
def test_strategy_tags_defaults_to_empty_list():
    p = TradingProfile.objects.create(name="Untagged", style="x")
    p.refresh_from_db()
    assert p.strategy_tags == []


@pytest.mark.django_db
def test_strategy_tags_round_trips_through_orm():
    p = TradingProfile.objects.create(
        name="Momo", style="x", strategy_tags=["momentum", "vol_options"]
    )
    p.refresh_from_db()
    assert p.strategy_tags == ["momentum", "vol_options"]


@pytest.mark.django_db
def test_save_does_not_backfill_strategy_tags():
    """Empty tags mean 'all families' — save() must NOT auto-fill them
    (unlike default_includes, which save() force-fills)."""
    p = TradingProfile.objects.create(name="Neutral", style="x", strategy_tags=[])
    p.refresh_from_db()
    assert p.strategy_tags == []
    assert p.default_includes == ["quotes", "positions", "breadth"]  # backfill still works
```

- [ ] Run it — expect failure:

```
docker compose exec web pytest apps/profiles/tests/test_strategy_tags.py -v
```

Expected: all 3 tests FAIL — `TypeError` ("'strategy_tags' is an invalid keyword argument" / "got unexpected keyword arguments") on the `create(...)` calls and `AttributeError: 'TradingProfile' object has no attribute 'strategy_tags'` on the default test.

- [ ] Minimal implementation — in `backend/apps/profiles/models.py`, insert between the `skills` field (ends line 79) and `created_at` (line 80):

```python
    strategy_tags = models.JSONField(
        default=list,
        blank=True,
        help_text="Strategy tags routing which signal families the 'signals' "
        "snapshot section computes for this profile. Empty = all four families.",
    )
```

So the tail of the field block reads:

```python
    skills = models.JSONField(
        default=list,
        blank=True,
        help_text="List of Anthropic Skill ids to attach per run. Empty = none.",
    )
    strategy_tags = models.JSONField(
        default=list,
        blank=True,
        help_text="Strategy tags routing which signal families the 'signals' "
        "snapshot section computes for this profile. Empty = all four families.",
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
```

Do NOT touch `save()` — no backfill for this field.

- [ ] Generate the migration:

```
make makemigrations
```

Expected output includes: `profiles/migrations/0011_tradingprofile_strategy_tags.py` with `+ Add field strategy_tags to tradingprofile`. The generated file should contain exactly one `migrations.AddField` op:

```python
        migrations.AddField(
            model_name="tradingprofile",
            name="strategy_tags",
            field=models.JSONField(
                blank=True,
                default=list,
                help_text="Strategy tags routing which signal families the 'signals' snapshot section computes for this profile. Empty = all four families.",
            ),
        ),
```

- [ ] Apply it and verify the drift gate:

```
make migrate
make check-migrations
```

Expected: migration applies cleanly; `check-migrations` exits 0 ("No changes detected").

- [ ] Run the test again — expect PASS:

```
docker compose exec web pytest apps/profiles/tests/test_strategy_tags.py -v
```

Expected: `3 passed`.

- [ ] Commit:

```
git add backend/apps/profiles/models.py backend/apps/profiles/migrations/0011_tradingprofile_strategy_tags.py backend/apps/profiles/tests/test_strategy_tags.py
git commit -m "feat(profiles): add strategy_tags JSONField to TradingProfile" -m "Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>"
```

---

### Task 2: expose + validate `strategy_tags` in the profiles API

**Files:**
- Modify: `backend/apps/profiles/serializers.py` (import at top; `TradingProfileSerializer.Meta.fields` list at lines 29-44; new `validate_strategy_tags` method on the serializer class)
- Test: `backend/apps/profiles/tests/test_strategy_tags_api.py` (new)

**Interfaces:**
- Consumes: `TradingProfile.strategy_tags` (JSONField, default list — Task 1). From the P1 contract (verbatim, already on main):

```python
# apps/market/services/signals/bundles.py
STRATEGY_TAGS = frozenset({"momentum", "mean_reversion", "vol_options", "positioning"})
```

- Produces: `strategy_tags` as a read/write field on `GET/POST/PATCH /api/profiles/`, list-validated against `bundles.STRATEGY_TAGS` (unknown tag or non-list → 400). FE Task 9 and the schema regen (Task 8) rely on this field being in the API payload.

**Steps:**

- [ ] Write the failing test — create `backend/apps/profiles/tests/test_strategy_tags_api.py`:

```python
import pytest
from rest_framework.test import APIClient

from apps.profiles.models import TradingProfile


@pytest.fixture
def api():
    return APIClient()


@pytest.mark.django_db
def test_create_profile_with_valid_strategy_tags(api):
    resp = api.post(
        "/api/profiles/",
        {"name": "Momo", "style": "x", "strategy_tags": ["momentum", "vol_options"]},
        format="json",
    )
    assert resp.status_code == 201
    body = resp.json()
    assert body["strategy_tags"] == ["momentum", "vol_options"]
    assert TradingProfile.objects.get(id=body["id"]).strategy_tags == [
        "momentum",
        "vol_options",
    ]


@pytest.mark.django_db
def test_strategy_tags_present_in_response_and_defaults_empty(api):
    resp = api.post("/api/profiles/", {"name": "Plain", "style": "x"}, format="json")
    assert resp.status_code == 201
    assert resp.json()["strategy_tags"] == []
    listed = api.get("/api/profiles/").json()
    assert listed[0]["strategy_tags"] == []


@pytest.mark.django_db
def test_unknown_strategy_tag_rejected_400(api):
    resp = api.post(
        "/api/profiles/",
        {"name": "Bad", "style": "x", "strategy_tags": ["momentum", "yolo"]},
        format="json",
    )
    assert resp.status_code == 400
    assert "strategy_tags" in resp.json()


@pytest.mark.django_db
def test_strategy_tags_must_be_a_list(api):
    resp = api.post(
        "/api/profiles/",
        {"name": "Bad2", "style": "x", "strategy_tags": "momentum"},
        format="json",
    )
    assert resp.status_code == 400
    assert "strategy_tags" in resp.json()


@pytest.mark.django_db
def test_patch_strategy_tags(api):
    p = TradingProfile.objects.create(name="P", style="x")
    resp = api.patch(
        f"/api/profiles/{p.id}/", {"strategy_tags": ["mean_reversion"]}, format="json"
    )
    assert resp.status_code == 200
    p.refresh_from_db()
    assert p.strategy_tags == ["mean_reversion"]
```

- [ ] Run it — expect failure:

```
docker compose exec web pytest apps/profiles/tests/test_strategy_tags_api.py -v
```

Expected: `test_create_profile_with_valid_strategy_tags` and `test_strategy_tags_present_in_response_and_defaults_empty` FAIL with `KeyError: 'strategy_tags'` (field silently absent — the exact landmine); the two rejection tests FAIL asserting 400 (got 201, unknown input silently dropped); the PATCH test FAILS asserting `["mean_reversion"]` (still `[]`).

- [ ] Minimal implementation — edit `backend/apps/profiles/serializers.py`. Add the import after the `rest_framework` import (line 5), before `from .models import ...` (line 7):

```python
from apps.market.services.signals.bundles import STRATEGY_TAGS
```

In `TradingProfileSerializer.Meta.fields` (lines 29-44), insert `"strategy_tags",` after `"default_model",`:

```python
        fields: ClassVar = [
            "id",
            "name",
            "style",
            "default_includes",
            "default_provider",
            "default_model",
            "strategy_tags",
            "enable_tools",
            "enable_thinking",
            "thinking_budget",
            "enable_memory",
            "enable_coach",
            "active",
            "created_at",
            "updated_at",
        ]
```

Then add the validator as a method on `TradingProfileSerializer` (after the `Meta` class, same indentation level as `Meta`):

```python
    def validate_strategy_tags(self, value):
        """Every entry must be a known strategy tag (bundles.STRATEGY_TAGS)."""
        if not isinstance(value, list):
            raise serializers.ValidationError("strategy_tags must be a list of tag strings.")
        unknown = sorted({str(t) for t in value if t not in STRATEGY_TAGS})
        if unknown:
            valid = ", ".join(sorted(STRATEGY_TAGS))
            raise serializers.ValidationError(
                f"Unknown strategy tags: {', '.join(unknown)}. Valid tags: {valid}."
            )
        return value
```

- [ ] Run the tests — expect PASS:

```
docker compose exec web pytest apps/profiles/tests/test_strategy_tags_api.py apps/profiles/tests/ -v
```

Expected: the 5 new tests pass AND the whole `apps/profiles/tests/` suite stays green (existing CRUD/endpoint tests must not regress).

- [ ] Commit:

```
git add backend/apps/profiles/serializers.py backend/apps/profiles/tests/test_strategy_tags_api.py
git commit -m "feat(profiles): expose and validate strategy_tags in the API" -m "Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>"
```

---

### Task 3: `signals` section kind on `SnapshotSection` + migration

**Files:**
- Modify: `backend/apps/snapshots/models.py` (`SnapshotSection.KIND_CHOICES`, lines 48-63)
- Create: `backend/apps/snapshots/migrations/0015_alter_snapshotsection_kind.py` (generated; prior precedents: 0009/0010/0012 are all `alter_snapshotsection_kind`)
- Test: `backend/apps/snapshots/tests/test_signals_kind.py` (new)

**Interfaces:**
- Consumes: `SnapshotSection` as it exists — `kind = models.CharField(max_length=16, choices=KIND_CHOICES)` (line 71); 14 existing kinds; migration chain ends at `0014_remove_snapshot_overnight`.
- Produces: kind string `"signals"` with label `"Strategy signals"` — Tasks 4-7 and the FE picker task rely on the exact string `"signals"`.

**Steps:**

- [ ] Write the failing test — create `backend/apps/snapshots/tests/test_signals_kind.py`:

```python
import pytest

from apps.profiles.models import TradingProfile
from apps.snapshots.models import Snapshot, SnapshotSection


def test_signals_kind_registered_and_fits_varchar16():
    kinds = dict(SnapshotSection.KIND_CHOICES)
    assert kinds.get("signals") == "Strategy signals"
    # kind is varchar(16) — a longer string would fail silently at write time
    assert len("signals") <= 16


@pytest.mark.django_db
def test_signals_section_row_persists():
    profile = TradingProfile.objects.create(name="P", style="x")
    snap = Snapshot.objects.create(profile=profile, includes=["signals"])
    sec = SnapshotSection.objects.create(
        snapshot=snap, kind="signals", status="done", payload={"AAPL": {}}
    )
    sec.refresh_from_db()
    assert sec.kind == "signals"
    assert sec.status == "done"
```

- [ ] Run it — expect failure:

```
docker compose exec web pytest apps/snapshots/tests/test_signals_kind.py -v
```

Expected: `test_signals_kind_registered_and_fits_varchar16` FAILS — `assert None == 'Strategy signals'`. (The DB row test may pass — choices are not DB-enforced — the registered-choice test is the gate.)

- [ ] Minimal implementation — in `backend/apps/snapshots/models.py`, append to `KIND_CHOICES` after the `("treasury", "Treasury rates"),` line (line 62):

```python
        ("treasury", "Treasury rates"),
        ("signals", "Strategy signals"),
    ]
```

- [ ] Generate + apply the migration, verify the gate:

```
make makemigrations
make migrate
make check-migrations
```

Expected: `snapshots/migrations/0015_alter_snapshotsection_kind.py` created with a single `migrations.AlterField` on `snapshotsection.kind` whose choices list now ends with `('signals', 'Strategy signals')`; both `migrate` and `check-migrations` succeed.

- [ ] Run the test — expect PASS:

```
docker compose exec web pytest apps/snapshots/tests/test_signals_kind.py -v
```

Expected: `2 passed`.

- [ ] Commit:

```
git add backend/apps/snapshots/models.py backend/apps/snapshots/migrations/0015_alter_snapshotsection_kind.py backend/apps/snapshots/tests/test_signals_kind.py
git commit -m "feat(snapshots): add the signals section kind" -m "Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>"
```

---

### Task 4: `fetch_signals_section` fetcher + `_FETCHERS` registration

**Files:**
- Modify: `backend/apps/snapshots/services/__init__.py` — imports (insert between the `quotes` import at line 24 and the `treasury` import at line 25), new function after `_fetch_news_section` (ends line 114), registration in `_FETCHERS` (dict at lines 117-153, insert after the `"quotes"` entry at line 147)
- Test: `backend/apps/snapshots/tests/test_signals_section.py` (new)

**Interfaces:**
- Consumes (P1 contract, verbatim — these exist on main):

```python
# apps/market/services/signals/engine.py
FAMILIES = ("momentum", "mean_reversion", "vol_options", "positioning")

def compute_signals(
    ticker: str,
    families: list[str] | None = None,   # None => all four
    *,
    benchmark: str = "$SPX",
) -> dict[str, dict[str, float | int | str | None]]:
    """{family: {signal_name: value|None}}. Never raises. Redis-cached per (family, ticker)."""

def compute_market_signals() -> dict[str, float | None]:
    """Market-wide signals (currently {"ad_line_slope_20d": ...}). Never raises."""

# apps/market/services/signals/bundles.py
FAMILY_FOR_TAG = {t: t for t in STRATEGY_TAGS}   # identity today; the indirection is the point
```

Also consumes: `TradingProfile.strategy_tags` (Task 1), kind `"signals"` (Task 3), and the existing capture-loop fetcher contract — keyword-only kwargs `(snapshot_id, watchlist_tickers, ohlc_ticker, ohlc_timeframe, ohlc_bars)` plus `**_` swallow; return `{"data": <JSON-serializable>}`; raise to mark the section `failed` (`services/__init__.py:222-241`).
- Produces: `fetch_signals_section(*, snapshot_id, watchlist_tickers, **_) -> dict` registered as `_FETCHERS["signals"]`. Payload shape (contract, verbatim): `{<ticker>: {<family>: {<signal>: value}}, "_market": {...}}` — tickers capped at 8; `"_market"` reserved. Tasks 5 (renderer) and 7 (diff) consume this exact shape.

**Steps:**

- [ ] Write the failing test — create `backend/apps/snapshots/tests/test_signals_section.py`:

```python
"""Tests for the 'signals' snapshot section fetcher."""

from unittest.mock import patch

import pytest

from apps.profiles.models import TradingProfile
from apps.snapshots.models import Snapshot
from apps.snapshots.services import _FETCHERS, capture, fetch_signals_section

FAKE_FAMILIES = {
    "momentum": {"macd_hist": 1.2, "adx": 27.0},
    "vol_options": {"iv_rank_252": 58.0},
}
FAKE_MARKET = {"ad_line_slope_20d": 0.4}


def _mk_snapshot(tags: list[str]) -> Snapshot:
    profile = TradingProfile.objects.create(
        name=f"P-{'-'.join(tags) or 'none'}", style="x", strategy_tags=tags
    )
    return Snapshot.objects.create(profile=profile, includes=["signals"])


@pytest.mark.django_db
def test_fetcher_registered():
    assert _FETCHERS["signals"] is fetch_signals_section


@pytest.mark.django_db
def test_payload_shape_per_ticker_plus_reserved_market_key():
    snap = _mk_snapshot([])
    with (
        patch("apps.snapshots.services.compute_signals", return_value=FAKE_FAMILIES),
        patch("apps.snapshots.services.compute_market_signals", return_value=FAKE_MARKET),
    ):
        result = fetch_signals_section(snapshot_id=snap.id, watchlist_tickers=["AAPL", "NVDA"])
    assert result["data"]["AAPL"] == FAKE_FAMILIES
    assert result["data"]["NVDA"] == FAKE_FAMILIES
    assert result["data"]["_market"] == FAKE_MARKET


@pytest.mark.django_db
def test_empty_tags_compute_all_families():
    snap = _mk_snapshot([])
    with (
        patch("apps.snapshots.services.compute_signals", return_value={}) as cs,
        patch("apps.snapshots.services.compute_market_signals", return_value={}),
    ):
        fetch_signals_section(snapshot_id=snap.id, watchlist_tickers=["AAPL"])
    cs.assert_called_once_with("AAPL", None)  # None => engine computes all four


@pytest.mark.django_db
def test_tags_route_families():
    snap = _mk_snapshot(["momentum", "vol_options"])
    with (
        patch("apps.snapshots.services.compute_signals", return_value={}) as cs,
        patch("apps.snapshots.services.compute_market_signals", return_value={}),
    ):
        fetch_signals_section(snapshot_id=snap.id, watchlist_tickers=["AAPL"])
    cs.assert_called_once_with("AAPL", ["momentum", "vol_options"])


@pytest.mark.django_db
def test_duplicate_and_unknown_tags_tolerated():
    """ORM writes bypass serializer validation — the fetcher dedupes and drops
    unknown tags; all-unknown falls back to all families (None)."""
    snap = _mk_snapshot(["momentum", "momentum", "bogus"])
    with (
        patch("apps.snapshots.services.compute_signals", return_value={}) as cs,
        patch("apps.snapshots.services.compute_market_signals", return_value={}),
    ):
        fetch_signals_section(snapshot_id=snap.id, watchlist_tickers=["AAPL"])
    cs.assert_called_once_with("AAPL", ["momentum"])

    snap2 = _mk_snapshot(["bogus"])
    with (
        patch("apps.snapshots.services.compute_signals", return_value={}) as cs2,
        patch("apps.snapshots.services.compute_market_signals", return_value={}),
    ):
        fetch_signals_section(snapshot_id=snap2.id, watchlist_tickers=["AAPL"])
    cs2.assert_called_once_with("AAPL", None)


@pytest.mark.django_db
def test_ticker_cap_at_8():
    snap = _mk_snapshot([])
    tickers = [f"T{i}" for i in range(12)]
    with (
        patch("apps.snapshots.services.compute_signals", return_value={}) as cs,
        patch("apps.snapshots.services.compute_market_signals", return_value={}),
    ):
        result = fetch_signals_section(snapshot_id=snap.id, watchlist_tickers=tickers)
    assert cs.call_count == 8
    assert set(result["data"]) == {f"T{i}" for i in range(8)} | {"_market"}


@pytest.mark.django_db
def test_failing_engine_marks_only_signals_section_failed():
    """Engine contract says never-raises, but the loop semantics must hold anyway:
    a raising fetcher fails ONLY its section; the snapshot stays ready."""
    profile = TradingProfile.objects.create(name="P-fail", style="x")
    with (
        patch("apps.snapshots.services.compute_signals", side_effect=RuntimeError("boom")),
        patch("apps.snapshots.services.fetch_quotes", return_value={"SPY": {"last": 500.0}}),
    ):
        snap = capture(
            profile=profile,
            objective="",
            includes=["quotes", "signals"],
            watchlist_tickers=["SPY"],
        )
    sections = {s.kind: s for s in snap.sections.all()}
    assert sections["signals"].status == "failed"
    assert "RuntimeError" in sections["signals"].error
    assert sections["quotes"].status == "done"
    assert snap.status == "ready"


@pytest.mark.django_db
def test_market_key_never_becomes_primary_ticker():
    """Primary derivation reads ONLY the quotes section — a signals-only
    snapshot derives no primary, and '_market' is never treated as a ticker."""
    profile = TradingProfile.objects.create(name="P-primary", style="x")
    with (
        patch("apps.snapshots.services.compute_signals", return_value={}),
        patch(
            "apps.snapshots.services.compute_market_signals",
            return_value={"ad_line_slope_20d": None},
        ),
    ):
        snap = capture(
            profile=profile, objective="", includes=["signals"], watchlist_tickers=["AAPL"]
        )
    assert snap.status == "ready"
    assert snap.primary_ticker is None
```

- [ ] Run it — expect failure:

```
docker compose exec web pytest apps/snapshots/tests/test_signals_section.py -v
```

Expected: collection error — `ImportError: cannot import name 'fetch_signals_section' from 'apps.snapshots.services'`.

- [ ] Minimal implementation — edit `backend/apps/snapshots/services/__init__.py`. First the imports: between `from apps.market.services.quotes import fetch_quotes` (line 24) and `from apps.market.services.treasury import fetch_treasury` (line 25), insert:

```python
from apps.market.services.signals.bundles import FAMILY_FOR_TAG
from apps.market.services.signals.engine import compute_market_signals, compute_signals
```

Then the fetcher — insert after `_fetch_news_section` (which ends at line 114), before the `_FETCHERS` dict:

```python
def fetch_signals_section(*, snapshot_id: int, watchlist_tickers: list[str], **_) -> dict:
    """Compute strategy signals for up to 8 watchlist tickers.

    Families come from the snapshot profile's strategy_tags (empty tags = all
    four; the engine treats families=None as "all"). Unknown tags are dropped
    and duplicates deduped — ORM writes bypass serializer validation.

    "_market" is a reserved payload key for market-wide signals: never a
    ticker, and never used for primary-ticker derivation (which only ever
    reads the quotes section — see apps.snapshots.primary).
    """
    snap = Snapshot.objects.select_related("profile").get(pk=snapshot_id)
    families: list[str] = []
    for tag in snap.profile.strategy_tags or []:
        fam = FAMILY_FOR_TAG.get(tag)
        if fam and fam not in families:
            families.append(fam)
    payload: dict = {
        t: compute_signals(t, families or None)
        for t in (list(watchlist_tickers) or [])[:8]
    }
    payload["_market"] = compute_market_signals()
    return {"data": payload}
```

Finally register it in `_FETCHERS` — after the `"quotes"` entry (line 147):

```python
    "quotes": lambda *, watchlist_tickers, **_: {"data": fetch_quotes(watchlist_tickers)},
    "signals": fetch_signals_section,
```

- [ ] Run the tests — expect PASS:

```
docker compose exec web pytest apps/snapshots/tests/test_signals_section.py -v
```

Expected: `8 passed`.

- [ ] Regression check on the capture suite (the loop, acks, and all-sections tests must not budge):

```
docker compose exec web pytest apps/snapshots/tests/ -q -k "capture"
```

Expected: all pass.

- [ ] Commit:

```
git add backend/apps/snapshots/services/__init__.py backend/apps/snapshots/tests/test_signals_section.py
git commit -m "feat(snapshots): signals section capture fetcher routed by strategy_tags" -m "Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>"
```

---

### Task 5: `_render_signals` renderer + `_title` entry (deterministic)

**Files:**
- Modify: `backend/apps/snapshots/serializer.py` — import at top (imports block, lines 8-10), `_title` map (lines 117-130), new `_render_signals` after `_render_fundamentals` (which ends at line 577), `_RENDERERS` dict (lines 580-592)
- Test: `backend/apps/snapshots/tests/test_serializer_signals.py` (new)

**Interfaces:**
- Consumes: the section payload shape from Task 4 — `{<ticker>: {<family>: {<signal>: value|None}}, "_market": {<signal>: value|None}}`; `FAMILIES = ("momentum", "mean_reversion", "vol_options", "positioning")` from `apps.market.services.signals.engine` (P1 contract); the existing `_fmt(v)` helper in this file (line 465: `None → "—"`, floats → `:.2f`, non-numeric → `str(v)`).
- Produces: `_render_signals(payload) -> str` registered as `_RENDERERS["signals"]`, `_title("signals") == "Strategy signals"`. Output starts `## Strategy signals`. **Byte-stable for identical payloads regardless of dict key order** (jsonb does not preserve order; the observer response cache keys on prompt bytes). Task 6 relies on `"signals"` producing rendered text so it participates in pruning.

**Steps:**

- [ ] Write the failing test — create `backend/apps/snapshots/tests/test_serializer_signals.py`:

```python
"""Tests for the signals section markdown renderer."""

import pytest

from apps.profiles.models import TradingProfile
from apps.snapshots.models import Snapshot, SnapshotSection
from apps.snapshots.serializer import _render_signals, _title, serialize_for_ai

PAYLOAD = {
    "NVDA": {
        "momentum": {"macd_hist": 1.234, "adx": 27.1, "ma_alignment": "20>50>200"},
        "mean_reversion": {"zscore_20d": -1.5, "rsi2": None},
    },
    "AAPL": {
        "vol_options": {"iv_rank_252": 58.0},
    },
    "_market": {"ad_line_slope_20d": 0.42},
}


def test_title():
    assert _title("signals") == "Strategy signals"


def test_render_signals_per_ticker_lines():
    out = _render_signals(PAYLOAD)
    assert out.startswith("## Strategy signals")
    assert "**AAPL**" in out
    assert "**NVDA**" in out
    assert "macd_hist=1.23" in out
    assert "iv_rank_252=58.00" in out
    assert "ma_alignment=20>50>200" in out
    assert "rsi2=—" in out  # None renders as em-dash — absent, never invented
    assert "- market: ad_line_slope_20d=0.42" in out


def test_render_signals_orders_tickers_alphabetically_and_market_last():
    out = _render_signals(PAYLOAD)
    assert out.index("**AAPL**") < out.index("**NVDA**")
    assert out.index("- market:") > out.index("**NVDA**")


def test_render_signals_families_in_canonical_order():
    out = _render_signals(PAYLOAD)
    assert out.index("- momentum:") < out.index("- mean_reversion:")


def test_render_signals_deterministic_across_key_order():
    # jsonb round-trips do NOT preserve key order — the renderer must sort
    # every level or the observer response cache is silently defeated.
    shuffled = {
        "_market": dict(reversed(list(PAYLOAD["_market"].items()))),
        "NVDA": {
            fam: dict(reversed(list(sigs.items())))
            for fam, sigs in reversed(list(PAYLOAD["NVDA"].items()))
        },
        "AAPL": PAYLOAD["AAPL"],
    }
    assert _render_signals(PAYLOAD) == _render_signals(shuffled)


def test_render_signals_empty_payload():
    assert "_(no signals data)_" in _render_signals({})
    assert "_(no signals data)_" in _render_signals(None)


@pytest.mark.django_db
def test_serialize_for_ai_includes_signals_block():
    profile = TradingProfile.objects.create(name="P", style="x")
    snap = Snapshot.objects.create(profile=profile, includes=["signals"], status="ready")
    SnapshotSection.objects.create(
        snapshot=snap, kind="signals", status="done", payload=PAYLOAD
    )
    out = serialize_for_ai(snap, max_tokens=40_000)
    assert "## Strategy signals" in out
    assert "iv_rank_252=58.00" in out
```

- [ ] Run it — expect failure:

```
docker compose exec web pytest apps/snapshots/tests/test_serializer_signals.py -v
```

Expected: collection error — `ImportError: cannot import name '_render_signals' from 'apps.snapshots.serializer'`.

- [ ] Minimal implementation — edit `backend/apps/snapshots/serializer.py`. Import (before the `apps.snapshots` imports at line 8, keeping isort order):

```python
from apps.market.services.signals.engine import FAMILIES
from apps.snapshots.image_store import read_image_bytes
from apps.snapshots.models import Snapshot, SnapshotImage
from apps.snapshots.token_budget import prune_to_budget
```

In the `_title` map (lines 117-130), add after the `"fundamentals"` entry:

```python
        "fundamentals": "Company fundamentals",
        "signals": "Strategy signals",
```

New renderer — insert after `_render_fundamentals` (ends line 577), before `_RENDERERS`:

```python
def _render_signals(payload) -> str:
    """Render the signals section as compact per-ticker lines.

    payload: {ticker: {family: {signal: value|None}}, "_market": {signal: value|None}}

    Output must be byte-stable for identical payloads: the observer response
    cache keys on the assembled prompt bytes, and jsonb round-trips do not
    preserve key order — so tickers, families, and signal names are all
    explicitly ordered here. No now-relative text.
    """
    if not isinstance(payload, dict) or not payload:
        return "## Strategy signals\n_(no signals data)_"
    lines = ["## Strategy signals"]
    for ticker in sorted(k for k in payload if k != "_market"):
        fams = payload.get(ticker)
        if not isinstance(fams, dict) or not fams:
            continue
        lines.append(f"**{ticker}**")
        ordered = [f for f in FAMILIES if f in fams]
        ordered += sorted(k for k in fams if k not in FAMILIES)
        for family in ordered:
            sigs = fams.get(family)
            if not isinstance(sigs, dict) or not sigs:
                continue
            pairs = ", ".join(f"{name}={_fmt(sigs[name])}" for name in sorted(sigs))
            lines.append(f"- {family}: {pairs}")
    market = payload.get("_market")
    if isinstance(market, dict) and market:
        pairs = ", ".join(f"{name}={_fmt(market[name])}" for name in sorted(market))
        lines.append(f"- market: {pairs}")
    if len(lines) == 1:
        return "## Strategy signals\n_(no signals data)_"
    return "\n".join(lines)
```

Register it in `_RENDERERS` (dict at lines 580-592), after the `"fundamentals"` entry:

```python
    "fundamentals": _render_fundamentals,
    "signals": _render_signals,
    "notes": lambda _p: "",
```

- [ ] Run the tests — expect PASS:

```
docker compose exec web pytest apps/snapshots/tests/test_serializer_signals.py -v
```

Expected: `7 passed`.

- [ ] Regression check on the serializer suite:

```
docker compose exec web pytest apps/snapshots/tests/ -q -k "serializer"
```

Expected: all pass.

- [ ] Commit:

```
git add backend/apps/snapshots/serializer.py backend/apps/snapshots/tests/test_serializer_signals.py
git commit -m "feat(snapshots): deterministic markdown renderer for the signals section" -m "Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>"
```

---

### Task 6: insert `signals` into `token_budget._PRUNE_ORDER`

**Files:**
- Modify: `backend/apps/snapshots/token_budget.py` (line 7, `_PRUNE_ORDER`)
- Test: `backend/apps/snapshots/tests/test_token_budget_signals.py` (new)

**Interfaces:**
- Consumes: `_PRUNE_ORDER = ["chain", "news", "ohlc", "breadth", "quotes", "positions"]` (current value at `token_budget.py:7`); `prune_to_budget(sections, *, max_tokens, provider, model)` deletes whole sections in `_PRUNE_ORDER` order until under budget.
- Produces: `_PRUNE_ORDER = ["chain", "news", "ohlc", "breadth", "signals", "quotes", "positions"]` — `signals` after `breadth`, before `quotes` (contract). Without this, an oversized signals payload is un-prunable and silently squeezes the listed kinds out of the AI payload (and dominates the 2k-token recall-embedding render).

**Steps:**

- [ ] Write the failing test — create `backend/apps/snapshots/tests/test_token_budget_signals.py`:

```python
from apps.snapshots.token_budget import _PRUNE_ORDER, prune_to_budget


def test_signals_sits_between_breadth_and_quotes_in_prune_order():
    assert "signals" in _PRUNE_ORDER
    assert (
        _PRUNE_ORDER.index("breadth")
        < _PRUNE_ORDER.index("signals")
        < _PRUNE_ORDER.index("quotes")
    )


def test_signals_pruned_after_breadth_and_before_quotes():
    big = "x " * 50_000
    sections = {"breadth": big, "signals": big, "quotes": big, "positions": "small"}
    out, pruned = prune_to_budget(sections, max_tokens=100)
    assert pruned == ["breadth", "signals", "quotes"]
    assert "positions" in out


def test_oversized_signals_dropped_while_small_quotes_kept():
    big = "x " * 50_000
    sections = {"signals": big, "quotes": "small"}
    out, pruned = prune_to_budget(sections, max_tokens=100)
    assert "signals" not in out
    assert "quotes" in out
    assert pruned == ["signals"]
```

- [ ] Run it — expect failure:

```
docker compose exec web pytest apps/snapshots/tests/test_token_budget_signals.py -v
```

Expected: all 3 FAIL — `assert 'signals' in _PRUNE_ORDER` is False; the behavior tests show signals surviving while quotes gets pruned.

- [ ] Minimal implementation — in `backend/apps/snapshots/token_budget.py` line 7, replace:

```python
_PRUNE_ORDER = ["chain", "news", "ohlc", "breadth", "quotes", "positions"]
```

with:

```python
_PRUNE_ORDER = ["chain", "news", "ohlc", "breadth", "signals", "quotes", "positions"]
```

- [ ] Run the tests — expect PASS, plus the existing token-budget suites (incl. Hypothesis property tests):

```
docker compose exec web pytest apps/snapshots/tests/test_token_budget_signals.py apps/snapshots/tests/test_token_budget.py apps/snapshots/tests/test_token_budget_properties.py apps/snapshots/tests/test_token_budget_image.py -v
```

Expected: all pass.

- [ ] Commit:

```
git add backend/apps/snapshots/token_budget.py backend/apps/snapshots/tests/test_token_budget_signals.py
git commit -m "feat(snapshots): make the signals section prunable after breadth" -m "Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>"
```

---### Task 7: `diff.py` branch for `signals` (scalar deltas)

**Files:**
- Modify: `backend/apps/snapshots/diff.py` — `_diff_one` dispatch (lines 79-94: add a branch before the `return ""` fall-through at line 94) and a new `_diff_signals` helper (add after `_diff_chain`, which ends at line 215)
- Test: `backend/apps/snapshots/tests/test_diff_signals.py` (new)

**Interfaces:**
- Consumes: the signals payload shape (Task 4): `{<ticker>: {<family>: {<signal>: value|None}}, "_market": {<signal>: value|None}}`; existing `_as_dict(payload)` helper (diff.py:53-55, coerces non-dicts to `{}` so the diff never raises); `diff_sections` per-section isolation (any raising branch is caught+logged, diff.py:30-48).
- Produces: `_diff_one("signals", prev, curr)` returning scalar-delta lines like `- AAPL iv_rank_252: 34 → 58` (contract) and `- market ad_line_slope_20d: 0.1 → 0.4` for the reserved key. Without this branch the section is invisible to diff-mode observers (`observer/services/run.py:178-195`), coverage revisions (`strategy/coverage/services/revise.py:130-137`), and `/api/snapshots/<id>/diff/`.

**Steps:**

- [ ] Write the failing test — create `backend/apps/snapshots/tests/test_diff_signals.py`:

```python
"""Tests for the signals branch of the snapshot diff."""

from apps.snapshots.diff import _diff_one, diff_sections

PREV = {
    "AAPL": {"vol_options": {"iv_rank_252": 34.0, "gex_total": None}},
    "NVDA": {"momentum": {"ma_alignment": "mixed", "adx": 20.0}},
    "_market": {"ad_line_slope_20d": 0.1},
}
CURR = {
    "AAPL": {"vol_options": {"iv_rank_252": 58.0, "gex_total": 1.0}},
    "NVDA": {"momentum": {"ma_alignment": "20>50>200", "adx": 20.0}},
    "_market": {"ad_line_slope_20d": 0.4},
}


def test_scalar_delta_rendered():
    out = _diff_one("signals", PREV, CURR)
    assert "- AAPL iv_rank_252: 34 → 58" in out


def test_string_state_change_rendered():
    out = _diff_one("signals", PREV, CURR)
    assert "- NVDA ma_alignment: mixed → 20>50>200" in out


def test_none_on_either_side_skipped():
    # gex_total went None -> 1.0: absent, never invented — no delta line.
    out = _diff_one("signals", PREV, CURR)
    assert "gex_total" not in out


def test_unchanged_values_skipped():
    out = _diff_one("signals", PREV, CURR)
    assert "adx" not in out


def test_market_block_diffed_with_market_label():
    out = _diff_one("signals", PREV, CURR)
    assert "- market ad_line_slope_20d: 0.1 → 0.4" in out


def test_malformed_payloads_return_empty_never_raise():
    assert _diff_one("signals", ["not", "a", "dict"], CURR) == ""
    assert _diff_one("signals", {"AAPL": "junk"}, {"AAPL": {"momentum": 5}}) == ""


def test_diff_sections_end_to_end_contains_signals_header():
    out = diff_sections({"signals": PREV}, {"signals": CURR})
    assert "**signals**:" in out
    assert "iv_rank_252" in out
```

- [ ] Run it — expect failure:

```
docker compose exec web pytest apps/snapshots/tests/test_diff_signals.py -v
```

Expected: the delta/market/string tests FAIL with empty-string output (`assert '- AAPL iv_rank_252: 34 → 58' in ''`) — the unregistered-kind fall-through at diff.py:94. The malformed + skip tests pass vacuously.

- [ ] Minimal implementation — edit `backend/apps/snapshots/diff.py`. In `_diff_one` (lines 79-94), add a branch before the final `return ""`:

```python
    if kind == "overnight":
        return _diff_overnight(_as_dict(prev), _as_dict(curr))
    if kind == "signals":
        return _diff_signals(_as_dict(prev), _as_dict(curr))
    return ""
```

Then add the helper after `_diff_chain` (ends line 215):

```python
def _diff_signals(prev: dict, curr: dict) -> str:
    """Scalar deltas per ticker/family/signal, e.g. `- AAPL iv_rank_252: 34 → 58`.

    Payload shape: {ticker: {family: {signal: value|None}}, "_market": {signal: value}}.
    A value that is None on either side is skipped (absent, never invented);
    "_market" is the reserved market-wide block, reported with the label `market`.
    """
    rows: list[str] = []

    def _sig_rows(label: str, p_sigs: dict, c_sigs: dict) -> None:
        for name in sorted(set(p_sigs) | set(c_sigs)):
            p_val, c_val = p_sigs.get(name), c_sigs.get(name)
            if p_val is None or c_val is None or p_val == c_val:
                continue
            if isinstance(p_val, int | float) and isinstance(c_val, int | float):
                rows.append(f"- {label} {name}: {p_val:g} → {c_val:g}")
            else:
                rows.append(f"- {label} {name}: {p_val} → {c_val}")

    for ticker in sorted((set(prev) | set(curr)) - {"_market"}):
        p_fams = _as_dict(prev.get(ticker))
        c_fams = _as_dict(curr.get(ticker))
        for family in sorted(set(p_fams) | set(c_fams)):
            _sig_rows(ticker, _as_dict(p_fams.get(family)), _as_dict(c_fams.get(family)))
    _sig_rows("market", _as_dict(prev.get("_market")), _as_dict(curr.get("_market")))
    return "\n".join(rows)
```

- [ ] Run the tests — expect PASS, plus the existing diff suites:

```
docker compose exec web pytest apps/snapshots/tests/test_diff_signals.py apps/snapshots/tests/ -q -k "diff"
```

Expected: all pass.

- [ ] Commit:

```
git add backend/apps/snapshots/diff.py backend/apps/snapshots/tests/test_diff_signals.py
git commit -m "feat(snapshots): scalar-delta diff support for the signals section" -m "Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>"
```

---

### Task 8: regenerate the OpenAPI schema + FE generated types

**Files:**
- Modify (generated): `backend/schema.yml`, `frontend/src/api/schema.d.ts`
- Tests: none (drift-gated artifacts; verification is by grep + git diff)

**Interfaces:**
- Consumes: `strategy_tags` in `TradingProfileSerializer` (Task 2); the `signals` kind choice (Task 3).
- Produces: committed `backend/schema.yml` + `frontend/src/api/schema.d.ts` containing `strategy_tags` under `TradingProfile`/`PatchedTradingProfile`. Both files are CI drift-gated — this task MUST land before the branch merges. Note: a plain JSONField lands as `unknown` in schema.d.ts (same as `default_includes` at schema.d.ts:2930) — the hand-written FE type in Task 9 is what the profile pages actually consume.

**Steps:**

- [ ] Regenerate the backend schema (runs spectacular inside `web`):

```
make schema
```

Expected: exits 0; `git diff --stat backend/schema.yml` shows changes.

- [ ] Verify the new field and kind are in the schema:

```
grep -n "strategy_tags" /home/dan/ledger/backend/schema.yml | head
grep -n "signals" /home/dan/ledger/backend/schema.yml | head
```

Expected: `strategy_tags` appears under both `TradingProfile` and `PatchedTradingProfile` components. `signals` appears in the `SnapshotSection` kind enum if drf-spectacular surfaces the choices (it does for choice fields); if the second grep only matches unrelated text, that is acceptable — the FE pickers are hand-coded lists, not schema-driven.

- [ ] Regenerate FE types **on the host** (NOT inside the frontend container — `pnpm gen:api` fails silently there because `../backend/schema.yml` is unresolvable; per project memory, the fallback is copying schema.yml into the container and running openapi-typescript against it):

```
cd /home/dan/ledger/frontend && pnpm gen:api
```

Expected: exits 0; `git diff --stat src/api/schema.d.ts` shows changes including `strategy_tags`.

- [ ] Verify:

```
grep -n "strategy_tags" /home/dan/ledger/frontend/src/api/schema.d.ts | head
```

Expected: at least two hits (TradingProfile + PatchedTradingProfile).

- [ ] Commit both generated files together:

```
git add backend/schema.yml frontend/src/api/schema.d.ts
git commit -m "chore(api): regenerate OpenAPI schema and FE types for strategy_tags + signals kind" -m "Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>"
```

---

### Task 9: FE — thread `strategy_tags` through the profile form (four hand-maintained spots)

**Files:**
- Modify: `frontend/src/api/profiles.ts` (type at lines 3-11)
- Modify: `frontend/src/pages/profiles/types.ts` (Draft + BLANK_DRAFT at lines 3-14; new `STRATEGY_TAG_OPTIONS` const)
- Modify: `frontend/src/pages/profiles/useProfileForm.ts` (`startEdit` field-copy at lines 17-26; new `toggleTag`; return object at line 40)
- Modify: `frontend/src/pages/profiles/ProfileForm.tsx` (imports lines 1-4; destructure line 7; new checkbox block after the Default sections `<div>` that ends at line 35)
- Test: `frontend/src/__tests__/ProfilesPage.test.tsx` (fixture `PROFILE_A` at lines 58-66 + new describe block appended)

**Interfaces:**
- Consumes: the API field `strategy_tags: string[]` (Task 2, backend always returns it); the existing `toggleInArray(list, value)` helper (`pages/profiles/types.ts:33-37`); the checkbox-set precedent (`SECTION_OPTIONS` + `toggleSection` in ProfileForm).
- Produces: `strategy_tags: string[]` on the hand-written `TradingProfile` type, `Draft`, `BLANK_DRAFT` (as `[]`), `startEdit` copy, and a labelled checkbox group in `ProfileForm` — omission in ANY of the four spots silently drops the field from create/edit payloads (the pages import the hand-written type, not schema.d.ts). Also `STRATEGY_TAG_OPTIONS = ["momentum", "mean_reversion", "vol_options", "positioning"]` (exactly `bundles.STRATEGY_TAGS`, hand-synced — there is no drift gate between them). No new components are created, so the storyless ratchet is untouched.

**Steps:**

- [ ] Write the failing tests — edit `frontend/src/__tests__/ProfilesPage.test.tsx`. First update the fixture (lines 58-66) so the type change in this task compiles and edit-population is testable — add `strategy_tags: ["momentum"],` :

```tsx
const PROFILE_A: TradingProfile = {
  id: 1,
  name: "Swing Trader",
  style: "Hold 2-5 days",
  default_includes: ["quotes", "ohlc"],
  default_provider: "claude",
  default_model: "claude-sonnet-4-6",
  strategy_tags: ["momentum"],
  active: true,
};
```

Then append this describe block at the end of the file:

```tsx
describe("ProfilesPage – strategy tags", () => {
  it("renders four strategy-tag checkboxes, unchecked by default", () => {
    renderWithProviders(<ProfilesPage />);
    for (const tag of ["momentum", "mean_reversion", "vol_options", "positioning"]) {
      expect(
        screen.getByRole("checkbox", { name: new RegExp(`^${tag}$`) }),
      ).not.toBeChecked();
    }
  });

  it("create body carries strategy_tags: [] when nothing is toggled", async () => {
    const user = userEvent.setup();
    const createMutate = vi.fn();
    mockUseCreateProfile.mockReturnValue({ mutate: createMutate, isPending: false } as never);

    renderWithProviders(<ProfilesPage />);
    await user.type(screen.getByPlaceholderText("Profile name"), "Untagged");
    fireEvent.click(screen.getByRole("button", { name: /create/i }));

    const [body] = createMutate.mock.calls[0];
    expect(body.strategy_tags).toEqual([]);
  });

  it("toggling a tag checkbox adds it to the create body", async () => {
    const user = userEvent.setup();
    const createMutate = vi.fn();
    mockUseCreateProfile.mockReturnValue({ mutate: createMutate, isPending: false } as never);

    renderWithProviders(<ProfilesPage />);
    await user.click(screen.getByRole("checkbox", { name: /^mean_reversion$/ }));
    await user.type(screen.getByPlaceholderText("Profile name"), "Reverter");
    fireEvent.click(screen.getByRole("button", { name: /create/i }));

    const [body] = createMutate.mock.calls[0];
    expect(body.strategy_tags).toEqual(["mean_reversion"]);
  });

  it("editing a profile populates its strategy tags and round-trips them", async () => {
    mockUseProfiles.mockReturnValue({ data: [PROFILE_A] } as never);
    const updateMutate = vi.fn();
    mockUseUpdateProfile.mockReturnValue({ mutate: updateMutate, isPending: false } as never);

    const user = userEvent.setup();
    renderWithProviders(<ProfilesPage />);

    await user.click(screen.getByRole("button", { name: /edit/i }));
    expect(screen.getByRole("checkbox", { name: /^momentum$/ })).toBeChecked();

    fireEvent.click(screen.getByRole("button", { name: /save/i }));
    const [args] = updateMutate.mock.calls[0];
    expect(args.body.strategy_tags).toEqual(["momentum"]);
  });
});
```

(Anchored regexes matter: `/^positioning$/` must not collide with the `positions` section checkbox — and it doesn't, because testing-library regex name matchers test the full accessible name.)

- [ ] Run it — expect failure:

```
docker compose exec frontend pnpm exec vitest run src/__tests__/ProfilesPage.test.tsx
```

Expected: the 4 new tests FAIL with `TestingLibraryElementError: Unable to find an accessible element with the role "checkbox" and name /^momentum$/` (and `body.strategy_tags` is `undefined` in the body tests). Pre-existing tests stay green.

- [ ] Implementation part 1 — `frontend/src/api/profiles.ts`: replace the type (lines 3-11) with:

```ts
export type TradingProfile = {
  id: number;
  name: string;
  style: string;
  default_includes: string[];
  default_provider: string;
  default_model: string;
  strategy_tags: string[];
  active: boolean;
};
```

- [ ] Implementation part 2 — `frontend/src/pages/profiles/types.ts`: add the options const after `SECTION_OPTIONS` (line 1), and extend `Draft` + `BLANK_DRAFT` (lines 3-14):

```ts
export const SECTION_OPTIONS = ["quotes", "ohlc", "positions", "breadth", "notes"] as const;

/** Hand-synced with backend bundles.STRATEGY_TAGS — no drift gate exists. */
export const STRATEGY_TAG_OPTIONS = [
  "momentum",
  "mean_reversion",
  "vol_options",
  "positioning",
] as const;

export type Draft = {
  name: string;
  style: string;
  default_includes: string[];
  default_provider: string;
  default_model: string;
  strategy_tags: string[];
};

export const BLANK_DRAFT: Draft = {
  name: "", style: "", default_includes: ["quotes", "positions", "breadth"],
  default_provider: "claude", default_model: "claude-sonnet-4-6",
  strategy_tags: [],
};
```

(Leave `PresetDraft`, `BLANK_PRESET_DRAFT`, and `toggleInArray` untouched.)

- [ ] Implementation part 3 — `frontend/src/pages/profiles/useProfileForm.ts`: add the field to `startEdit` (lines 17-26) and a `toggleTag`, and return it (line 40):

```ts
  const startEdit = (p: TradingProfile) => {
    setEditing(p);
    setDraft({
      name: p.name,
      style: p.style,
      default_includes: p.default_includes,
      default_provider: p.default_provider,
      default_model: p.default_model,
      strategy_tags: p.strategy_tags ?? [],
    });
  };
```

```ts
  const toggleSection = (sec: string) =>
    setDraft((d) => ({ ...d, default_includes: toggleInArray(d.default_includes, sec) }));

  const toggleTag = (tag: string) =>
    setDraft((d) => ({ ...d, strategy_tags: toggleInArray(d.strategy_tags, tag) }));

  return { editing, draft, setDraft, submit, toggleSection, toggleTag, startEdit, reset };
```

- [ ] Implementation part 4 — `frontend/src/pages/profiles/ProfileForm.tsx`: update the import (line 3) and destructure (line 7):

```tsx
import { SECTION_OPTIONS, STRATEGY_TAG_OPTIONS } from "./types";
```

```tsx
  const { editing, draft, setDraft, submit, toggleSection, toggleTag, reset } = form;
```

and insert this block immediately after the Default sections `<div>` (which ends at line 35), before the provider/model row:

```tsx
      <div>
        <div className="text-xs text-slate-500 mb-1">
          Strategy tags (route signal families; empty = all)
        </div>
        <div className="flex flex-wrap gap-2">
          {STRATEGY_TAG_OPTIONS.map((tag) => (
            <label key={tag} className="flex items-center gap-1 text-sm">
              <input
                type="checkbox" checked={draft.strategy_tags.includes(tag)}
                onChange={() => toggleTag(tag)}
              />
              {tag}
            </label>
          ))}
        </div>
      </div>
```

- [ ] Run the tests — expect PASS (whole file, old + new):

```
docker compose exec frontend pnpm exec vitest run src/__tests__/ProfilesPage.test.tsx
```

Expected: all tests pass, including the pre-existing ProfilesPage + preset suites.

- [ ] Typecheck + lint the FE (catches any other fixture typed as `TradingProfile` missing the new required field — `ProfilesPage.test.tsx` is the only one today):

```
docker compose exec frontend pnpm run lint
```

Expected: exits 0.

- [ ] Commit:

```
git add frontend/src/api/profiles.ts frontend/src/pages/profiles/types.ts frontend/src/pages/profiles/useProfileForm.ts frontend/src/pages/profiles/ProfileForm.tsx frontend/src/__tests__/ProfilesPage.test.tsx
git commit -m "feat(frontend): strategy_tags editing in the profile form" -m "Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>"
```

---

### Task 10: FE — add `signals` to both section-kind pickers

**Files:**
- Modify: `frontend/src/components/SnapshotSectionPicker.tsx` (`SECTIONS` list, lines 1-14)
- Modify: `frontend/src/pages/profiles/types.ts` (`SECTION_OPTIONS`, line 1)
- Tests: `frontend/src/__tests__/SnapshotSectionPicker.test.tsx` (LABELS at lines 6-19, count assertions at lines 22-29) and `frontend/src/__tests__/ProfilesPage.test.tsx` (one new test appended)

**Interfaces:**
- Consumes: kind string `"signals"` (Task 3); the two hand-coded picker lists — the composer's `SECTIONS` (12 entries) and the profile form's `SECTION_OPTIONS` (5 entries). Neither is generated from the backend `_FETCHERS` registry and there is no drift gate; a kind missing from either list simply cannot be toggled from that UI.
- Produces: `{ key: "signals", label: "Strategy signals" }` in `SnapshotSectionPicker.SECTIONS` (composer can include it per-capture) and `"signals"` in `SECTION_OPTIONS` (profiles can default-include it, which is how observer/trigger fires pick the section up).

**Steps:**

- [ ] Write the failing tests. In `frontend/src/__tests__/SnapshotSectionPicker.test.tsx`, update `LABELS` (lines 6-19) — insert `"Strategy signals"` after `"Market context"`:

```tsx
const LABELS = [
  "Quotes",
  "OHLC bars",
  "Positions",
  "Market context",
  "Strategy signals",
  "My notes",
  "Option chain",
  "News",
  "Upcoming events",
  "Macro (FRED)",
  "SEC filings",
  "Treasury rates",
  "Charts (server-render)",
];
```

and update the count test (lines 22-29):

```tsx
  it("renders 13 labeled checkboxes", () => {
    render(<SnapshotSectionPicker value={[]} onChange={() => {}} />);
    const checkboxes = screen.getAllByRole("checkbox");
    expect(checkboxes).toHaveLength(13);
    for (const label of LABELS) {
      expect(screen.getByLabelText(label)).toBeInTheDocument();
    }
  });
```

Then append to the main `describe("ProfilesPage", ...)` block in `frontend/src/__tests__/ProfilesPage.test.tsx` (anywhere among its `it`s):

```tsx
  it("profile form offers the signals section and toggles it into default_includes", async () => {
    const user = userEvent.setup();
    const createMutate = vi.fn();
    mockUseCreateProfile.mockReturnValue({ mutate: createMutate, isPending: false } as never);

    renderWithProviders(<ProfilesPage />);
    const signalsCheckbox = screen.getByRole("checkbox", { name: /^signals$/ });
    expect(signalsCheckbox).not.toBeChecked();
    await user.click(signalsCheckbox);
    await user.type(screen.getByPlaceholderText("Profile name"), "SignalsUser");
    fireEvent.click(screen.getByRole("button", { name: /create/i }));

    const [body] = createMutate.mock.calls[0];
    expect(body.default_includes).toContain("signals");
  });
```

(`/^signals$/` cannot collide with the four tag checkboxes — none of them is named exactly `signals`.)

- [ ] Run them — expect failure:

```
docker compose exec frontend pnpm exec vitest run src/__tests__/SnapshotSectionPicker.test.tsx src/__tests__/ProfilesPage.test.tsx
```

Expected: picker test FAILS (`expected [...12 items] to have a length of 13` and `Unable to find a label with the text of: Strategy signals`); the ProfilesPage test FAILS (`Unable to find an accessible element with the role "checkbox" and name /^signals$/`).

- [ ] Implementation part 1 — `frontend/src/components/SnapshotSectionPicker.tsx`: insert into `SECTIONS` after the `breadth` entry (line 5):

```tsx
const SECTIONS = [
  { key: "quotes", label: "Quotes" },
  { key: "ohlc", label: "OHLC bars" },
  { key: "positions", label: "Positions" },
  { key: "breadth", label: "Market context" },
  { key: "signals", label: "Strategy signals" },
  { key: "notes", label: "My notes" },
  { key: "chain", label: "Option chain" },
  { key: "news", label: "News" },
  { key: "events", label: "Upcoming events" },
  { key: "macro", label: "Macro (FRED)" },
  { key: "filings", label: "SEC filings" },
  { key: "treasury", label: "Treasury rates" },
  { key: "image", label: "Charts (server-render)" },
];
```

- [ ] Implementation part 2 — `frontend/src/pages/profiles/types.ts` line 1, append `"signals"`:

```ts
export const SECTION_OPTIONS = ["quotes", "ohlc", "positions", "breadth", "notes", "signals"] as const;
```

- [ ] Run the tests — expect PASS:

```
docker compose exec frontend pnpm exec vitest run src/__tests__/SnapshotSectionPicker.test.tsx src/__tests__/ProfilesPage.test.tsx src/__tests__/SnapshotComposerPage.test.tsx
```

Expected: all pass (`SnapshotComposerPage.test.tsx` is included as a regression check — it renders the picker but asserts no checkbox count).

- [ ] Commit:

```
git add frontend/src/components/SnapshotSectionPicker.tsx frontend/src/pages/profiles/types.ts frontend/src/__tests__/SnapshotSectionPicker.test.tsx frontend/src/__tests__/ProfilesPage.test.tsx
git commit -m "feat(frontend): add the signals section to composer and profile pickers" -m "Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>"
```

---

### Task 11: final verification — full gates, worker restart, landmine sweep

**Files:** none created (fix-forward only if a gate fails).

**Interfaces:**
- Consumes: everything from Tasks 1-10.
- Produces: a green `make check`-equivalent state and a verified spec-§12 landmine checklist for P2.

**Steps:**

- [ ] Backend suites for both touched apps:

```
docker compose exec web pytest apps/profiles apps/snapshots -q
```

Expected: all pass, 0 failures.

- [ ] Full FE test run (coverage floors 80/74/77/82 must hold):

```
docker compose exec frontend pnpm exec vitest run
```

Expected: all pass; coverage thresholds met; `storyCoverage` test green (no new components were added).

- [ ] Migration + schema drift gates:

```
make check-migrations
git status --short backend/schema.yml frontend/src/api/schema.d.ts
```

Expected: `check-migrations` exits 0; both generated files committed (empty `git status` output for them).

- [ ] Full lint (ruff + mypy zero-baseline + import-linter + deptry + semgrep rules + FE eslint/depcruise/type-coverage):

```
make lint
```

Expected: exits 0. (`ty` is advisory; anything else red must be fixed before finishing.)

- [ ] Restart the stale-code landmine away — the capture loop runs in `worker`, which does NOT hot-reload backend changes the way `web` does:

```
docker compose restart worker beat
```

- [ ] Landmine sweep (spec §12, P2 items) — each command must produce a hit:

```
grep -n "strategy_tags" /home/dan/ledger/backend/apps/profiles/serializers.py
grep -n '"signals"' /home/dan/ledger/backend/apps/snapshots/token_budget.py
grep -n '"signals"' /home/dan/ledger/backend/apps/snapshots/diff.py
grep -n '"signals"' /home/dan/ledger/backend/apps/snapshots/serializer.py
grep -rn '"signals"' /home/dan/ledger/frontend/src/components/SnapshotSectionPicker.tsx /home/dan/ledger/frontend/src/pages/profiles/types.ts
```

Confirm by reading the hits: serializer `Meta.fields` includes `strategy_tags`; `signals` is in `_PRUNE_ORDER` between `breadth` and `quotes`; `_diff_one` has the `signals` branch; `_RENDERERS`/`_title` carry `signals`; both FE lists carry it. Also confirm (by absence): no changes under `backend/apps/observer/`, `backend/apps/core/scheduled_tasks.py`, `backend/apps/core/feature_flags.py`, or `backend/apps/export/` — `git log --stat` over this branch must not touch them.

- [ ] Manual smoke (optional but recommended, dev stack running via `make dev`): create a profile with tags `["momentum"]` and default sections including `signals` at `/profiles`, capture a snapshot from the composer with the `Strategy signals` section checked, and confirm the section reaches `done` and renders in the snapshot detail. Note: if the visual e2e lane is run later, the composer baseline will drift by one checkbox — regenerate via `make e2e-visual-update` in that lane's own PR, not preemptively here.

- [ ] If any gate required a fix, commit it:

```
git add -A && git commit -m "fix: address P2 gate findings" -m "Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>"
```
