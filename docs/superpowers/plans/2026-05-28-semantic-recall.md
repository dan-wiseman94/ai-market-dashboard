# Semantic Recall Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Semantic search + auto-resurfacing over the whole AI corpus (assistant messages, snapshots, theses, journal, observations, post-mortems) via local pgvector embeddings, with a `/recall` page, a `<RelatedObservations>` panel, and an AI `recall` tool — degrading to Postgres full-text search when no embedding backend is present.

**Architecture:** A central `RecallDocument` (kind + object_id + text + 384-dim vector + FTS column) indexed by a periodic sweep + a backfill command. An `embed()` seam (local `fastembed`, returns `None` → FTS fallback) keeps the backend swappable. Search/related services mirror the on-demand `apps.analytics` pattern; the `recall` tool plugs into the existing tool registry. Spec: `docs/superpowers/specs/2026-05-28-semantic-recall-design.md`. **Depends on Snapshot Intelligence** (uses `Snapshot.primary_ticker`).

**Tech Stack:** Django 6 + DRF, Celery + Redis, Postgres 17 + **pgvector**, `fastembed` (ONNX), React + TS. Docker.

**Conventions for every task:** in-container pytest (no `backend/` prefix); `make makemigrations`/`make migrate`; conventional commits + `Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>` trailer. **After deploy: rebuild images (new deps + model bake), `docker compose restart worker beat`, and run `manage.py recall_backfill` once.**

---

## File Structure

- `compose.yaml`, `compose.e2e.yaml`, prod overlay — `db` image → `pgvector/pgvector:pg17` (modify).
- `backend/pyproject.toml` + `uv.lock` — add `pgvector`, `fastembed` (modify).
- `backend/Dockerfile` — bake the embedding model into `base` (modify).
- `backend/apps/recall/` — **new app**: `apps.py`, `models.py`, `embeddings.py`, `text.py`, `services/index.py`, `services/search.py`, `tasks.py`, `serializers.py`, `views.py`, `urls.py`, `management/commands/recall_backfill.py`, `migrations/0001_initial.py`.
- `backend/config/settings/base.py` — `INSTALLED_APPS += "apps.recall"` (modify).
- `backend/config/urls.py` — include `api/recall/` **before** the generic `/api/` (modify).
- `backend/config/celery.py` — autodiscover `apps.recall` + `index_pending` beat entry (modify).
- `backend/apps/ai/tools/registry.py` — register the `recall` tool (modify).
- `frontend/src/api/recall.ts`, `hooks/useRecall.ts`, `pages/RecallPage.tsx`, `components/RelatedObservations.tsx` — **new**; router/nav/shortcut (modify).
- `e2e/api/test_recall_search.py` — **new**.

---

## Task 1: Platform — pgvector image + deps + model bake

**Files:** `compose.yaml`, `compose.e2e.yaml`, prod overlay, `backend/pyproject.toml`, `backend/Dockerfile`

- [ ] **Step 1: Swap the db image** in `compose.yaml` (line 5), `compose.e2e.yaml` (and its `db-e2e` service), and the prod overlay: `image: postgres:17-alpine` → `image: pgvector/pgvector:pg17`. (Same PG17 → `pg_data` volume reused.)

- [ ] **Step 2: Add deps** to `backend/pyproject.toml` `dependencies`:

```
    "pgvector>=0.3,<1.0",
    "fastembed>=0.4,<1.0",
```

- [ ] **Step 3: Bake the model** — in `backend/Dockerfile`, in the `base` stage after the `uv sync` layer (after line 26), add:

```dockerfile
ENV FASTEMBED_CACHE_PATH=/app/.fastembed_cache
RUN --mount=type=cache,target=/root/.cache/uv \
    uv run python -c "from fastembed import TextEmbedding; TextEmbedding('BAAI/bge-small-en-v1.5')"
```

- [ ] **Step 4: Rebuild + verify the extension and model load**

```bash
docker compose down && docker compose build && docker compose up -d
docker compose exec db psql -U "$POSTGRES_USER" -d "$POSTGRES_DB" -c "CREATE EXTENSION IF NOT EXISTS vector; SELECT extname FROM pg_extension WHERE extname='vector';"
docker compose exec web uv run python -c "from fastembed import TextEmbedding; m=TextEmbedding('BAAI/bge-small-en-v1.5'); print(len(list(m.embed(['hi']))[0]))"
```

