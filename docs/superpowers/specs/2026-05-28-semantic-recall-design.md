# Semantic Recall (`apps.recall`) — design

**Date:** 2026-05-28
**Status:** Approved (pending spec review)
**Topic:** A unified semantic search + auto-resurfacing layer over the dashboard's entire AI corpus — every past observation, thread message, thesis, decision-journal entry, observation report, and post-mortem — by *meaning*, not keyword. pgvector embeddings (local, offline) + a `/recall` search page + a "you observed this before" auto-resurface panel + an AI `recall` tool. Spec 3 (the flagship) of a three-spec batch (Snapshot Intelligence → Triggers v2 → Semantic Recall). This is roadmap feature #4 — the only named roadmap item with no prior spec, and the one capability the M11 "second brain" set up but never delivered.

## Problem

The dashboard generates a large, growing volume of AI output — observations, theses, journal entries, post-mortems — but it is **write-only**: there is no way to ask "didn't the AI flag exactly this on NVDA back in March?" Today you would have to remember which thread it was in and scroll. The archive is an asset the product can't yet use. There is **zero** embedding/vector/recall code in the repo — this is a fresh build, not a half-finished one.

Recall turns the archive into Luhmann's "conversation partner": surfacing past reasoning by similarity, both on demand (a search page + an AI tool) and proactively (resurfacing the most-similar prior observations whenever you open a new snapshot or thread on a ticker). It slots into two established patterns — the on-demand `apps.analytics` service+view+hook shape, and the opt-in tool registry — plus one new platform dependency (pgvector + a local embedding model).

## Non-goals (YAGNI)

- **No multi-user / sharing** — single-user brain.
- **No OpenAI-compatible embedding backend in v3.** Local `fastembed` only; the `embed()` seam leaves the door open to add it later with no call-site change.
- **No re-embedding-on-model-change automation** beyond the `recall_backfill` management command (changing the model/dimension is a deliberate, documented re-backfill).
- **No cross-encoder re-ranking, no per-chunk splitting** of long documents — embed the whole document text, truncated to the model's window.
- **No embedding of raw user free-text messages** — only AI/structured artifacts (assistant `done` messages, snapshots, theses, journal entries, observation reports, post-mortems).
- **No scheduled "trend" alerts off recall** — search + resurface only.

## Design decisions (settled during brainstorming)

| Decision | Choice | Rationale |
|---|---|---|
| Embedding backend | Local `fastembed` (`BAAI/bge-small-en-v1.5`, 384-dim), ONNX, no torch | Works for everyone with no key/cost, fully offline, on-brand local-first; far lighter than torch |
| No-backend fallback | Postgres full-text search (FTS) | The "degrade with no key" guardrail — `/recall` always works, lexically when the model is absent |
| Backend seam | `embed(texts) -> list[list[float]] | None` | Swappable later (OpenAI-compatible) with no call-site changes |
| pgvector | Swap `db` to `pgvector/pgvector:pg17` (same PG17) | Volume-compatible image swap; `CREATE EXTENSION vector` via migration |
| Storage | One central `RecallDocument` (kind + object_id + text + vector) | One place to search/backfill/index; HNSW cosine index; avoids vector columns on six models |
| Indexing | Periodic `recall.index_pending` sweep + `recall_backfill` command | Decoupled (no signals on six save paths); minutes-latency is fine for a brain |
| Model home | Baked into `web` + `worker` images at build | Offline at runtime; web embeds the query, worker embeds documents |

## Architecture

```
 sources (Message done / Snapshot / Thesis / JournalEntry / ObservationReport / PostMortem)
        │
 recall.index_pending (beat, ~few min): find unindexed / content-changed rows, cap per tick
        └─ recall.index_document(kind, id): text.build(kind, obj) → embed([text]) → upsert RecallDocument
                                                                   (None → store text only, embedding NULL)
        manage.py recall_backfill  ── one-time initial load (same path) ──┘

 RecallDocument(kind, object_id, text, embedding VectorField(384) NULL, embedding_model,
                tickers, source_created_at, content_hash, indexed_at)
        ├─ HNSW(embedding, vector_cosine_ops)         ← semantic KNN
        └─ GIN(search SearchVectorField)              ← FTS fallback

 QUERY:  GET /api/recall/?q=&k=&kind=&ticker=
            search.search(q): embed(q) → order_by(CosineDistance) ; else SearchRank(FTS)
            → [{kind, object_id, snippet, score, source_created_at, tickers, link}]

 RESURFACE: GET /api/recall/related/?kind=&id=&k=  (or ?ticker=)
            search.related(seed): KNN on seed's embedding, exclude self
            → <RelatedObservations> panel on ThreadDetailPage + Snapshot detail

 AI TOOL:  default_toolset() registers ToolSpec("recall", fn=_recall)  (opt-in via profile.enable_tools)
```

### 1. Platform — db image + extension + deps

- **`db` image:** `postgres:17-alpine` → `pgvector/pgvector:pg17` in `compose.yaml`, `compose.e2e.yaml`, and the prod overlay (and the `db-e2e` service). Same major version 17 → existing `pg_data` volume is reused; no dump/restore.
- **Migration `0001`** (apps.recall): first operation `pgvector.django.VectorExtension()` (`CREATE EXTENSION IF NOT EXISTS vector`; reversible) — ordered **before** the `CreateModel` that uses `VectorField`.
- **Deps (`pyproject.toml`):** `pgvector` (Django integration) + `fastembed`. `uv.lock` regenerated; images rebuilt (`uv sync --frozen`).
- **Model bake:** `backend/Dockerfile` (`web` + `worker` targets) downloads `BAAI/bge-small-en-v1.5` at build (a tiny `python -c "from fastembed import TextEmbedding; TextEmbedding('BAAI/bge-small-en-v1.5')"` warms the cache into the image). ~+300MB/image + longer cold build (documented, like the chromium note).

### 2. Model — `apps/recall/models.py`

```python
from pgvector.django import VectorField, HnswIndex
from django.contrib.postgres.search import SearchVectorField
from django.contrib.postgres.indexes import GinIndex

class RecallDocument(models.Model):
    KIND_CHOICES = [("message","Message"),("snapshot","Snapshot"),("thesis","Thesis"),
                    ("journal","Journal"),("observation","Observation"),("postmortem","PostMortem")]
    kind = models.CharField(max_length=16, choices=KIND_CHOICES)
    object_id = models.IntegerField()
    text = models.TextField()
    embedding = VectorField(dimensions=384, null=True, blank=True)
    embedding_model = models.CharField(max_length=64, blank=True, default="")
    tickers = models.JSONField(default=list)              # for ?ticker= filtering
    source_created_at = models.DateTimeField(null=True, blank=True)
    content_hash = models.CharField(max_length=64)        # skip re-embed when unchanged
    indexed_at = models.DateTimeField(auto_now=True)
    search = SearchVectorField(null=True)                 # FTS fallback (populated on index)

    class Meta:
        constraints = [models.UniqueConstraint(fields=["kind","object_id"], name="uniq_recall_doc")]
        indexes = [
            HnswIndex(name="recall_emb_hnsw", fields=["embedding"],
                      m=16, ef_construction=64, opclasses=["vector_cosine_ops"]),
            GinIndex(fields=["search"], name="recall_search_gin"),
            models.Index(fields=["kind", "object_id"]),
            models.Index(fields=["-source_created_at"]),
        ]
```

### 3. Embedding seam — `apps/recall/embeddings.py`

```python
MODEL_NAME = "BAAI/bge-small-en-v1.5"
DIM = 384

def embed(texts: list[str]) -> list[list[float]] | None:
    """Return one 384-vector per input, or None if no backend is available.
    Lazily constructs a module-singleton fastembed TextEmbedding; any import/load
    failure → None so callers fall back to FTS. Never raises."""
```

`AI_RECALL_EMBED_MODEL` setting can override the model name (tests stub `embed`). A `None` return is the single signal that flips search/index into FTS-only mode.

### 4. Text builders — `apps/recall/text.py` (pure)

`build_text(kind, obj) -> str` and `extract_tickers(kind, obj) -> list[str]`, per kind — message→`content` text (blocks flattened); snapshot→`serialize_for_ai(snap)` (`apps/snapshots/serializer.py:12`), truncated; thesis→`title + rationale + ticker/direction`; journal→`note`; observation→report text; postmortem→report narrative. Tickers from `snapshot.primary_ticker` (Spec 1), `thesis.ticker`, or the source's `snapshot_ref`. Tolerates missing fields (never raises). `content_hash = sha256(text)`.

### 5. Indexing — `apps/recall/tasks.py` + `services/index.py`

- `@shared_task(name="recall.index_pending")` (beat, e.g. `crontab(minute="*/5")`): for each kind, select source rows **not** in `RecallDocument` (or whose recomputed `content_hash` differs), capped (e.g. 200/tick), and dispatch `recall.index_document(kind, id)`. Messages are `role="assistant", status="done"` only.
- `@shared_task(name="recall.index_document")`: load source → `build_text` → `embed([text])` (batchable) → upsert `RecallDocument` (set `embedding` or leave null on `None`; set `search = SearchVector(text)`; store `embedding_model`, `tickers`, `source_created_at`, `content_hash`).
- `manage.py recall_backfill [--kinds …]`: the one-time initial load over existing rows (same code path, batched embeds).
- `apps.recall` added to the explicit `autodiscover_tasks([...])` list and a beat entry; **`docker compose restart worker beat`** after adding.

### 6. Search — `apps/recall/services/search.py`

```python
def search(q, *, k=10, kinds=None, ticker=None) -> list[Hit]:
    qs = RecallDocument.objects.all()
    if kinds:  qs = qs.filter(kind__in=kinds)
    if ticker: qs = qs.filter(tickers__contains=[ticker.upper()])
    vec = embed([q])
    if vec is not None:
        qs = qs.filter(embedding__isnull=False).order_by(CosineDistance("embedding", vec[0]))
    else:
        sq = SearchQuery(q); qs = qs.annotate(rank=SearchRank("search", sq)).filter(search=sq).order_by("-rank")
    return [_to_hit(d) for d in qs[:k]]      # Hit: kind, object_id, snippet, score, source_created_at, tickers, link

def related(kind, object_id, *, k=5) -> list[Hit]:    # KNN on the seed's stored embedding, exclude self
def related_to_ticker(ticker, *, k=5) -> list[Hit]:
```