Expected: `vector` row printed; the embed dimension prints `384`.

- [ ] **Step 5: Regenerate the lock + commit**

```bash
docker compose exec web uv lock   # then copy uv.lock back to host if needed
git add compose.yaml compose.e2e.yaml backend/pyproject.toml backend/Dockerfile uv.lock
# include the prod overlay file in the add
git commit -m "feat(infra): pgvector db image + fastembed embedding model"
```

---

## Task 2: `apps.recall` scaffold + `RecallDocument` model + migration

**Files:** new app files + `config/settings/base.py`, `config/urls.py`
- Test: `backend/apps/recall/tests/test_model.py`

- [ ] **Step 1: Scaffold the app** (use the repo's `new-django-app` conventions): `apps/recall/__init__.py`, `apps.py` (`class RecallConfig(AppConfig): name = "apps.recall"; label = "recall"`), empty `urls.py`. Add `"apps.recall"` to `INSTALLED_APPS` in `config/settings/base.py`. Add to `config/urls.py` **before** the generic `/api/` include: `path("api/recall/", include("apps.recall.urls"))`.

- [ ] **Step 2: Write the failing test**

```python
# backend/apps/recall/tests/test_model.py
import pytest
from apps.recall.models import RecallDocument

@pytest.mark.django_db
def test_recall_document_roundtrip():
    d = RecallDocument.objects.create(
        kind="thesis", object_id=1, text="NVDA bullish into earnings",
        embedding=[0.1] * 384, embedding_model="bge-small", tickers=["NVDA"],
        content_hash="abc")
    d.refresh_from_db()
    assert d.kind == "thesis" and len(d.embedding) == 384 and d.tickers == ["NVDA"]

@pytest.mark.django_db
def test_unique_kind_object():
    RecallDocument.objects.create(kind="thesis", object_id=1, text="x", content_hash="h")
    with pytest.raises(Exception):
        RecallDocument.objects.create(kind="thesis", object_id=1, text="y", content_hash="h2")
```

- [ ] **Step 3: Implement the model** `backend/apps/recall/models.py`:

```python
from __future__ import annotations
from typing import ClassVar
from django.contrib.postgres.indexes import GinIndex
from django.contrib.postgres.search import SearchVectorField
from django.db import models
from pgvector.django import HnswIndex, VectorField


class RecallDocument(models.Model):
    KIND_CHOICES: ClassVar = [("message","Message"),("snapshot","Snapshot"),("thesis","Thesis"),
                              ("journal","Journal"),("observation","Observation"),("postmortem","PostMortem")]
    kind = models.CharField(max_length=16, choices=KIND_CHOICES)
    object_id = models.IntegerField()
    text = models.TextField()
    embedding = VectorField(dimensions=384, null=True, blank=True)
    embedding_model = models.CharField(max_length=64, blank=True, default="")
    tickers = models.JSONField(default=list)
    source_created_at = models.DateTimeField(null=True, blank=True)
    content_hash = models.CharField(max_length=64)
    search = SearchVectorField(null=True)
    indexed_at = models.DateTimeField(auto_now=True)

    class Meta:
        constraints: ClassVar = [models.UniqueConstraint(fields=["kind","object_id"], name="uniq_recall_doc")]
        indexes: ClassVar = [
            HnswIndex(name="recall_emb_hnsw", fields=["embedding"], m=16, ef_construction=64,
                      opclasses=["vector_cosine_ops"]),
            GinIndex(fields=["search"], name="recall_search_gin"),
            models.Index(fields=["-source_created_at"]),
        ]
```

- [ ] **Step 4: Generate the migration, then prepend `VectorExtension`.** Run `make makemigrations recall`. Then edit `apps/recall/migrations/0001_initial.py` to make `pgvector.django.VectorExtension()` the **first** operation (before `CreateModel`):

```python
from pgvector.django import VectorExtension
# ...
    operations = [VectorExtension(), migrations.CreateModel(...), ...]
```

- [ ] **Step 5: Migrate + run the test**

Run: `make migrate && docker compose exec web pytest apps/recall/tests/test_model.py -v`
Expected: PASS.

- [ ] **Step 6: Commit**

```bash
git add backend/apps/recall/ backend/config/settings/base.py backend/config/urls.py
git commit -m "feat(recall): app scaffold + RecallDocument (pgvector + FTS)"
```

---

## Task 3: `embed()` seam

**Files:** `backend/apps/recall/embeddings.py`; Test: `backend/apps/recall/tests/test_embeddings.py`

- [ ] **Step 1: Write the failing tests**

```python
# backend/apps/recall/tests/test_embeddings.py
from apps.recall import embeddings

def test_embed_returns_vectors(monkeypatch):
    class FakeModel:
        def embed(self, texts): return [[0.0]*384 for _ in texts]
    monkeypatch.setattr(embeddings, "_get_model", lambda: FakeModel())
    out = embeddings.embed(["a", "b"])
    assert out is not None and len(out) == 2 and len(out[0]) == 384

def test_embed_none_when_backend_unavailable(monkeypatch):
    monkeypatch.setattr(embeddings, "_get_model", lambda: None)
    assert embeddings.embed(["a"]) is None
```

- [ ] **Step 2: Run — expect failure.** `docker compose exec web pytest apps/recall/tests/test_embeddings.py -v`

- [ ] **Step 3: Implement** `backend/apps/recall/embeddings.py`:

```python
"""Local embedding backend (fastembed). Returns None when unavailable → FTS fallback."""
from __future__ import annotations
import logging
import numpy as np

log = logging.getLogger(__name__)
MODEL_NAME = "BAAI/bge-small-en-v1.5"
DIM = 384
_model = None
_tried = False

def _get_model():
    global _model, _tried
    if _model is None and not _tried:
        _tried = True
        try:
            from fastembed import TextEmbedding
            _model = TextEmbedding(model_name=MODEL_NAME)
        except Exception as exc:           # import error, model missing, etc.
            log.warning("recall.embed unavailable: %s", exc)
            _model = None
    return _model

def embed(texts: list[str]) -> list[list[float]] | None:
    model = _get_model()
    if model is None or not texts:
        return None if model is None else []
    try:
        return [np.asarray(v, dtype=float).tolist() for v in model.embed(list(texts))]
    except Exception as exc:
        log.warning("recall.embed failed: %s", exc)
        return None
```

- [ ] **Step 4: Run — expect pass.** `docker compose exec web pytest apps/recall/tests/test_embeddings.py -v`

- [ ] **Step 5: Commit**

```bash
git add backend/apps/recall/embeddings.py backend/apps/recall/tests/test_embeddings.py
git commit -m "feat(recall): fastembed embed() seam with None fallback"
```

---

## Task 4: Text builders

**Files:** `backend/apps/recall/text.py`; Test: `backend/apps/recall/tests/test_text.py`

- [ ] **Step 1: Write the failing tests**

```python
# backend/apps/recall/tests/test_text.py
import pytest
from apps.profiles.models import TradingProfile
from apps.thesis.models import Thesis
from apps.recall.text import build_text, extract_tickers, content_hash

@pytest.mark.django_db
def test_thesis_text_and_tickers():
    p = TradingProfile.objects.create(name="P", default_includes=["quotes"])
    th = Thesis.objects.create(title="NVDA run", ticker="NVDA", direction="bullish",
                               rationale="AI demand", profile=p)
    assert "NVDA run" in build_text("thesis", th) and "AI demand" in build_text("thesis", th)
    assert extract_tickers("thesis", th) == ["NVDA"]

def test_content_hash_stable():
    assert content_hash("abc") == content_hash("abc") and content_hash("abc") != content_hash("abd")
```

- [ ] **Step 2: Run — expect failure.**

- [ ] **Step 3: Implement** `backend/apps/recall/text.py`:

```python
from __future__ import annotations
import hashlib

def content_hash(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()

def _message_text(msg) -> str:
    c = msg.content or {}
    if isinstance(c, dict):
        if "text" in c: return str(c["text"])
        if "blocks" in c:
            return "\n".join(b.get("text","") for b in c["blocks"] if isinstance(b, dict))
    return str(c)

def build_text(kind: str, obj) -> str:
    if kind == "message":   return _message_text(obj)[:8000]
    if kind == "snapshot":
        from apps.snapshots.serializer import serialize_for_ai
        return serialize_for_ai(obj, max_tokens=2000)
    if kind == "thesis":    return f"{obj.title}\n{obj.rationale}\n{obj.ticker} {obj.direction}"
    if kind == "journal":   return obj.note or ""
    if kind == "postmortem":
        r = obj.report or {}
        return " ".join(str(r.get(k,"")) for k in ("summary","lessons","what_missed")) or obj.verdict
    if kind == "observation": return _message_text(obj)[:8000]
    return ""

def extract_tickers(kind: str, obj) -> list[str]:
    if kind == "thesis": return [obj.ticker.upper()] if obj.ticker else []
    snap = getattr(obj, "snapshot_ref", None) or getattr(obj, "snapshot", None) or (obj if kind=="snapshot" else None)
    pt = getattr(snap, "primary_ticker", None)
    return [pt] if pt else []
```

- [ ] **Step 4: Run — expect pass.** **Step 5: Commit** `feat(recall): per-kind text builders + tickers + content hash`.

---

## Task 5: Index service + tasks + backfill command + beat

**Files:** `services/index.py`, `tasks.py`, `management/commands/recall_backfill.py`, `config/celery.py`
- Test: `backend/apps/recall/tests/test_index.py`

- [ ] **Step 1: Write the failing tests**

```python
# backend/apps/recall/tests/test_index.py
import pytest
from apps.profiles.models import TradingProfile
from apps.thesis.models import Thesis
from apps.recall.models import RecallDocument
from apps.recall.services.index import index_one, pending

@pytest.mark.django_db
def test_index_one_upserts(monkeypatch):
    import apps.recall.services.index as idx
    monkeypatch.setattr(idx, "embed", lambda texts: [[0.0]*384 for _ in texts])
    p = TradingProfile.objects.create(name="P", default_includes=["quotes"])
    th = Thesis.objects.create(title="t", ticker="NVDA", direction="bullish", profile=p)
    index_one("thesis", th.id)
    doc = RecallDocument.objects.get(kind="thesis", object_id=th.id)
    assert doc.tickers == ["NVDA"] and doc.embedding is not None

@pytest.mark.django_db
def test_index_one_null_embedding_when_no_backend(monkeypatch):
    import apps.recall.services.index as idx
    monkeypatch.setattr(idx, "embed", lambda texts: None)
    p = TradingProfile.objects.create(name="P", default_includes=["quotes"])
    th = Thesis.objects.create(title="t", ticker="NVDA", direction="bullish", profile=p)
    index_one("thesis", th.id)
    assert RecallDocument.objects.get(kind="thesis", object_id=th.id).embedding is None

@pytest.mark.django_db
def test_pending_finds_unindexed():
    p = TradingProfile.objects.create(name="P", default_includes=["quotes"])
    th = Thesis.objects.create(title="t", ticker="NVDA", direction="bullish", profile=p)
    assert ("thesis", th.id) in list(pending(cap=50))
```

- [ ] **Step 2: Run — expect failure.**

- [ ] **Step 3: Implement** `backend/apps/recall/services/index.py`:

```python
from __future__ import annotations
from django.contrib.postgres.search import SearchVector
from apps.recall.embeddings import MODEL_NAME, embed
from apps.recall.models import RecallDocument
from apps.recall.text import build_text, content_hash, extract_tickers

def _source(kind, object_id):
    if kind == "thesis":
        from apps.thesis.models import Thesis; return Thesis.objects.filter(id=object_id).first()
    if kind == "journal":
        from apps.thesis.models import DecisionJournalEntry; return DecisionJournalEntry.objects.filter(id=object_id).first()
    if kind == "postmortem":
        from apps.thesis.models import PostMortem; return PostMortem.objects.filter(id=object_id).first()
    if kind == "snapshot":
        from apps.snapshots.models import Snapshot; return Snapshot.objects.filter(id=object_id).first()
    from apps.threads.models import Message
    return Message.objects.filter(id=object_id).first()       # message / observation

def _source_created_at(obj):
    return getattr(obj, "created_at", None) or getattr(obj, "captured_at", None)

def index_one(kind: str, object_id: int) -> None:
    obj = _source(kind, object_id)
    if obj is None:
        return
    text = build_text(kind, obj) or ""
    h = content_hash(text)
    existing = RecallDocument.objects.filter(kind=kind, object_id=object_id).first()
    if existing and existing.content_hash == h and existing.embedding is not None:
        return                                                # unchanged + already embedded
    vec = embed([text])
    embedding = vec[0] if vec else None
    doc, _ = RecallDocument.objects.update_or_create(
        kind=kind, object_id=object_id,
        defaults=dict(text=text, embedding=embedding,
                      embedding_model=MODEL_NAME if embedding is not None else "",
                      tickers=extract_tickers(kind, obj),
                      source_created_at=_source_created_at(obj), content_hash=h),
    )
    RecallDocument.objects.filter(pk=doc.pk).update(search=SearchVector("text", config="english"))

def pending(*, cap: int = 200):
    """Yield (kind, object_id) for indexable sources not current in RecallDocument."""
    from apps.threads.models import Message
    from apps.thesis.models import DecisionJournalEntry, PostMortem, Thesis
    from apps.snapshots.models import Snapshot
    seen = {(k, o) for k, o in RecallDocument.objects.values_list("kind", "object_id")}
    out, n = [], 0
    def add(kind, ids):
        nonlocal n
        for i in ids:
            if (kind, i) not in seen and n < cap:
                out.append((kind, i)); n += 1
    add("message", Message.objects.filter(role="assistant", status="done").values_list("id", flat=True))
    add("snapshot", Snapshot.objects.filter(status="ready").values_list("id", flat=True))
    add("thesis", Thesis.objects.values_list("id", flat=True))
    add("journal", DecisionJournalEntry.objects.values_list("id", flat=True))
    add("postmortem", PostMortem.objects.filter(status="done").values_list("id", flat=True))
    return out
```

> Re-indexing on edit (content_hash change) is handled by `index_one`; the `pending` sweep targets only not-yet-seen rows for cheapness — a periodic full `recall_backfill` (Step 5) catches edits. (Documented trade-off.)

- [ ] **Step 4: Tasks + command + beat.** `backend/apps/recall/tasks.py`:

```python
from celery import shared_task
from apps.recall.services.index import index_one, pending

@shared_task(name="recall.index_document")
def index_document(kind: str, object_id: int) -> None:
    index_one(kind, object_id)

@shared_task(name="recall.index_pending")
def index_pending() -> dict:
    items = pending(cap=200)
    for kind, oid in items:
        index_document.delay(kind, oid)
    return {"dispatched": len(items)}
```

`backend/apps/recall/management/commands/recall_backfill.py`: a `Command` that iterates `pending(cap=10**9)` and calls `index_one` synchronously (batched), printing progress.

`config/celery.py`: add `"apps.recall"` to `autodiscover_tasks([...])` and a beat entry:

```python
    "recall-index-pending": {"task": "recall.index_pending", "schedule": crontab(minute="*/5")},
```

- [ ] **Step 5: Run — expect pass + restart workers**

Run: `docker compose exec web pytest apps/recall/tests/test_index.py -v && docker compose restart worker beat`
Expected: PASS.

- [ ] **Step 6: Commit** `feat(recall): index sweep + tasks + backfill command + beat`.

---

## Task 6: Search service + API

**Files:** `services/search.py`, `serializers.py`, `views.py`, `urls.py`
- Test: `backend/apps/recall/tests/test_search.py`

- [ ] **Step 1: Write the failing tests**

```python
# backend/apps/recall/tests/test_search.py
import pytest
from rest_framework.test import APIClient
from apps.recall.models import RecallDocument
from apps.recall.services import search as S

def _doc(oid, vec, text="hello", ticker="NVDA"):
    return RecallDocument.objects.create(kind="thesis", object_id=oid, text=text,
        embedding=vec, embedding_model="m", tickers=[ticker], content_hash=str(oid))

@pytest.mark.django_db
def test_semantic_search_orders_by_cosine(monkeypatch):
    near = [1.0]+[0.0]*383; far = [0.0]*383+[1.0]
    a = _doc(1, near); b = _doc(2, far)
    monkeypatch.setattr(S, "embed", lambda texts: [near])
    hits = S.search("q", k=2)
    assert hits[0]["object_id"] == a.id

@pytest.mark.django_db
def test_fts_fallback_when_no_embedding(monkeypatch):
    from django.contrib.postgres.search import SearchVector
    d = _doc(1, None, text="nvidia earnings beat")
    RecallDocument.objects.filter(pk=d.pk).update(search=SearchVector("text"))
    monkeypatch.setattr(S, "embed", lambda texts: None)
    hits = S.search("earnings", k=5)
    assert any(h["object_id"] == d.id for h in hits)

@pytest.mark.django_db
def test_ticker_filter(monkeypatch):
    monkeypatch.setattr(S, "embed", lambda texts: [[1.0]+[0.0]*383])
    _doc(1, [1.0]+[0.0]*383, ticker="NVDA"); _doc(2, [1.0]+[0.0]*383, ticker="SPY")
    assert {h["object_id"] for h in S.search("q", k=5, ticker="NVDA")} == {1}
```

- [ ] **Step 2: Run — expect failure.**

- [ ] **Step 3: Implement** `backend/apps/recall/services/search.py`:

```python
from __future__ import annotations
from django.contrib.postgres.search import SearchQuery, SearchRank
from pgvector.django import CosineDistance
from apps.recall.embeddings import embed
from apps.recall.models import RecallDocument

_LINKS = {"message": "/threads", "snapshot": "/snapshots", "thesis": "/theses",
          "journal": "/theses", "postmortem": "/theses", "observation": "/threads"}

def _hit(d) -> dict:
    return {"kind": d.kind, "object_id": d.object_id, "snippet": (d.text or "")[:280],
            "source_created_at": d.source_created_at, "tickers": d.tickers,
            "link": f"{_LINKS.get(d.kind, '/recall')}/{d.object_id}"}

def _filtered(qs, kinds, ticker):
    if kinds: qs = qs.filter(kind__in=kinds)
    if ticker: qs = qs.filter(tickers__contains=[ticker.upper()])
    return qs

def search(q: str, *, k: int = 10, kinds=None, ticker=None) -> list[dict]:
    vec = embed([q])
    qs = _filtered(RecallDocument.objects.all(), kinds, ticker)
    if vec:
        qs = qs.filter(embedding__isnull=False).order_by(CosineDistance("embedding", vec[0]))
    else:
        sq = SearchQuery(q, config="english")
        qs = qs.annotate(rank=SearchRank("search", sq)).filter(search=sq).order_by("-rank")
    return [_hit(d) for d in qs[:k]]

def mode() -> str:
    return "semantic" if embed(["probe"]) else "keyword"

def related(kind: str, object_id: int, *, k: int = 5) -> list[dict]:
    seed = RecallDocument.objects.filter(kind=kind, object_id=object_id, embedding__isnull=False).first()
    if seed is None:
        return []
    qs = (RecallDocument.objects.filter(embedding__isnull=False)
          .exclude(pk=seed.pk).order_by(CosineDistance("embedding", seed.embedding)))
    return [_hit(d) for d in qs[:k]]

def related_to_ticker(ticker: str, *, k: int = 5) -> list[dict]:
    qs = (RecallDocument.objects.filter(tickers__contains=[ticker.upper()])
          .order_by("-source_created_at"))
    return [_hit(d) for d in qs[:k]]
```

- [ ] **Step 4: API.** `serializers.py` (a thin serializer or pass dicts through), `views.py` (function views like the market/analytics endpoints): `GET /api/recall/?q=&k=&kind=&ticker=` → `{results: search(...), mode: mode()}`; `GET /api/recall/related/?kind=&id=&k=` → `related(...)`; `GET /api/recall/status/` → per-kind counts + `mode`. Wire `urls.py` (already included before `/api/` in Task 2).

- [ ] **Step 5: Run — expect pass.** `docker compose exec web pytest apps/recall/tests/test_search.py -v`

- [ ] **Step 6: Commit** `feat(recall): semantic + FTS search/related services + API`.

---

## Task 7: AI `recall` tool

**Files:** `backend/apps/ai/tools/registry.py`; Test: `backend/apps/ai/tests/test_recall_tool.py`

- [ ] **Step 1: Write the failing test**

```python
# backend/apps/ai/tests/test_recall_tool.py
import pytest
from apps.ai.tools.registry import default_toolset

@pytest.mark.django_db
def test_recall_tool_registered(monkeypatch):
    import apps.recall.services.search as S
    monkeypatch.setattr(S, "search", lambda q, **k: [{"kind":"thesis","object_id":1,"snippet":"NVDA","link":"/theses/1"}])
    ts = default_toolset()
    out = ts.run("recall", {"query": "nvda"})
    assert out and out[0]["object_id"] == 1
```

- [ ] **Step 2: Run — expect failure.**

- [ ] **Step 3: Register the tool** in `default_toolset()` (`apps/ai/tools/registry.py`):

```python
def _recall(*, query: str, k: int = 5) -> list[dict]:
    from apps.recall.services.search import search
    return search(query, k=k)

    # inside default_toolset(), before `return ts`:
    ts.register(ToolSpec(
        name="recall",
        description="Search your own past observations, theses, snapshots, and notes by meaning. "
                    "Returns top matches with kind, snippet, and link.",
        input_schema={"type": "object", "properties": {
            "query": {"type": "string"},
            "k": {"type": "integer", "minimum": 1, "maximum": 20, "default": 5}},
            "required": ["query"]},
        fn=_recall))
```

- [ ] **Step 4: Run — expect pass.** **Step 5: Commit** `feat(recall): AI recall tool in the default toolset`.

---

## Task 8: Frontend — /recall page + RelatedObservations

**Files:** `frontend/src/api/recall.ts`, `hooks/useRecall.ts`, `pages/RecallPage.tsx`, `components/RelatedObservations.tsx`, router/nav; Test: `frontend/src/__tests__/RecallPage.test.tsx`

- [ ] **Step 1: API + hooks.** `api/recall.ts`: `recallSearch(params)`, `recallRelated({kind,id})`. `useRecall.ts`: `useRecall(q, filters)`, `useRelated(kind,id)`.

- [ ] **Step 2: Failing test** — `RecallPage` renders results (snippet + kind badge + link) for a mocked `/api/recall/?q=`, and shows the `mode` badge ("semantic"/"keyword").

- [ ] **Step 3: Run — expect failure.** `docker compose exec frontend pnpm exec vitest run src/__tests__/RecallPage.test.tsx`

- [ ] **Step 4: Build** `RecallPage.tsx` (query box + kind/ticker filters + grouped results + mode badge, `Skeleton`/`EmptyState`, ledger tokens), and `<RelatedObservations kind id>` (renders `useRelated` top-K links). Mount `<RelatedObservations>` on `ThreadDetailPage` and the Snapshot detail (snapshot keyed via `related_to_ticker(primary_ticker)` — call a `related?ticker=` variant). Wire route `{ path: "recall", element: <RecallPage/>, handle: { crumb: "Recall" } }`, SideNav entry, `go-recall` Cmd-K command, a free `g` shortcut.

- [ ] **Step 5: Run — expect pass + lint.** `docker compose exec frontend pnpm exec vitest run src/__tests__/RecallPage.test.tsx && docker compose exec frontend pnpm run lint`

- [ ] **Step 6: Commit** `feat(frontend): /recall search page + RelatedObservations panel`.

---

## Task 9: E2E recall check

**Files:** `e2e/api/test_recall_search.py`

- [ ] **Step 1: Write the test** (under `MOCK_EXTERNAL`): create a thesis, run `manage.py recall_backfill` (or call `index_one`), `GET /api/recall/?q=<word in the thesis>` and assert a hit with the right `object_id`. Assert `status` endpoint reports counts. Embeddings are local so this works without keys.

- [ ] **Step 2: Run.** `make e2e-one t=api/test_recall_search.py` (after `make e2e-up`). Fix the feature, not the assertion.

- [ ] **Step 3: Commit** `test(e2e): recall backfill + search returns a hit`.

---

## Final verification

- [ ] `docker compose exec web pytest apps/recall -q` — green.
- [ ] `make migrate` clean from scratch on a fresh volume (extension + HNSW/GIN apply): `docker compose down -v && docker compose up -d && make migrate`.
- [ ] `manage.py recall_backfill` populates documents; `/api/recall/status/` shows counts + `mode=semantic`.
- [ ] `make check` — green.

## Self-review (completed against the spec)

- **Spec coverage:** pgvector image + extension + deps + model bake (Task 1) · `RecallDocument` + HNSW + GIN (2) · local `embed()` + None fallback (3) · per-kind text/tickers (4) · sweep + backfill + beat (5) · semantic + FTS search + related (6) · AI `recall` tool (7) · `/recall` page + `RelatedObservations` (8) · e2e (9). All sections map.
- **Placeholders:** none in code steps; the API view (6 Step 4) and frontend (8) describe wiring but pin behavior via tests.
- **Type consistency:** `embed()` signature stable across Tasks 3/5/6; `index_one`/`pending` signatures match tasks.py + the command; `_hit` dict shape (`kind/object_id/snippet/link`) is what the `recall` tool test (7) and frontend (8) consume; `RecallDocument` fields match across model (2), index (5), search (6); `DIM=384`/`VectorField(384)` consistent.
- **Dependency note:** uses `Snapshot.primary_ticker` (Snapshot Intelligence) in `text.extract_tickers` and `related_to_ticker` — Snapshot Intelligence must be merged first (matches the build order).