`_to_hit.link` resolves each source to its route (`/threads/<id>` for message, snapshot detail for snapshot, `/theses/<id>` for thesis, …). The response also reports `mode: "semantic" | "keyword"` so the UI can badge it.

### 7. Surfaces

- **API** (`apps/recall/{views,urls}.py`, function views like the market/analytics endpoints, placed **before** the generic `/api/` include):
  - `GET /api/recall/?q=&k=&kind=&ticker=` — search.
  - `GET /api/recall/related/?kind=&id=&k=` (or `?ticker=`) — resurface.
  - `GET /api/recall/status/` — indexed counts per kind + `mode` (semantic/keyword) + model.
- **AI `recall` tool:** add a `ToolSpec(name="recall", description="Search your own past observations, theses, and notes by meaning. Returns top matches with source + snippet.", input_schema={query, k?}, fn=_recall)` to `default_toolset()` (`apps/ai/tools/registry.py`). `_recall` calls `search.search` and returns compact hits. Opt-in via the existing `profile.enable_tools`; provider-agnostic (Claude + OpenAI/local via the parity loop).
- **Frontend:**
  - `/recall` page (`RecallPage.tsx`): query box + kind/ticker filters → results grouped by kind, each with snippet + link + a "semantic/keyword" mode badge. `Skeleton`/`EmptyState`.
  - `<RelatedObservations>` panel: mounted on `ThreadDetailPage` and the Snapshot detail; calls `related`/`related_to_ticker` (snapshot keyed by its `primary_ticker` from Spec 1) and shows top-K "you noted this before" links.
  - `api/recall.ts` + `useRecall`/`useRelated` hooks; SideNav entry + `go-recall` Cmd-K command + a free `g <x>` shortcut.

### 8. Degradation

`embed()` returns `None` (fastembed/model missing or load error) → indexing stores `text` + `search` with a null `embedding`; search uses FTS. The `/recall` page, `related` panel, and `recall` tool all keep working (lexically). When a model becomes available, a later sweep / `recall_backfill` fills the null embeddings. The brain is never dark.

### 9. Testing

- **`test_embeddings.py`** — `embed` returns 384-vectors with a stubbed backend; `None` on load failure (never raises).
- **`test_text.py`** — per-kind `build_text`/`extract_tickers`/`content_hash`; missing-field tolerance.
- **`test_index.py`** — sweep selects only unindexed/changed rows, respects the cap, messages filtered to assistant/done; `index_document` upsert + null-embedding path; `content_hash` skip.
- **`test_search.py`** — semantic ordering (mock vectors) + FTS fallback ranking + `kind`/`ticker` filters; `related` excludes self; `mode` flag.
- **`test_tool.py`** — the `recall` tool returns hits via the registry.
- **Migration** — `VectorExtension` + model + HNSW/GIN apply on a pgvector test DB; reversible.
- **Frontend (`vitest`)** — `RecallPage` (loading/empty/results, mode badge) + `<RelatedObservations>`.
- **E2E (`api`)** — `recall_backfill` → `GET /api/recall/?q=` returns a hit under `MOCK_EXTERNAL` (embedding stubbed/local).

### 10. Ops & migrations

- **db image swap** in all three overlays + `db-e2e`; existing PG17 volume reused.
- `apps/recall/migrations/0001`: `VectorExtension()` → `CreateModel(RecallDocument)` → HNSW + GIN indexes (reversible).
- `pyproject` deps (`pgvector`, `fastembed`) + `uv.lock` → **image rebuild** + model bake (Dockerfile change, longer cold build, ~+300MB).
- `INSTALLED_APPS += "apps.recall"`; `autodiscover_tasks += "apps.recall"`; `index_pending` beat entry; **`docker compose restart worker beat`**.
- `manage.py recall_backfill` run once post-deploy.
- No new credential or external network dependency (embedding is local).

## Implementation order (for the plan)

1. Platform: db image swap + `pgvector`/`fastembed` deps + `uv.lock` + Dockerfile model bake.
2. `apps.recall` scaffold (app, INSTALLED_APPS, urls-before-`/api/`) + `RecallDocument` + `0001` migration (extension + model + indexes).
3. `embeddings.embed()` seam + `text.py` builders + tests (mock backend).
4. `services/index.py` + `tasks.py` (`index_document`, `index_pending`) + `recall_backfill` command + beat entry + tests.
5. `services/search.py` (`search`/`related`/`related_to_ticker`) + API views/urls + tests.
6. AI `recall` tool in the registry + test.
7. Frontend: `api/recall.ts`, hooks, `RecallPage`, `<RelatedObservations>` on thread + snapshot detail, nav/command/shortcut, vitest.
8. E2E `api` recall check.

Steps 3–6 depend on 1–2; step 5 depends on 3 (embed) + 4 (indexed data to search); step 7 depends on 5; the `recall` tool (6) is independent of the frontend.
