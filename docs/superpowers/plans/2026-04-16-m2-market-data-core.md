# M2 Market Data Core Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Live Schwab integration — OAuth-connect your Schwab account, ingest quotes / OHLC / positions / market context into Postgres with a Redis-cached read layer, manage watchlists via CRUD REST, and render a basic watchlist + per-ticker UI. After M2, the dashboard shows your real account data and current market state.

**Architecture:**
- `apps/secrets` (new) — `ApiCredential` model with Fernet-encrypted blob field; Schwab OAuth token exchange + refresh live here.
- `apps/market` (new) — Schwab client factory (via `schwab.auth.client_from_access_functions`), fetch services (quotes / OHLC / positions / context), Redis cache helpers, DRF endpoints.
- `apps/profiles` (new) — `Watchlist` + `WatchlistSymbol` models + CRUD endpoints. (Full `TradingProfile` comes in M3.)
- Frontend adds `/settings`, `/watchlists`, `/watchlists/:id`, `/market/:ticker` and a dashboard widget. TanStack Query layered on for server state + polling.

**Tech Stack (additions to M1):**
- `schwab-py` (Schwab API client)
- `cryptography` (Fernet encryption for token storage)
- `httpx` (already pulled in by schwab-py; used directly for the OAuth token exchange)
- `pandas` (schwab-py dependency; we use it for OHLC normalization)
- `@tanstack/react-query` v5 (frontend server state)
- `date-fns` (frontend timestamps)

---

## File Layout Added by This Plan

```
backend/apps/
├── secrets/                          # New app: encrypted credential storage + OAuth
│   ├── __init__.py  apps.py  admin.py
│   ├── models.py                     # ApiCredential
│   ├── fields.py                     # EncryptedJSONField (Fernet)
│   ├── schwab_oauth.py               # Token exchange (authorize → code → token), refresh
│   ├── urls.py  views.py             # /api/schwab/authorize, /api/schwab/callback, /api/schwab/status
│   ├── migrations/
│   └── tests/
│       ├── test_encrypted_field.py
│       ├── test_schwab_oauth.py
│       └── test_status_endpoint.py
├── market/                           # New app: market data
│   ├── __init__.py  apps.py  admin.py
│   ├── models.py                     # Quote, OHLCBar, Position, MarketContext
│   ├── schwab_client.py              # get_schwab_client() factory, token read/write
│   ├── cache.py                      # Redis cache helpers (get-or-fetch, TTL table)
│   ├── services/
│   │   ├── __init__.py
│   │   ├── quotes.py                 # fetch_quotes(tickers)
│   │   ├── ohlc.py                   # fetch_ohlc(ticker, timeframe, bars)
│   │   ├── positions.py              # fetch_positions()
│   │   └── context.py                # fetch_market_context()  — SPY/QQQ/VIX + sectors + breadth
│   ├── serializers.py                # DRF serializers
│   ├── urls.py  views.py             # /api/market/{quotes,ohlc,positions,context}
│   ├── tasks.py                      # celery task: refresh_schwab_token
│   ├── migrations/
│   └── tests/
│       ├── test_cache.py
│       ├── test_services_quotes.py
│       ├── test_services_ohlc.py
│       ├── test_services_positions.py
│       ├── test_services_context.py
│       └── test_endpoints.py
└── profiles/                         # New app: watchlists (trading profiles come in M3)
    ├── __init__.py  apps.py  admin.py
    ├── models.py                     # Watchlist, WatchlistSymbol
    ├── serializers.py
    ├── urls.py  views.py             # /api/watchlists/, /api/watchlists/<id>/, .../symbols/
    ├── migrations/
    └── tests/
        ├── test_watchlist_crud.py
        └── test_symbol_crud.py

frontend/src/
├── api/
│   ├── client.ts                     # (modified) add apiGet/apiPost/apiDelete helpers
│   ├── market.ts                     # fetchQuotes, fetchOhlc, fetchPositions, fetchContext
│   ├── watchlists.ts                 # CRUD
│   └── schwab.ts                     # schwabStatus, schwabAuthorizeUrl
├── hooks/
│   ├── useQueryClient.ts             # (TanStack QueryClient instance)
│   ├── useQuotes.ts
│   ├── useOhlc.ts
│   ├── usePositions.ts
│   ├── useMarketContext.ts
│   ├── useWatchlists.ts
│   ├── useWatchlist.ts
│   └── useSchwabStatus.ts
├── components/
│   ├── QuoteCell.tsx                 # price + %change pill
│   ├── WatchlistTable.tsx
│   ├── PositionsTable.tsx
│   ├── MarketContextStrip.tsx
│   └── SchwabConnectionCard.tsx
├── pages/
│   ├── Dashboard.tsx                 # (replaces App.tsx's health shell)
│   ├── Settings.tsx
│   ├── WatchlistsList.tsx
│   ├── WatchlistDetail.tsx
│   └── MarketTicker.tsx
├── App.tsx                           # (modified) router + QueryClientProvider
└── router.tsx                        # React Router v6 routes
```

Responsibility recap:
- **`apps/secrets`** owns anything touching third-party credentials and their encryption. No market logic lives here.
- **`apps/market`** owns Schwab client construction and data fetching. No credential storage logic (it asks `apps/secrets` for tokens).
- **`apps/profiles`** owns user-facing taxonomy (watchlists now, profiles in M3). No market data logic.

---

## Task 1: Add M2 dependencies

**Files:** `pyproject.toml`, `frontend/package.json`

- [ ] **Step 1.1: Add Python deps to `pyproject.toml`**

In `[project].dependencies`, add after the existing entries:

```toml
    "schwab-py>=1.4,<2.0",
    "cryptography>=43,<44",
    "pandas>=2.2,<3.0",
```

- [ ] **Step 1.2: Add frontend deps**

Edit `frontend/package.json` `dependencies` to add:

```json
    "@tanstack/react-query": "^5.59.0",
    "date-fns": "^4.1.0",
    "react-router-dom": "^6.27.0"
```

- [ ] **Step 1.3: Rebuild images to pick up new deps**

```bash
cd /home/dan/ai-dashboard
docker compose build web worker beat frontend
docker compose up -d
sleep 10
docker compose exec web python -c "import schwab, cryptography, pandas; print('ok')"
docker compose exec frontend node -e "require('@tanstack/react-query'); require('react-router-dom'); console.log('ok')"
```

Expected: both print `ok`.

- [ ] **Step 1.4: Commit**

```bash
git add pyproject.toml frontend/package.json
git commit -m "chore(deps): add schwab-py, cryptography, pandas, tanstack-query, react-router"
```

---

## Task 2: Fernet encrypted JSON field (TDD)

**Files:**
- Create: `backend/apps/secrets/__init__.py`, `apps.py`
- Create: `backend/apps/secrets/fields.py`
- Create: `backend/apps/secrets/tests/__init__.py`, `test_encrypted_field.py`
- Modify: `backend/config/settings/base.py` (add app + `ENCRYPTION_KEY` derivation)

- [ ] **Step 2.1: Scaffold the `secrets` app**

```bash
mkdir -p /home/dan/ai-dashboard/backend/apps/secrets/tests
touch /home/dan/ai-dashboard/backend/apps/secrets/__init__.py
touch /home/dan/ai-dashboard/backend/apps/secrets/tests/__init__.py
```

Write `backend/apps/secrets/apps.py`:

```python
from django.apps import AppConfig


class SecretsConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "apps.secrets"
    label = "secrets_app"  # "secrets" would collide with Python's stdlib
```

- [ ] **Step 2.2: Register the app**

Edit `backend/config/settings/base.py` `INSTALLED_APPS` — after `"apps.core"` add:

```python
    "apps.secrets",
```

And after the `REDIS_URL = ...` block, add encryption-key derivation:

```python
import base64
import hashlib

# Deterministic Fernet key derived from SECRET_KEY + a per-install salt.
# The salt is generated on first boot (apps/secrets/keys.py) — it's a 32-byte random file
# at /data/secret.salt. Losing it permanently destroys stored credentials.
_ENCRYPTION_SALT_PATH = env.str("ENCRYPTION_SALT_PATH", default="/data/secret.salt")
```

(The `keys.py` module that actually reads/generates the salt is created in the next step.)

- [ ] **Step 2.3: Write failing encrypted-field test**

Write `backend/apps/secrets/tests/test_encrypted_field.py`:

```python
import json

import pytest

from apps.secrets.fields import EncryptedJSONField, derive_fernet_key


def test_derive_fernet_key_is_deterministic_for_same_inputs():
    k1 = derive_fernet_key(b"secret-key-abc", b"salt-bytes-16xxx")
    k2 = derive_fernet_key(b"secret-key-abc", b"salt-bytes-16xxx")
    assert k1 == k2
    # Fernet keys are 44-char urlsafe-base64-encoded 32-byte strings
    assert len(k1) == 44
    assert isinstance(k1, bytes)


def test_derive_fernet_key_changes_with_salt():
    k1 = derive_fernet_key(b"same-key", b"salt-one-bytes..")
    k2 = derive_fernet_key(b"same-key", b"salt-two-bytes..")
    assert k1 != k2


def test_field_roundtrip_encrypts_json():
    field = EncryptedJSONField()
    payload = {"access_token": "abc123", "expires_at": 1234567890, "nested": [1, 2, {"k": "v"}]}
    encrypted = field.get_prep_value(payload)
    assert isinstance(encrypted, bytes)
    # Ciphertext must NOT contain the plaintext
    assert b"abc123" not in encrypted

    decrypted = field.from_db_value(encrypted, expression=None, connection=None)
    assert decrypted == payload


def test_field_handles_none():
    field = EncryptedJSONField(null=True)
    assert field.get_prep_value(None) is None
    assert field.from_db_value(None, expression=None, connection=None) is None


def test_field_rejects_tampered_ciphertext():
    from cryptography.fernet import InvalidToken
    field = EncryptedJSONField()
    encrypted = field.get_prep_value({"a": 1})
    tampered = encrypted[:-5] + b"XXXXX"
    with pytest.raises(InvalidToken):
        field.from_db_value(tampered, expression=None, connection=None)
```

- [ ] **Step 2.4: Write `backend/apps/secrets/keys.py`**

```python
"""Encryption key derivation.

Key = HKDF(DJANGO_SECRET_KEY, salt=file(/data/secret.salt)). The salt is a 32-byte
random file, generated on first call if missing. Losing the salt destroys all
stored credentials — back it up alongside /data if you care.
"""
from __future__ import annotations

import base64
import os
import secrets as py_secrets
from pathlib import Path

from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.kdf.hkdf import HKDF
from django.conf import settings


def _load_or_create_salt(path: Path) -> bytes:
    if path.exists():
        return path.read_bytes()
    path.parent.mkdir(parents=True, exist_ok=True)
    salt = py_secrets.token_bytes(32)
    path.write_bytes(salt)
    os.chmod(path, 0o600)
    return salt


def derive_fernet_key_from_settings() -> bytes:
    salt_path = Path(settings._ENCRYPTION_SALT_PATH if hasattr(settings, "_ENCRYPTION_SALT_PATH") else "/data/secret.salt")
    # settings._ENCRYPTION_SALT_PATH is defined in base.py
    salt = _load_or_create_salt(salt_path)
    return derive_fernet_key(settings.SECRET_KEY.encode("utf-8"), salt)


def derive_fernet_key(secret: bytes, salt: bytes) -> bytes:
    """HKDF-SHA256 → 32 bytes → urlsafe-base64 (Fernet expects this form)."""
    raw = HKDF(
        algorithm=hashes.SHA256(),
        length=32,
        salt=salt,
        info=b"ai-dashboard-fernet-v1",
    ).derive(secret)
    return base64.urlsafe_b64encode(raw)
```

- [ ] **Step 2.5: Write `backend/apps/secrets/fields.py`**

```python
"""Django field that transparently encrypts JSON payloads with Fernet.

Usage:
    class MyModel(models.Model):
        token = EncryptedJSONField(null=True)

Stored on disk as raw Fernet ciphertext in a BYTEA column. Decrypted lazily on read.
"""
from __future__ import annotations

import json
from typing import Any

from cryptography.fernet import Fernet
from django.db import models

from apps.secrets.keys import derive_fernet_key_from_settings, derive_fernet_key

__all__ = ["EncryptedJSONField", "derive_fernet_key"]


def _fernet() -> Fernet:
    return Fernet(derive_fernet_key_from_settings())


class EncryptedJSONField(models.BinaryField):
    """Stores an arbitrary JSON-serializable value encrypted with Fernet."""

    description = "JSON value encrypted with Fernet"

    def from_db_value(self, value: bytes | None, expression, connection) -> Any:
        if value is None:
            return None
        plaintext = _fernet().decrypt(bytes(value))
        return json.loads(plaintext.decode("utf-8"))

    def to_python(self, value: Any) -> Any:
        # When a dict has just been assigned (not loaded from DB), pass through.
        if value is None or isinstance(value, (dict, list, str, int, float, bool)):
            return value
        return self.from_db_value(value, None, None)

    def get_prep_value(self, value: Any) -> bytes | None:
        if value is None:
            return None
        plaintext = json.dumps(value, separators=(",", ":"), sort_keys=True).encode("utf-8")
        return _fernet().encrypt(plaintext)
```

- [ ] **Step 2.6: Run tests and verify pass**

```bash
docker compose exec web pytest backend/apps/secrets/tests/test_encrypted_field.py -v
```

Expected: 4 passed.

- [ ] **Step 2.7: Commit**

```bash
git add backend/apps/secrets backend/config/settings/base.py
git commit -m "feat(secrets): fernet-encrypted json field + HKDF key derivation"
```

---

## Task 3: `ApiCredential` model (TDD)

**Files:**
- Create: `backend/apps/secrets/models.py`
- Create: `backend/apps/secrets/tests/test_models.py`
- Create: migration via `manage.py makemigrations`

- [ ] **Step 3.1: Write failing model test**

Write `backend/apps/secrets/tests/test_models.py`:

```python
import pytest
from django.utils import timezone
from datetime import timedelta

from apps.secrets.models import ApiCredential


@pytest.mark.django_db
def test_create_credential_stores_token_encrypted():
    cred = ApiCredential.objects.create(
        provider="schwab",
        token={"access_token": "A", "refresh_token": "R", "expires_at": 123},
        expires_at=timezone.now() + timedelta(hours=1),
    )
    cred.refresh_from_db()
    assert cred.token == {"access_token": "A", "refresh_token": "R", "expires_at": 123}


@pytest.mark.django_db
def test_unique_per_provider():
    ApiCredential.objects.create(provider="schwab", token={"a": 1})
    with pytest.raises(Exception):
        ApiCredential.objects.create(provider="schwab", token={"a": 2})


@pytest.mark.django_db
def test_is_expired_helper():
    past = ApiCredential(provider="schwab", token={}, expires_at=timezone.now() - timedelta(minutes=1))
    future = ApiCredential(provider="schwab", token={}, expires_at=timezone.now() + timedelta(minutes=10))
    none = ApiCredential(provider="schwab", token={})
    assert past.is_expired() is True
    assert future.is_expired() is False
    assert none.is_expired() is True  # no expiry recorded → treat as expired
```

- [ ] **Step 3.2: Write `backend/apps/secrets/models.py`**

```python
"""Encrypted per-provider credential storage."""
from __future__ import annotations

from django.db import models
from django.utils import timezone

from apps.secrets.fields import EncryptedJSONField


class ApiCredential(models.Model):
    """One row per third-party provider (schwab, news, ...)."""

    PROVIDER_CHOICES = [
        ("schwab", "Charles Schwab"),
        ("finnhub", "Finnhub"),
        ("marketaux", "Marketaux"),
    ]

    provider = models.CharField(max_length=32, choices=PROVIDER_CHOICES, unique=True)
    token = EncryptedJSONField(null=True, blank=True)  # full OAuth token dict or {"api_key": "..."}
    expires_at = models.DateTimeField(null=True, blank=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "secrets_apicredential"

    def __str__(self) -> str:
        return f"{self.get_provider_display()} (expires: {self.expires_at or 'never'})"

    def is_expired(self) -> bool:
        if self.expires_at is None:
            return True
        return timezone.now() >= self.expires_at
```

- [ ] **Step 3.3: Generate + apply migration**

```bash
docker compose exec web python manage.py makemigrations secrets_app
docker compose exec web python manage.py migrate
```

- [ ] **Step 3.4: Run tests**

```bash
docker compose exec web pytest backend/apps/secrets/tests/test_models.py -v
```

Expected: 3 passed.

- [ ] **Step 3.5: Commit**

```bash
git add backend/apps/secrets/models.py backend/apps/secrets/tests/test_models.py backend/apps/secrets/migrations/
git commit -m "feat(secrets): ApiCredential model with encrypted token storage"
```

---

## Task 4: Schwab OAuth token exchange + refresh (TDD)

**Files:**
- Create: `backend/apps/secrets/schwab_oauth.py`
- Create: `backend/apps/secrets/tests/test_schwab_oauth.py`
- Modify: `backend/config/settings/base.py` (add `SCHWAB_CLIENT_ID`, `SCHWAB_CLIENT_SECRET`, `SCHWAB_CALLBACK_URL`)
- Modify: `.env.example` (add the three `SCHWAB_*` keys)

Schwab OAuth endpoints (from schwab-py source + Schwab developer docs):
- Authorize URL: `https://api.schwabapi.com/v1/oauth/authorize`
- Token URL: `https://api.schwabapi.com/v1/oauth/token`
- Access token TTL: 30 min. Refresh token TTL: 7 days.

- [ ] **Step 4.1: Add Schwab settings**

Edit `backend/config/settings/base.py` — add near the bottom:

```python
# Schwab OAuth
SCHWAB_CLIENT_ID = env("SCHWAB_CLIENT_ID", default="")
SCHWAB_CLIENT_SECRET = env("SCHWAB_CLIENT_SECRET", default="")
SCHWAB_CALLBACK_URL = env("SCHWAB_CALLBACK_URL", default="https://127.0.0.1:8000/api/schwab/callback")
SCHWAB_AUTHORIZE_URL = "https://api.schwabapi.com/v1/oauth/authorize"
SCHWAB_TOKEN_URL = "https://api.schwabapi.com/v1/oauth/token"
```

Edit `.env.example` — append:

```bash

# Schwab OAuth (register your app at https://developer.schwab.com; callback must match exactly)
SCHWAB_CLIENT_ID=
SCHWAB_CLIENT_SECRET=
SCHWAB_CALLBACK_URL=https://127.0.0.1:8000/api/schwab/callback
```

- [ ] **Step 4.2: Write failing OAuth tests**

Write `backend/apps/secrets/tests/test_schwab_oauth.py`:

```python
from unittest.mock import MagicMock, patch

import pytest
from django.test import override_settings

from apps.secrets.schwab_oauth import (
    build_authorize_url,
    exchange_code_for_token,
    refresh_token,
    persist_token,
)
from apps.secrets.models import ApiCredential


@override_settings(
    SCHWAB_CLIENT_ID="cid",
    SCHWAB_CALLBACK_URL="https://127.0.0.1:8000/api/schwab/callback",
    SCHWAB_AUTHORIZE_URL="https://api.schwabapi.com/v1/oauth/authorize",
)
def test_build_authorize_url_includes_required_params():
    url = build_authorize_url()
    assert url.startswith("https://api.schwabapi.com/v1/oauth/authorize?")
    assert "client_id=cid" in url
    assert "response_type=code" in url
    assert "redirect_uri=https%3A%2F%2F127.0.0.1%3A8000%2Fapi%2Fschwab%2Fcallback" in url


@override_settings(
    SCHWAB_CLIENT_ID="cid",
    SCHWAB_CLIENT_SECRET="csec",
    SCHWAB_CALLBACK_URL="https://127.0.0.1:8000/api/schwab/callback",
    SCHWAB_TOKEN_URL="https://api.schwabapi.com/v1/oauth/token",
)
def test_exchange_code_for_token_posts_correct_body():
    mock_resp = MagicMock()
    mock_resp.status_code = 200
    mock_resp.json.return_value = {
        "access_token": "AT",
        "refresh_token": "RT",
        "expires_in": 1800,
        "token_type": "Bearer",
    }
    with patch("apps.secrets.schwab_oauth.httpx.post", return_value=mock_resp) as post:
        tok = exchange_code_for_token("the-code")
        post.assert_called_once()
        _, kwargs = post.call_args
        assert kwargs["data"]["grant_type"] == "authorization_code"
        assert kwargs["data"]["code"] == "the-code"
        assert kwargs["data"]["redirect_uri"] == "https://127.0.0.1:8000/api/schwab/callback"
        assert kwargs["auth"] == ("cid", "csec")
    assert tok["access_token"] == "AT"
    assert tok["refresh_token"] == "RT"
    assert "expires_at" in tok  # our code adds this


@override_settings(SCHWAB_CLIENT_ID="cid", SCHWAB_CLIENT_SECRET="csec", SCHWAB_TOKEN_URL="u")
def test_refresh_token_uses_refresh_grant():
    mock_resp = MagicMock()
    mock_resp.status_code = 200
    mock_resp.json.return_value = {
        "access_token": "AT2",
        "refresh_token": "RT2",
        "expires_in": 1800,
    }
    with patch("apps.secrets.schwab_oauth.httpx.post", return_value=mock_resp) as post:
        tok = refresh_token("old-refresh")
        _, kwargs = post.call_args
        assert kwargs["data"]["grant_type"] == "refresh_token"
        assert kwargs["data"]["refresh_token"] == "old-refresh"
    assert tok["access_token"] == "AT2"


@pytest.mark.django_db
def test_persist_token_creates_or_updates_credential():
    tok = {"access_token": "A", "refresh_token": "R", "expires_at": 1700000000}
    persist_token(tok)
    cred = ApiCredential.objects.get(provider="schwab")
    assert cred.token["access_token"] == "A"
    # Upsert
    tok2 = {"access_token": "A2", "refresh_token": "R2", "expires_at": 1800000000}
    persist_token(tok2)
    cred.refresh_from_db()
    assert cred.token["access_token"] == "A2"
```

- [ ] **Step 4.3: Write `backend/apps/secrets/schwab_oauth.py`**

```python
"""Schwab OAuth2 helpers: build authorize URL, exchange code, refresh token, persist.

schwab-py handles refresh automatically for runtime clients via
`client_from_access_functions`, but we still need these for:
- Building the authorize URL shown in the frontend.
- Handling our web callback (schwab-py's built-in flows are CLI-oriented).
- Scheduled proactive refresh via Celery.
"""
from __future__ import annotations

import time
from urllib.parse import urlencode

import httpx
from django.conf import settings
from django.utils import timezone


def build_authorize_url(*, state: str = "") -> str:
    params = {
        "client_id": settings.SCHWAB_CLIENT_ID,
        "redirect_uri": settings.SCHWAB_CALLBACK_URL,
        "response_type": "code",
    }
    if state:
        params["state"] = state
    return f"{settings.SCHWAB_AUTHORIZE_URL}?{urlencode(params)}"


def exchange_code_for_token(code: str) -> dict:
    """Exchange an authorization code for an access/refresh token."""
    resp = httpx.post(
        settings.SCHWAB_TOKEN_URL,
        data={
            "grant_type": "authorization_code",
            "code": code,
            "redirect_uri": settings.SCHWAB_CALLBACK_URL,
        },
        auth=(settings.SCHWAB_CLIENT_ID, settings.SCHWAB_CLIENT_SECRET),
        timeout=15.0,
    )
    resp.raise_for_status()
    body = resp.json()
    body["expires_at"] = int(time.time()) + int(body.get("expires_in", 1800))
    return body


def refresh_token(refresh_token_value: str) -> dict:
    """Use a refresh token to obtain a new access token."""
    resp = httpx.post(
        settings.SCHWAB_TOKEN_URL,
        data={"grant_type": "refresh_token", "refresh_token": refresh_token_value},
        auth=(settings.SCHWAB_CLIENT_ID, settings.SCHWAB_CLIENT_SECRET),
        timeout=15.0,
    )
    resp.raise_for_status()
    body = resp.json()
    body["expires_at"] = int(time.time()) + int(body.get("expires_in", 1800))
    return body


def persist_token(token: dict) -> None:
    """Upsert the schwab token into ApiCredential."""
    from apps.secrets.models import ApiCredential
    from datetime import datetime

    expires_at = datetime.fromtimestamp(token["expires_at"], tz=timezone.get_current_timezone())
    ApiCredential.objects.update_or_create(
        provider="schwab",
        defaults={"token": token, "expires_at": expires_at},
    )


def load_token() -> dict | None:
    """Return the current token dict, or None if not connected."""
    from apps.secrets.models import ApiCredential

    try:
        return ApiCredential.objects.get(provider="schwab").token
    except ApiCredential.DoesNotExist:
        return None
```

- [ ] **Step 4.4: Run tests**

```bash
docker compose exec web pytest backend/apps/secrets/tests/test_schwab_oauth.py -v
```

Expected: 4 passed.

- [ ] **Step 4.5: Commit**

```bash
git add backend/apps/secrets/schwab_oauth.py \
        backend/apps/secrets/tests/test_schwab_oauth.py \
        backend/config/settings/base.py .env.example
git commit -m "feat(secrets): Schwab OAuth2 token exchange + refresh helpers"
```

---

## Task 5: Schwab OAuth views + URLs (TDD)

**Files:**
- Create: `backend/apps/secrets/urls.py`, `views.py`
- Create: `backend/apps/secrets/tests/test_views.py`
- Modify: `backend/config/urls.py` (include `apps.secrets.urls`)

- [ ] **Step 5.1: Write failing view tests**

Write `backend/apps/secrets/tests/test_views.py`:

```python
from unittest.mock import patch

import pytest
from django.test import Client, override_settings
from django.utils import timezone
from datetime import timedelta

from apps.secrets.models import ApiCredential


@pytest.mark.django_db
@override_settings(
    SCHWAB_CLIENT_ID="cid",
    SCHWAB_CALLBACK_URL="https://127.0.0.1:8000/api/schwab/callback",
    SCHWAB_AUTHORIZE_URL="https://api.schwabapi.com/v1/oauth/authorize",
)
def test_authorize_endpoint_returns_schwab_url():
    client = Client()
    response = client.get("/api/schwab/authorize/")
    assert response.status_code == 200
    body = response.json()
    assert body["url"].startswith("https://api.schwabapi.com/v1/oauth/authorize?")
    assert "client_id=cid" in body["url"]


@pytest.mark.django_db
def test_callback_without_code_returns_400():
    client = Client()
    response = client.get("/api/schwab/callback/")
    assert response.status_code == 400
    assert response.json()["code"] == "missing_code"


@pytest.mark.django_db
@override_settings(SCHWAB_CLIENT_ID="cid", SCHWAB_CLIENT_SECRET="csec")
def test_callback_exchanges_code_and_redirects_to_settings():
    with patch("apps.secrets.views.exchange_code_for_token") as ex, \
         patch("apps.secrets.views.persist_token") as ps:
        ex.return_value = {"access_token": "A", "refresh_token": "R", "expires_at": 9999999999}
        client = Client()
        response = client.get("/api/schwab/callback/", {"code": "abc"})
        assert response.status_code == 302
        assert response["Location"] == "/settings?schwab=connected"
        ex.assert_called_once_with("abc")
        ps.assert_called_once()


@pytest.mark.django_db
def test_status_not_connected():
    client = Client()
    response = client.get("/api/schwab/status/")
    assert response.status_code == 200
    assert response.json() == {"connected": False, "expires_at": None}


@pytest.mark.django_db
def test_status_connected():
    future = timezone.now() + timedelta(days=5)
    ApiCredential.objects.create(provider="schwab", token={"access_token": "A"}, expires_at=future)
    client = Client()
    response = client.get("/api/schwab/status/")
    body = response.json()
    assert body["connected"] is True
    assert body["expires_at"] is not None
```

- [ ] **Step 5.2: Write `backend/apps/secrets/views.py`**

```python
"""Schwab OAuth endpoints."""
from __future__ import annotations

from django.http import HttpRequest, HttpResponseRedirect, JsonResponse
from django.views.decorators.http import require_GET

from apps.secrets.models import ApiCredential
from apps.secrets.schwab_oauth import (
    build_authorize_url,
    exchange_code_for_token,
    persist_token,
)


@require_GET
def schwab_authorize(_request: HttpRequest) -> JsonResponse:
    """Returns the URL the frontend should open to begin Schwab OAuth."""
    return JsonResponse({"url": build_authorize_url()})


@require_GET
def schwab_callback(request: HttpRequest) -> JsonResponse | HttpResponseRedirect:
    """Schwab redirects here with ?code=... after user consent."""
    code = request.GET.get("code")
    if not code:
        return JsonResponse(
            {"code": "missing_code", "message": "Schwab callback did not include a code parameter."},
            status=400,
        )
    try:
        token = exchange_code_for_token(code)
    except Exception as exc:  # noqa: BLE001 — surface any provider error
        return JsonResponse(
            {"code": "oauth_exchange_failed", "message": str(exc)},
            status=502,
        )
    persist_token(token)
    return HttpResponseRedirect("/settings?schwab=connected")


@require_GET
def schwab_status(_request: HttpRequest) -> JsonResponse:
    try:
        cred = ApiCredential.objects.get(provider="schwab")
    except ApiCredential.DoesNotExist:
        return JsonResponse({"connected": False, "expires_at": None})
    return JsonResponse(
        {
            "connected": True,
            "expires_at": cred.expires_at.isoformat() if cred.expires_at else None,
        }
    )
```

- [ ] **Step 5.3: Write `backend/apps/secrets/urls.py`**

```python
from django.urls import path

from . import views

app_name = "secrets_app"

urlpatterns = [
    path("authorize/", views.schwab_authorize, name="authorize"),
    path("callback/", views.schwab_callback, name="callback"),
    path("status/", views.schwab_status, name="status"),
]
```

- [ ] **Step 5.4: Mount URLs**

Edit `backend/config/urls.py`:

```python
from django.contrib import admin
from django.urls import include, path

urlpatterns = [
    path("admin/", admin.site.urls),
    path("api/", include("apps.core.urls")),
    path("api/schwab/", include("apps.secrets.urls")),
]
```

- [ ] **Step 5.5: Run tests**

```bash
docker compose exec web pytest backend/apps/secrets/tests/test_views.py -v
```

Expected: 5 passed.

- [ ] **Step 5.6: Commit**

```bash
git add backend/apps/secrets/views.py backend/apps/secrets/urls.py \
        backend/apps/secrets/tests/test_views.py backend/config/urls.py
git commit -m "feat(secrets): Schwab OAuth authorize/callback/status endpoints"
```

---

## Task 6: Schwab client factory (TDD)

**Files:**
- Create: `backend/apps/market/__init__.py`, `apps.py`, `schwab_client.py`
- Create: `backend/apps/market/tests/__init__.py`, `test_schwab_client.py`
- Modify: `backend/config/settings/base.py` (add `"apps.market"` to INSTALLED_APPS)

- [ ] **Step 6.1: Scaffold `market` app**

```bash
mkdir -p /home/dan/ai-dashboard/backend/apps/market/tests
touch /home/dan/ai-dashboard/backend/apps/market/__init__.py
touch /home/dan/ai-dashboard/backend/apps/market/tests/__init__.py
```

Write `backend/apps/market/apps.py`:

```python
from django.apps import AppConfig


class MarketConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "apps.market"
    label = "market"
```

Register in `INSTALLED_APPS` after `"apps.secrets"`.

- [ ] **Step 6.2: Write failing schwab-client test**

Write `backend/apps/market/tests/test_schwab_client.py`:

```python
from unittest.mock import patch

import pytest
from django.test import override_settings
from django.utils import timezone
from datetime import timedelta

from apps.market.schwab_client import get_schwab_client, SchwabNotConnectedError
from apps.secrets.models import ApiCredential


@pytest.mark.django_db
def test_raises_when_not_connected():
    with pytest.raises(SchwabNotConnectedError):
        get_schwab_client()


@pytest.mark.django_db
@override_settings(SCHWAB_CLIENT_ID="cid", SCHWAB_CLIENT_SECRET="csec")
def test_returns_client_when_connected():
    ApiCredential.objects.create(
        provider="schwab",
        token={"access_token": "AT", "refresh_token": "RT", "expires_at": 9999999999, "token_type": "Bearer"},
        expires_at=timezone.now() + timedelta(hours=1),
    )
    # Mock the schwab-py factory so we don't need real credentials
    with patch("apps.market.schwab_client.client_from_access_functions") as factory:
        factory.return_value = object()
        client = get_schwab_client()
        assert client is factory.return_value
        # Verify factory called with client id + secret + read/write funcs
        args, kwargs = factory.call_args
        assert kwargs.get("api_key") == "cid" or (args and args[0] == "cid")


@pytest.mark.django_db
@override_settings(SCHWAB_CLIENT_ID="cid", SCHWAB_CLIENT_SECRET="csec")
def test_write_func_persists_refreshed_token():
    ApiCredential.objects.create(
        provider="schwab",
        token={"access_token": "OLD", "refresh_token": "RT"},
    )
    from apps.market.schwab_client import _make_write_func

    write = _make_write_func()
    write({"access_token": "NEW", "refresh_token": "RT2", "expires_at": 9999999999})
    cred = ApiCredential.objects.get(provider="schwab")
    assert cred.token["access_token"] == "NEW"
    assert cred.token["refresh_token"] == "RT2"
```

- [ ] **Step 6.3: Write `backend/apps/market/schwab_client.py`**

```python
"""Schwab client factory.

Uses schwab-py's `client_from_access_functions` so token storage is entirely
under our control (encrypted in Postgres via ApiCredential). Token refreshes
are written back through `_make_write_func`.
"""
from __future__ import annotations

from typing import Any

from django.conf import settings

from apps.secrets.schwab_oauth import load_token, persist_token


class SchwabNotConnectedError(RuntimeError):
    """Raised when no Schwab credential exists. Callers should surface this to the UI."""


def _make_read_func():
    def read() -> dict | None:
        return load_token()
    return read


def _make_write_func():
    def write(token: Any) -> None:
        # schwab-py calls this with the raw token dict after refresh.
        # Our persist_token expects an 'expires_at' field (unix seconds).
        if "expires_at" not in token and "expires_in" in token:
            import time
            token["expires_at"] = int(time.time()) + int(token["expires_in"])
        persist_token(token)
    return write


def get_schwab_client(*, asyncio: bool = False):
    """Return a live schwab.client.Client (or AsyncClient if asyncio=True).

    Raises SchwabNotConnectedError if no credential row exists.
    """
    from schwab.auth import client_from_access_functions

    if load_token() is None:
        raise SchwabNotConnectedError("No Schwab credential; connect at /settings first.")

    return client_from_access_functions(
        api_key=settings.SCHWAB_CLIENT_ID,
        app_secret=settings.SCHWAB_CLIENT_SECRET,
        token_read_func=_make_read_func(),
        token_write_func=_make_write_func(),
        asyncio=asyncio,
    )
```

- [ ] **Step 6.4: Run tests**

```bash
docker compose exec web pytest backend/apps/market/tests/test_schwab_client.py -v
```

Expected: 3 passed.

- [ ] **Step 6.5: Commit**

```bash
git add backend/apps/market/__init__.py backend/apps/market/apps.py \
        backend/apps/market/schwab_client.py backend/apps/market/tests/ \
        backend/config/settings/base.py
git commit -m "feat(market): schwab client factory using encrypted DB-backed tokens"
```

---

## Task 7: Market data models (TDD)

**Files:**
- Create: `backend/apps/market/models.py`
- Create: `backend/apps/market/tests/test_models.py`

- [ ] **Step 7.1: Write failing model tests**

Write `backend/apps/market/tests/test_models.py`:

```python
import pytest
from django.utils import timezone
from datetime import datetime, timedelta, timezone as dt_timezone
from decimal import Decimal

from apps.market.models import Quote, OHLCBar, Position, MarketContext


@pytest.mark.django_db
def test_quote_create():
    q = Quote.objects.create(
        ticker="SPY",
        last=Decimal("550.12"),
        bid=Decimal("550.11"),
        ask=Decimal("550.13"),
        volume=123456,
        ts=timezone.now(),
    )
    assert q.ticker == "SPY"
    assert q.last == Decimal("550.12")


@pytest.mark.django_db
def test_ohlcbar_unique_per_ticker_timeframe_ts():
    ts = timezone.now().replace(second=0, microsecond=0)
    OHLCBar.objects.create(
        ticker="SPY", timeframe="1m",
        open=Decimal("1"), high=Decimal("2"), low=Decimal("1"), close=Decimal("2"), volume=100, ts=ts,
    )
    with pytest.raises(Exception):
        OHLCBar.objects.create(
            ticker="SPY", timeframe="1m",
            open=Decimal("1"), high=Decimal("2"), low=Decimal("1"), close=Decimal("2"), volume=100, ts=ts,
        )


@pytest.mark.django_db
def test_position_create():
    p = Position.objects.create(
        ticker="NVDA",
        qty=Decimal("100"),
        avg_cost=Decimal("800.50"),
        mkt_value=Decimal("85000"),
        unrealized_pl=Decimal("4950"),
        day_pl=Decimal("250"),
        as_of=timezone.now(),
    )
    assert p.qty == Decimal("100")


@pytest.mark.django_db
def test_market_context_create():
    mc = MarketContext.objects.create(
        spy_last=Decimal("550"), qqq_last=Decimal("480"), vix_last=Decimal("14"),
        sectors={"XLK": 215.4, "XLF": 45.2}, breadth={"advance_count": 1200, "decline_count": 900},
        as_of=timezone.now(),
    )
    assert mc.sectors["XLK"] == 215.4
```

- [ ] **Step 7.2: Write `backend/apps/market/models.py`**

```python
"""Market data tables — append-only caches of what we've fetched from Schwab."""
from __future__ import annotations

from django.db import models


class Quote(models.Model):
    ticker = models.CharField(max_length=16, db_index=True)
    last = models.DecimalField(max_digits=14, decimal_places=4, null=True)
    bid = models.DecimalField(max_digits=14, decimal_places=4, null=True)
    ask = models.DecimalField(max_digits=14, decimal_places=4, null=True)
    volume = models.BigIntegerField(null=True)
    high = models.DecimalField(max_digits=14, decimal_places=4, null=True)
    low = models.DecimalField(max_digits=14, decimal_places=4, null=True)
    pct_change = models.DecimalField(max_digits=8, decimal_places=4, null=True)
    ts = models.DateTimeField(db_index=True)

    class Meta:
        indexes = [models.Index(fields=["ticker", "-ts"])]


class OHLCBar(models.Model):
    TIMEFRAMES = [("1m", "1m"), ("5m", "5m"), ("15m", "15m"), ("1h", "1h"), ("1d", "1d")]

    ticker = models.CharField(max_length=16)
    timeframe = models.CharField(max_length=4, choices=TIMEFRAMES)
    open = models.DecimalField(max_digits=14, decimal_places=4)
    high = models.DecimalField(max_digits=14, decimal_places=4)
    low = models.DecimalField(max_digits=14, decimal_places=4)
    close = models.DecimalField(max_digits=14, decimal_places=4)
    volume = models.BigIntegerField()
    ts = models.DateTimeField()

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=["ticker", "timeframe", "ts"], name="uniq_bar"),
        ]
        indexes = [models.Index(fields=["ticker", "timeframe", "-ts"])]


class Position(models.Model):
    ticker = models.CharField(max_length=16, db_index=True)
    qty = models.DecimalField(max_digits=16, decimal_places=6)
    avg_cost = models.DecimalField(max_digits=14, decimal_places=4, null=True)
    mkt_value = models.DecimalField(max_digits=16, decimal_places=4, null=True)
    unrealized_pl = models.DecimalField(max_digits=14, decimal_places=4, null=True)
    day_pl = models.DecimalField(max_digits=14, decimal_places=4, null=True)
    as_of = models.DateTimeField()

    class Meta:
        indexes = [models.Index(fields=["ticker", "-as_of"])]


class MarketContext(models.Model):
    spy_last = models.DecimalField(max_digits=14, decimal_places=4, null=True)
    qqq_last = models.DecimalField(max_digits=14, decimal_places=4, null=True)
    vix_last = models.DecimalField(max_digits=14, decimal_places=4, null=True)
    sectors = models.JSONField(default=dict)   # {"XLK": 215.4, ...}
    breadth = models.JSONField(default=dict)   # {"advance_count": N, "decline_count": M, ...}
    as_of = models.DateTimeField(db_index=True)
```

- [ ] **Step 7.3: Migrate + test**

```bash
docker compose exec web python manage.py makemigrations market
docker compose exec web python manage.py migrate
docker compose exec web pytest backend/apps/market/tests/test_models.py -v
```

Expected: 4 passed.

- [ ] **Step 7.4: Commit**

```bash
git add backend/apps/market/models.py backend/apps/market/tests/test_models.py backend/apps/market/migrations/
git commit -m "feat(market): Quote/OHLCBar/Position/MarketContext models"
```

---

## Task 8: Redis cache helpers (TDD)

**Files:**
- Create: `backend/apps/market/cache.py`
- Create: `backend/apps/market/tests/test_cache.py`

- [ ] **Step 8.1: Write failing cache test**

Write `backend/apps/market/tests/test_cache.py`:

```python
from unittest.mock import MagicMock

import fakeredis
import pytest

from apps.market import cache as cache_module


@pytest.fixture
def redis_fake(monkeypatch):
    r = fakeredis.FakeRedis()
    monkeypatch.setattr(cache_module, "_redis", lambda: r)
    return r


def test_get_or_fetch_hits_when_fresh(redis_fake):
    fetcher = MagicMock(return_value={"hello": "world"})
    v1 = cache_module.get_or_fetch("k1", ttl_seconds=10, fetcher=fetcher)
    v2 = cache_module.get_or_fetch("k1", ttl_seconds=10, fetcher=fetcher)
    assert v1 == {"hello": "world"}
    assert v2 == {"hello": "world"}
    fetcher.assert_called_once()


def test_get_or_fetch_refetches_after_expiry(redis_fake):
    fetcher = MagicMock(side_effect=[{"v": 1}, {"v": 2}])
    cache_module.get_or_fetch("k2", ttl_seconds=1, fetcher=fetcher)
    redis_fake.delete("k2")  # simulate expiry
    result = cache_module.get_or_fetch("k2", ttl_seconds=1, fetcher=fetcher)
    assert result == {"v": 2}
    assert fetcher.call_count == 2


def test_ttl_for_kind_returns_configured_values():
    assert cache_module.ttl_for_kind("quotes") == 5
    assert cache_module.ttl_for_kind("positions") == 10
    assert cache_module.ttl_for_kind("ohlc_1m") == 30
    assert cache_module.ttl_for_kind("ohlc_1d") == 3600
    assert cache_module.ttl_for_kind("news") == 300
    assert cache_module.ttl_for_kind("unknown-kind") == 30  # default
```

- [ ] **Step 8.2: Write `backend/apps/market/cache.py`**

```python
"""Redis cache helpers for market data.

TTLs come from the design spec §5.2. Values are JSON-serialized.
"""
from __future__ import annotations

import json
from typing import Any, Callable

import redis
from django.conf import settings

_TTL: dict[str, int] = {
    "quotes": 5,
    "ohlc_1m": 30,
    "ohlc_5m": 120,
    "ohlc_15m": 300,
    "ohlc_1h": 900,
    "ohlc_1d": 3600,
    "chain": 15,
    "breadth": 30,
    "news": 300,
    "positions": 10,
    "context": 30,
}


def _redis() -> redis.Redis:
    return redis.Redis.from_url(settings.REDIS_URL)


def ttl_for_kind(kind: str) -> int:
    return _TTL.get(kind, 30)


def get_or_fetch(key: str, *, ttl_seconds: int, fetcher: Callable[[], Any]) -> Any:
    """Read JSON from Redis at key; if missing, call fetcher, store, return."""
    r = _redis()
    cached = r.get(key)
    if cached is not None:
        return json.loads(cached)
    value = fetcher()
    r.set(key, json.dumps(value, default=str), ex=ttl_seconds)
    return value
```

- [ ] **Step 8.3: Run tests**

```bash
docker compose exec web pytest backend/apps/market/tests/test_cache.py -v
```

Expected: 3 passed.

- [ ] **Step 8.4: Commit**

```bash
git add backend/apps/market/cache.py backend/apps/market/tests/test_cache.py
git commit -m "feat(market): redis cache helpers with per-kind TTLs"
```

---

## Task 9: Quote fetch service (TDD)

**Files:**
- Create: `backend/apps/market/services/__init__.py`, `quotes.py`
- Create: `backend/apps/market/tests/test_services_quotes.py`

- [ ] **Step 9.1: Write failing test**

Write `backend/apps/market/tests/test_services_quotes.py`:

```python
from unittest.mock import MagicMock, patch

import pytest
from django.utils import timezone

from apps.market.services.quotes import fetch_quotes
from apps.market import cache as cache_module


@pytest.fixture(autouse=True)
def fake_redis(monkeypatch):
    import fakeredis
    r = fakeredis.FakeRedis()
    monkeypatch.setattr(cache_module, "_redis", lambda: r)
    return r


@pytest.mark.django_db
def test_fetch_quotes_uses_schwab_and_caches():
    # Schwab get_quotes returns a mapping: {"SPY": {...}, "QQQ": {...}}
    schwab_resp = MagicMock()
    schwab_resp.json.return_value = {
        "SPY": {"quote": {"lastPrice": 550.0, "bidPrice": 549.9, "askPrice": 550.1,
                          "totalVolume": 1000, "highPrice": 552, "lowPrice": 548, "netPercentChange": 0.5}},
        "QQQ": {"quote": {"lastPrice": 480.0, "bidPrice": 479.9, "askPrice": 480.1,
                          "totalVolume": 900, "highPrice": 482, "lowPrice": 478, "netPercentChange": 0.2}},
    }
    client = MagicMock()
    client.get_quotes.return_value = schwab_resp

    with patch("apps.market.services.quotes.get_schwab_client", return_value=client):
        result = fetch_quotes(["SPY", "QQQ"])

    assert result["SPY"]["last"] == 550.0
    assert result["QQQ"]["last"] == 480.0
    client.get_quotes.assert_called_once_with(["SPY", "QQQ"])

    # Second call within TTL should NOT hit Schwab again
    with patch("apps.market.services.quotes.get_schwab_client", return_value=client):
        result2 = fetch_quotes(["SPY", "QQQ"])
    assert result2 == result
    assert client.get_quotes.call_count == 1  # still 1 from before


@pytest.mark.django_db
def test_fetch_quotes_empty_list():
    result = fetch_quotes([])
    assert result == {}
```

- [ ] **Step 9.2: Write `backend/apps/market/services/__init__.py`**

```python
"""Service layer — thin functions that orchestrate Schwab + cache + DB writes."""
```

- [ ] **Step 9.3: Write `backend/apps/market/services/quotes.py`**

```python
"""Quote fetching service."""
from __future__ import annotations

from typing import Iterable

from apps.market import cache
from apps.market.schwab_client import get_schwab_client


def fetch_quotes(tickers: Iterable[str]) -> dict[str, dict]:
    """Return {ticker: {last, bid, ask, volume, high, low, pct_change}} keyed by ticker.

    Cached in Redis for 5s. One Schwab call per cache miss; batched.
    """
    ticker_list = sorted(set(t.upper() for t in tickers if t))
    if not ticker_list:
        return {}
    cache_key = f"market:quotes:{','.join(ticker_list)}"
    return cache.get_or_fetch(
        cache_key,
        ttl_seconds=cache.ttl_for_kind("quotes"),
        fetcher=lambda: _fetch_from_schwab(ticker_list),
    )


def _fetch_from_schwab(tickers: list[str]) -> dict[str, dict]:
    client = get_schwab_client()
    resp = client.get_quotes(tickers)
    raw = resp.json()
    out: dict[str, dict] = {}
    for t, blob in raw.items():
        q = blob.get("quote", {}) if isinstance(blob, dict) else {}
        out[t] = {
            "last": q.get("lastPrice"),
            "bid": q.get("bidPrice"),
            "ask": q.get("askPrice"),
            "volume": q.get("totalVolume"),
            "high": q.get("highPrice"),
            "low": q.get("lowPrice"),
            "pct_change": q.get("netPercentChange"),
        }
    return out
```

- [ ] **Step 9.4: Add `fakeredis` to test deps**

Edit `pyproject.toml` → `[dependency-groups].dev` — confirm `fakeredis>=2.24,<3.0` is present (it should be from M1). If not, add it, rebuild.

- [ ] **Step 9.5: Run tests**

```bash
docker compose exec web pytest backend/apps/market/tests/test_services_quotes.py -v
```

Expected: 2 passed.

- [ ] **Step 9.6: Commit**

```bash
git add backend/apps/market/services backend/apps/market/tests/test_services_quotes.py
git commit -m "feat(market): fetch_quotes service with Redis cache"
```

---

## Task 10: OHLC fetch service (TDD)

**Files:**
- Create: `backend/apps/market/services/ohlc.py`
- Create: `backend/apps/market/tests/test_services_ohlc.py`

- [ ] **Step 10.1: Write failing test**

Write `backend/apps/market/tests/test_services_ohlc.py`:

```python
from unittest.mock import MagicMock, patch

import pytest

from apps.market.services.ohlc import fetch_ohlc
from apps.market import cache as cache_module


@pytest.fixture(autouse=True)
def fake_redis(monkeypatch):
    import fakeredis
    r = fakeredis.FakeRedis()
    monkeypatch.setattr(cache_module, "_redis", lambda: r)
    return r


@pytest.mark.django_db
def test_fetch_ohlc_1m_calls_schwab_price_history():
    # Schwab's price-history endpoint returns {"candles": [{open, high, low, close, volume, datetime}, ...]}
    resp = MagicMock()
    resp.json.return_value = {
        "candles": [
            {"open": 100, "high": 101, "low": 99, "close": 100.5, "volume": 1000, "datetime": 1700000000000},
            {"open": 100.5, "high": 101.5, "low": 100, "close": 101, "volume": 1200, "datetime": 1700000060000},
        ]
    }
    client = MagicMock()
    client.get_price_history_every_minute.return_value = resp

    with patch("apps.market.services.ohlc.get_schwab_client", return_value=client):
        bars = fetch_ohlc("SPY", timeframe="1m", bars=60)

    assert len(bars) == 2
    assert bars[0]["open"] == 100
    assert bars[0]["ts"]  # ISO timestamp
    client.get_price_history_every_minute.assert_called_once()


@pytest.mark.django_db
def test_fetch_ohlc_invalid_timeframe_raises():
    with pytest.raises(ValueError):
        fetch_ohlc("SPY", timeframe="3m", bars=60)
```

- [ ] **Step 10.2: Write `backend/apps/market/services/ohlc.py`**

```python
"""OHLC price history service."""
from __future__ import annotations

from datetime import datetime, timezone as dt_tz

from apps.market import cache
from apps.market.schwab_client import get_schwab_client

_METHOD_BY_TIMEFRAME = {
    "1m": "get_price_history_every_minute",
    "5m": "get_price_history_every_five_minutes",
    "15m": "get_price_history_every_fifteen_minutes",
    "1h": "get_price_history_every_thirty_minutes",  # Schwab exposes 30m; we map 1h to 30m here (caller bucketed if needed)
    "1d": "get_price_history_every_day",
}


def fetch_ohlc(ticker: str, *, timeframe: str, bars: int = 60) -> list[dict]:
    if timeframe not in _METHOD_BY_TIMEFRAME:
        raise ValueError(f"Unsupported timeframe: {timeframe}")
    ticker = ticker.upper()
    cache_key = f"market:ohlc:{ticker}:{timeframe}:{bars}"
    return cache.get_or_fetch(
        cache_key,
        ttl_seconds=cache.ttl_for_kind(f"ohlc_{timeframe}"),
        fetcher=lambda: _fetch_from_schwab(ticker, timeframe, bars),
    )


def _fetch_from_schwab(ticker: str, timeframe: str, bars: int) -> list[dict]:
    client = get_schwab_client()
    method = getattr(client, _METHOD_BY_TIMEFRAME[timeframe])
    resp = method(ticker)
    raw = resp.json()
    candles = raw.get("candles", [])[-bars:]
    out = []
    for c in candles:
        ts_ms = c.get("datetime", 0)
        out.append({
            "open": c.get("open"),
            "high": c.get("high"),
            "low": c.get("low"),
            "close": c.get("close"),
            "volume": c.get("volume"),
            "ts": datetime.fromtimestamp(ts_ms / 1000, tz=dt_tz.utc).isoformat(),
        })
    return out
```

- [ ] **Step 10.3: Run tests**

```bash
docker compose exec web pytest backend/apps/market/tests/test_services_ohlc.py -v
```

Expected: 2 passed.

- [ ] **Step 10.4: Commit**

```bash
git add backend/apps/market/services/ohlc.py backend/apps/market/tests/test_services_ohlc.py
git commit -m "feat(market): fetch_ohlc service"
```

---

## Task 11: Positions fetch service (TDD)

**Files:**
- Create: `backend/apps/market/services/positions.py`
- Create: `backend/apps/market/tests/test_services_positions.py`

- [ ] **Step 11.1: Write failing test**

Write `backend/apps/market/tests/test_services_positions.py`:

```python
from unittest.mock import MagicMock, patch

import pytest

from apps.market.services.positions import fetch_positions
from apps.market import cache as cache_module


@pytest.fixture(autouse=True)
def fake_redis(monkeypatch):
    import fakeredis
    r = fakeredis.FakeRedis()
    monkeypatch.setattr(cache_module, "_redis", lambda: r)
    return r


@pytest.mark.django_db
def test_fetch_positions_extracts_from_account():
    # schwab-py returns a list from get_accounts with fields=positions
    hash_resp = MagicMock()
    hash_resp.json.return_value = [{"accountNumber": "111", "hashValue": "HASH1"}]

    accounts_resp = MagicMock()
    accounts_resp.json.return_value = [{
        "securitiesAccount": {
            "positions": [
                {
                    "instrument": {"symbol": "NVDA"},
                    "longQuantity": 100, "shortQuantity": 0,
                    "averagePrice": 800.0,
                    "marketValue": 85000.0,
                    "currentDayProfitLoss": 250.0,
                    "longOpenProfitLoss": 4950.0,
                },
                {
                    "instrument": {"symbol": "SPY"},
                    "longQuantity": 50, "shortQuantity": 0,
                    "averagePrice": 540.0,
                    "marketValue": 27500.0,
                    "currentDayProfitLoss": 100.0,
                    "longOpenProfitLoss": 500.0,
                },
            ]
        }
    }]

    client = MagicMock()
    client.get_account_numbers.return_value = hash_resp
    client.get_accounts.return_value = accounts_resp

    with patch("apps.market.services.positions.get_schwab_client", return_value=client):
        positions = fetch_positions()

    assert len(positions) == 2
    nvda = next(p for p in positions if p["ticker"] == "NVDA")
    assert nvda["qty"] == 100
    assert nvda["avg_cost"] == 800.0
    assert nvda["unrealized_pl"] == 4950.0
    assert nvda["day_pl"] == 250.0
```

- [ ] **Step 11.2: Write `backend/apps/market/services/positions.py`**

```python
"""Account positions service."""
from __future__ import annotations

from apps.market import cache
from apps.market.schwab_client import get_schwab_client


def fetch_positions() -> list[dict]:
    return cache.get_or_fetch(
        "market:positions",
        ttl_seconds=cache.ttl_for_kind("positions"),
        fetcher=_fetch_from_schwab,
    )


def _fetch_from_schwab() -> list[dict]:
    client = get_schwab_client()
    # Get account hashes then fetch positions via fields=positions
    hash_resp = client.get_account_numbers()
    hashes = [a["hashValue"] for a in hash_resp.json()]

    out: list[dict] = []
    accounts_resp = client.get_accounts(fields=client.Account.Fields.POSITIONS)
    for acct_blob in accounts_resp.json():
        sec_acct = acct_blob.get("securitiesAccount", {})
        for p in sec_acct.get("positions", []):
            symbol = p.get("instrument", {}).get("symbol", "")
            qty = p.get("longQuantity", 0) - p.get("shortQuantity", 0)
            out.append({
                "ticker": symbol,
                "qty": qty,
                "avg_cost": p.get("averagePrice"),
                "mkt_value": p.get("marketValue"),
                "unrealized_pl": p.get("longOpenProfitLoss") or p.get("shortOpenProfitLoss"),
                "day_pl": p.get("currentDayProfitLoss"),
            })
    return out
```

- [ ] **Step 11.3: Test + commit**

```bash
docker compose exec web pytest backend/apps/market/tests/test_services_positions.py -v
git add backend/apps/market/services/positions.py backend/apps/market/tests/test_services_positions.py
git commit -m "feat(market): fetch_positions service"
```

Expected: 1 passed.

---

## Task 12: Market context service (TDD)

**Files:**
- Create: `backend/apps/market/services/context.py`
- Create: `backend/apps/market/tests/test_services_context.py`

Sector ETFs: XLK (tech), XLF (fin), XLE (energy), XLV (health), XLY (disc), XLP (staples), XLI (industrials), XLU (utilities), XLB (materials), XLRE (real estate), XLC (comms).

- [ ] **Step 12.1: Write failing test**

Write `backend/apps/market/tests/test_services_context.py`:

```python
from unittest.mock import patch

import pytest

from apps.market.services.context import fetch_market_context, SECTOR_ETFS, CONTEXT_SYMBOLS
from apps.market import cache as cache_module


@pytest.fixture(autouse=True)
def fake_redis(monkeypatch):
    import fakeredis
    r = fakeredis.FakeRedis()
    monkeypatch.setattr(cache_module, "_redis", lambda: r)


def test_context_symbols_includes_core_and_sectors():
    assert "SPY" in CONTEXT_SYMBOLS
    assert "QQQ" in CONTEXT_SYMBOLS
    assert "$VIX" in CONTEXT_SYMBOLS
    for etf in SECTOR_ETFS:
        assert etf in CONTEXT_SYMBOLS


@pytest.mark.django_db
def test_fetch_market_context_shape():
    quotes = {s: {"last": 100.0 + i} for i, s in enumerate(CONTEXT_SYMBOLS)}
    with patch("apps.market.services.context.fetch_quotes", return_value=quotes):
        ctx = fetch_market_context()
    assert ctx["spy_last"] == quotes["SPY"]["last"]
    assert ctx["qqq_last"] == quotes["QQQ"]["last"]
    assert ctx["vix_last"] == quotes["$VIX"]["last"]
    for etf in SECTOR_ETFS:
        assert etf in ctx["sectors"]
    assert "breadth" in ctx  # may be empty dict, that's fine
```

- [ ] **Step 12.2: Write `backend/apps/market/services/context.py`**

```python
"""Market context: SPY/QQQ/VIX + sector ETFs + breadth (best-effort)."""
from __future__ import annotations

from apps.market import cache
from apps.market.services.quotes import fetch_quotes

SECTOR_ETFS = ["XLK", "XLF", "XLE", "XLV", "XLY", "XLP", "XLI", "XLU", "XLB", "XLRE", "XLC"]
CORE = ["SPY", "QQQ", "$VIX"]
# Advance/decline indices — Schwab may or may not return these; we try and fall back silently.
BREADTH = ["$ADVN", "$DECN", "$TICK", "$TRIN"]
CONTEXT_SYMBOLS = CORE + SECTOR_ETFS + BREADTH


def fetch_market_context() -> dict:
    return cache.get_or_fetch(
        "market:context",
        ttl_seconds=cache.ttl_for_kind("context"),
        fetcher=_fetch,
    )


def _fetch() -> dict:
    quotes = fetch_quotes(CONTEXT_SYMBOLS)
    sectors = {etf: quotes.get(etf, {}).get("last") for etf in SECTOR_ETFS}
    breadth = {}
    for sym in BREADTH:
        q = quotes.get(sym, {})
        if q.get("last") is not None:
            breadth[sym] = q["last"]
    return {
        "spy_last": quotes.get("SPY", {}).get("last"),
        "qqq_last": quotes.get("QQQ", {}).get("last"),
        "vix_last": quotes.get("$VIX", {}).get("last"),
        "sectors": sectors,
        "breadth": breadth,
    }
```

- [ ] **Step 12.3: Test + commit**

```bash
docker compose exec web pytest backend/apps/market/tests/test_services_context.py -v
git add backend/apps/market/services/context.py backend/apps/market/tests/test_services_context.py
git commit -m "feat(market): fetch_market_context (SPY/QQQ/VIX + sectors + breadth)"
```

Expected: 2 passed.

---

## Task 13: Watchlist models + admin (TDD)

**Files:**
- Create: `backend/apps/profiles/__init__.py`, `apps.py`, `admin.py`, `models.py`
- Create: `backend/apps/profiles/tests/__init__.py`, `test_models.py`
- Modify: `backend/config/settings/base.py` (register app)

- [ ] **Step 13.1: Scaffold**

```bash
mkdir -p /home/dan/ai-dashboard/backend/apps/profiles/tests
touch /home/dan/ai-dashboard/backend/apps/profiles/__init__.py
touch /home/dan/ai-dashboard/backend/apps/profiles/tests/__init__.py
```

Write `backend/apps/profiles/apps.py`:

```python
from django.apps import AppConfig


class ProfilesConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "apps.profiles"
    label = "profiles"
```

Register in `INSTALLED_APPS` after `"apps.market"`.

- [ ] **Step 13.2: Write failing model test**

Write `backend/apps/profiles/tests/test_models.py`:

```python
import pytest

from apps.profiles.models import Watchlist, WatchlistSymbol


@pytest.mark.django_db
def test_create_watchlist_with_symbols():
    w = Watchlist.objects.create(name="My Scalps")
    WatchlistSymbol.objects.create(watchlist=w, ticker="SPY", sort_order=0)
    WatchlistSymbol.objects.create(watchlist=w, ticker="QQQ", sort_order=1)
    assert list(w.symbols.order_by("sort_order").values_list("ticker", flat=True)) == ["SPY", "QQQ"]


@pytest.mark.django_db
def test_unique_symbol_per_watchlist():
    w = Watchlist.objects.create(name="A")
    WatchlistSymbol.objects.create(watchlist=w, ticker="SPY", sort_order=0)
    with pytest.raises(Exception):
        WatchlistSymbol.objects.create(watchlist=w, ticker="SPY", sort_order=1)


@pytest.mark.django_db
def test_ticker_is_uppercased():
    w = Watchlist.objects.create(name="A")
    s = WatchlistSymbol.objects.create(watchlist=w, ticker="nvda", sort_order=0)
    s.refresh_from_db()
    assert s.ticker == "NVDA"
```

- [ ] **Step 13.3: Write `backend/apps/profiles/models.py`**

```python
"""Watchlists. (TradingProfile comes in M3.)"""
from __future__ import annotations

from django.db import models


class Watchlist(models.Model):
    name = models.CharField(max_length=100)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["name"]

    def __str__(self) -> str:
        return self.name


class WatchlistSymbol(models.Model):
    watchlist = models.ForeignKey(Watchlist, related_name="symbols", on_delete=models.CASCADE)
    ticker = models.CharField(max_length=16)
    sort_order = models.PositiveIntegerField(default=0)

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=["watchlist", "ticker"], name="uniq_watchlist_ticker"),
        ]
        ordering = ["watchlist_id", "sort_order"]

    def save(self, *args, **kwargs) -> None:
        self.ticker = (self.ticker or "").upper()
        super().save(*args, **kwargs)
```

- [ ] **Step 13.4: Write `backend/apps/profiles/admin.py`**

```python
from django.contrib import admin

from .models import Watchlist, WatchlistSymbol


class WatchlistSymbolInline(admin.TabularInline):
    model = WatchlistSymbol
    extra = 1


@admin.register(Watchlist)
class WatchlistAdmin(admin.ModelAdmin):
    list_display = ("name", "created_at")
    inlines = [WatchlistSymbolInline]
```

- [ ] **Step 13.5: Migrate + test**

```bash
docker compose exec web python manage.py makemigrations profiles
docker compose exec web python manage.py migrate
docker compose exec web pytest backend/apps/profiles/tests/test_models.py -v
```

Expected: 3 passed.

- [ ] **Step 13.6: Commit**

```bash
git add backend/apps/profiles/ backend/config/settings/base.py
git commit -m "feat(profiles): Watchlist + WatchlistSymbol models + admin"
```

---

## Task 14: Watchlist DRF endpoints (TDD)

**Files:**
- Create: `backend/apps/profiles/serializers.py`, `urls.py`, `views.py`
- Create: `backend/apps/profiles/tests/test_endpoints.py`
- Modify: `backend/config/urls.py` (include watchlist urls)

- [ ] **Step 14.1: Write failing endpoint test**

Write `backend/apps/profiles/tests/test_endpoints.py`:

```python
import pytest
from rest_framework.test import APIClient

from apps.profiles.models import Watchlist, WatchlistSymbol


@pytest.fixture
def api():
    return APIClient()


@pytest.mark.django_db
def test_list_create_watchlist(api):
    assert api.get("/api/watchlists/").json() == []

    resp = api.post("/api/watchlists/", {"name": "Scalps"}, format="json")
    assert resp.status_code == 201
    wid = resp.json()["id"]

    data = api.get("/api/watchlists/").json()
    assert len(data) == 1
    assert data[0]["name"] == "Scalps"
    assert data[0]["id"] == wid


@pytest.mark.django_db
def test_rename_and_delete_watchlist(api):
    w = Watchlist.objects.create(name="A")
    api.patch(f"/api/watchlists/{w.id}/", {"name": "B"}, format="json")
    w.refresh_from_db()
    assert w.name == "B"

    api.delete(f"/api/watchlists/{w.id}/")
    assert not Watchlist.objects.filter(id=w.id).exists()


@pytest.mark.django_db
def test_add_remove_symbol(api):
    w = Watchlist.objects.create(name="A")

    r = api.post(f"/api/watchlists/{w.id}/symbols/", {"ticker": "spy"}, format="json")
    assert r.status_code == 201
    sid = r.json()["id"]
    assert WatchlistSymbol.objects.get(id=sid).ticker == "SPY"

    r = api.delete(f"/api/watchlists/{w.id}/symbols/{sid}/")
    assert r.status_code == 204
    assert not WatchlistSymbol.objects.filter(id=sid).exists()


@pytest.mark.django_db
def test_reorder_symbols(api):
    w = Watchlist.objects.create(name="A")
    a = WatchlistSymbol.objects.create(watchlist=w, ticker="SPY", sort_order=0)
    b = WatchlistSymbol.objects.create(watchlist=w, ticker="QQQ", sort_order=1)

    r = api.post(f"/api/watchlists/{w.id}/reorder/", {"order": [b.id, a.id]}, format="json")
    assert r.status_code == 200
    a.refresh_from_db(); b.refresh_from_db()
    assert b.sort_order == 0
    assert a.sort_order == 1


@pytest.mark.django_db
def test_duplicate_symbol_returns_400(api):
    w = Watchlist.objects.create(name="A")
    api.post(f"/api/watchlists/{w.id}/symbols/", {"ticker": "SPY"}, format="json")
    r = api.post(f"/api/watchlists/{w.id}/symbols/", {"ticker": "SPY"}, format="json")
    assert r.status_code == 400
```

- [ ] **Step 14.2: Write `backend/apps/profiles/serializers.py`**

```python
from rest_framework import serializers

from .models import Watchlist, WatchlistSymbol


class WatchlistSymbolSerializer(serializers.ModelSerializer):
    class Meta:
        model = WatchlistSymbol
        fields = ["id", "ticker", "sort_order"]
        read_only_fields = ["sort_order"]


class WatchlistSerializer(serializers.ModelSerializer):
    symbols = WatchlistSymbolSerializer(many=True, read_only=True)

    class Meta:
        model = Watchlist
        fields = ["id", "name", "created_at", "symbols"]
        read_only_fields = ["created_at"]
```

- [ ] **Step 14.3: Write `backend/apps/profiles/views.py`**

```python
"""Watchlist + WatchlistSymbol CRUD + reorder."""
from __future__ import annotations

from django.db import IntegrityError, transaction
from django.shortcuts import get_object_or_404
from rest_framework import mixins, status, viewsets
from rest_framework.decorators import action
from rest_framework.response import Response

from .models import Watchlist, WatchlistSymbol
from .serializers import WatchlistSerializer, WatchlistSymbolSerializer


class WatchlistViewSet(viewsets.ModelViewSet):
    queryset = Watchlist.objects.prefetch_related("symbols")
    serializer_class = WatchlistSerializer

    @action(detail=True, methods=["post"])
    def reorder(self, request, pk=None):
        """Body: {'order': [symbol_id, ...]}"""
        wl = self.get_object()
        ids = request.data.get("order", [])
        with transaction.atomic():
            for idx, sid in enumerate(ids):
                WatchlistSymbol.objects.filter(id=sid, watchlist=wl).update(sort_order=idx)
        return Response({"ok": True})


class WatchlistSymbolViewSet(
    mixins.CreateModelMixin, mixins.DestroyModelMixin, viewsets.GenericViewSet
):
    serializer_class = WatchlistSymbolSerializer

    def get_queryset(self):
        return WatchlistSymbol.objects.filter(watchlist_id=self.kwargs["watchlist_pk"])

    def create(self, request, *args, **kwargs):
        wl = get_object_or_404(Watchlist, pk=self.kwargs["watchlist_pk"])
        ticker = request.data.get("ticker", "").upper()
        if not ticker:
            return Response(
                {"code": "invalid_input", "message": "ticker is required"},
                status=400,
            )
        next_order = (wl.symbols.count())
        try:
            sym = WatchlistSymbol.objects.create(watchlist=wl, ticker=ticker, sort_order=next_order)
        except IntegrityError:
            return Response(
                {"code": "duplicate", "message": f"{ticker} is already in this watchlist"},
                status=400,
            )
        return Response(WatchlistSymbolSerializer(sym).data, status=201)
```

- [ ] **Step 14.4: Write `backend/apps/profiles/urls.py`**

```python
from django.urls import include, path
from rest_framework_nested import routers as nested_routers  # nested routers
from rest_framework.routers import DefaultRouter

from . import views

router = DefaultRouter()
router.register("watchlists", views.WatchlistViewSet, basename="watchlist")

symbols_router = nested_routers.NestedDefaultRouter(router, "watchlists", lookup="watchlist")
symbols_router.register("symbols", views.WatchlistSymbolViewSet, basename="watchlist-symbols")

urlpatterns = [
    path("", include(router.urls)),
    path("", include(symbols_router.urls)),
]
```

- [ ] **Step 14.5: Add `drf-nested-routers` dep**

Edit `pyproject.toml` — append to `[project].dependencies`:

```toml
    "drf-nested-routers>=0.94,<1.0",
```

Rebuild:
```bash
docker compose build web
docker compose up -d
```

- [ ] **Step 14.6: Mount URLs**

Edit `backend/config/urls.py`:

```python
urlpatterns = [
    path("admin/", admin.site.urls),
    path("api/", include("apps.core.urls")),
    path("api/schwab/", include("apps.secrets.urls")),
    path("api/", include("apps.profiles.urls")),
]
```

- [ ] **Step 14.7: Run tests + commit**

```bash
docker compose exec web pytest backend/apps/profiles/tests/test_endpoints.py -v
git add backend/apps/profiles backend/config/urls.py pyproject.toml
git commit -m "feat(profiles): watchlist CRUD + symbol add/remove/reorder endpoints"
```

Expected: 5 passed.

---

## Task 15: Market data DRF endpoints (TDD)

**Files:**
- Create: `backend/apps/market/serializers.py`, `urls.py`, `views.py`
- Create: `backend/apps/market/tests/test_endpoints.py`
- Modify: `backend/config/urls.py` (include market urls)

- [ ] **Step 15.1: Write failing endpoint tests**

Write `backend/apps/market/tests/test_endpoints.py`:

```python
from unittest.mock import patch

import pytest
from rest_framework.test import APIClient


@pytest.fixture
def api():
    return APIClient()


@pytest.fixture
def no_schwab(monkeypatch):
    """Raise SchwabNotConnectedError from every fetch service."""
    from apps.market.schwab_client import SchwabNotConnectedError

    def boom(*a, **kw):
        raise SchwabNotConnectedError("not connected")

    monkeypatch.setattr("apps.market.services.quotes._fetch_from_schwab", boom)
    monkeypatch.setattr("apps.market.services.ohlc._fetch_from_schwab", boom)
    monkeypatch.setattr("apps.market.services.positions._fetch_from_schwab", boom)


@pytest.mark.django_db
def test_quotes_endpoint_happy(api):
    with patch("apps.market.views.fetch_quotes", return_value={"SPY": {"last": 550.0}}):
        r = api.get("/api/market/quotes/?tickers=SPY")
        assert r.status_code == 200
        assert r.json() == {"SPY": {"last": 550.0}}


@pytest.mark.django_db
def test_quotes_endpoint_missing_param(api):
    r = api.get("/api/market/quotes/")
    assert r.status_code == 400
    assert r.json()["code"] == "missing_tickers"


@pytest.mark.django_db
def test_ohlc_endpoint_happy(api):
    bars = [{"ts": "2026-01-01T00:00:00+00:00", "open": 1, "high": 2, "low": 1, "close": 2, "volume": 10}]
    with patch("apps.market.views.fetch_ohlc", return_value=bars):
        r = api.get("/api/market/ohlc/?ticker=SPY&timeframe=1m&bars=60")
        assert r.status_code == 200
        assert r.json()["bars"] == bars


@pytest.mark.django_db
def test_positions_endpoint_happy(api):
    with patch("apps.market.views.fetch_positions", return_value=[{"ticker": "NVDA", "qty": 100}]):
        r = api.get("/api/market/positions/")
        assert r.status_code == 200
        assert r.json()[0]["ticker"] == "NVDA"


@pytest.mark.django_db
def test_context_endpoint_happy(api):
    ctx = {"spy_last": 550, "qqq_last": 480, "vix_last": 14, "sectors": {}, "breadth": {}}
    with patch("apps.market.views.fetch_market_context", return_value=ctx):
        r = api.get("/api/market/context/")
        assert r.status_code == 200
        assert r.json() == ctx


@pytest.mark.django_db
def test_not_connected_returns_503(api, no_schwab):
    r = api.get("/api/market/positions/")
    assert r.status_code == 503
    assert r.json()["code"] == "schwab_not_connected"
```

- [ ] **Step 15.2: Write `backend/apps/market/views.py`**

```python
"""Market data read endpoints."""
from __future__ import annotations

from django.http import HttpRequest, JsonResponse
from django.views.decorators.http import require_GET

from apps.market.schwab_client import SchwabNotConnectedError
from apps.market.services.context import fetch_market_context
from apps.market.services.ohlc import fetch_ohlc
from apps.market.services.positions import fetch_positions
from apps.market.services.quotes import fetch_quotes


def _err(code: str, message: str, status: int) -> JsonResponse:
    return JsonResponse({"code": code, "message": message}, status=status)


def _wrap_schwab(fn):
    """Decorator: catch SchwabNotConnectedError and return 503."""
    def inner(request: HttpRequest, *args, **kwargs):
        try:
            return fn(request, *args, **kwargs)
        except SchwabNotConnectedError as e:
            return _err("schwab_not_connected", str(e), 503)
    return inner


@require_GET
@_wrap_schwab
def quotes(request: HttpRequest) -> JsonResponse:
    tickers = request.GET.get("tickers", "").strip()
    if not tickers:
        return _err("missing_tickers", "Provide ?tickers=SPY,QQQ", 400)
    ticker_list = [t for t in tickers.split(",") if t]
    return JsonResponse(fetch_quotes(ticker_list))


@require_GET
@_wrap_schwab
def ohlc(request: HttpRequest) -> JsonResponse:
    ticker = request.GET.get("ticker", "").strip()
    timeframe = request.GET.get("timeframe", "1m")
    try:
        bars = int(request.GET.get("bars", "60"))
    except ValueError:
        return _err("invalid_bars", "bars must be an integer", 400)
    if not ticker:
        return _err("missing_ticker", "Provide ?ticker=", 400)
    try:
        result = fetch_ohlc(ticker, timeframe=timeframe, bars=bars)
    except ValueError as e:
        return _err("invalid_timeframe", str(e), 400)
    return JsonResponse({"ticker": ticker.upper(), "timeframe": timeframe, "bars": result})


@require_GET
@_wrap_schwab
def positions(_request: HttpRequest) -> JsonResponse:
    return JsonResponse(fetch_positions(), safe=False)


@require_GET
@_wrap_schwab
def context(_request: HttpRequest) -> JsonResponse:
    return JsonResponse(fetch_market_context())
```

- [ ] **Step 15.3: Write `backend/apps/market/urls.py`**

```python
from django.urls import path

from . import views

app_name = "market"

urlpatterns = [
    path("quotes/", views.quotes, name="quotes"),
    path("ohlc/", views.ohlc, name="ohlc"),
    path("positions/", views.positions, name="positions"),
    path("context/", views.context, name="context"),
]
```

- [ ] **Step 15.4: Mount + test + commit**

Edit `backend/config/urls.py` to add:
```python
    path("api/market/", include("apps.market.urls")),
```

```bash
docker compose exec web pytest backend/apps/market/tests/test_endpoints.py -v
git add backend/apps/market/views.py backend/apps/market/urls.py backend/apps/market/tests/test_endpoints.py backend/config/urls.py
git commit -m "feat(market): /api/market/{quotes,ohlc,positions,context} endpoints"
```

Expected: 6 passed.

---

## Task 16: Scheduled Schwab token refresh (Celery)

**Files:**
- Create: `backend/apps/market/tasks.py`
- Create: `backend/apps/market/tests/test_tasks.py`
- Modify: `backend/config/celery.py` (register beat schedule)

- [ ] **Step 16.1: Write failing test**

Write `backend/apps/market/tests/test_tasks.py`:

```python
from unittest.mock import patch

import pytest
from django.utils import timezone
from datetime import timedelta
from django.test import override_settings

from apps.secrets.models import ApiCredential
from apps.market.tasks import refresh_schwab_token


@pytest.mark.django_db
@override_settings(CELERY_TASK_ALWAYS_EAGER=True, CELERY_TASK_EAGER_PROPAGATES=True)
def test_refresh_noops_when_not_connected():
    result = refresh_schwab_token.delay().get(timeout=2)
    assert result == {"ok": False, "reason": "not_connected"}


@pytest.mark.django_db
@override_settings(CELERY_TASK_ALWAYS_EAGER=True, CELERY_TASK_EAGER_PROPAGATES=True)
def test_refresh_noops_when_fresh():
    ApiCredential.objects.create(
        provider="schwab",
        token={"access_token": "A", "refresh_token": "R"},
        expires_at=timezone.now() + timedelta(hours=1),
    )
    result = refresh_schwab_token.delay().get(timeout=2)
    assert result == {"ok": False, "reason": "fresh"}


@pytest.mark.django_db
@override_settings(CELERY_TASK_ALWAYS_EAGER=True, CELERY_TASK_EAGER_PROPAGATES=True)
def test_refresh_triggers_when_near_expiry():
    ApiCredential.objects.create(
        provider="schwab",
        token={"access_token": "A", "refresh_token": "OLD"},
        expires_at=timezone.now() + timedelta(minutes=2),  # <5 min
    )
    with patch("apps.market.tasks.refresh_token") as refresh, \
         patch("apps.market.tasks.persist_token") as persist:
        refresh.return_value = {"access_token": "NEW", "refresh_token": "NEW_R", "expires_at": 9999999999}
        result = refresh_schwab_token.delay().get(timeout=2)
    assert result == {"ok": True}
    refresh.assert_called_once_with("OLD")
    persist.assert_called_once()
```

- [ ] **Step 16.2: Write `backend/apps/market/tasks.py`**

```python
"""Scheduled Schwab token maintenance."""
from __future__ import annotations

from datetime import timedelta

from celery import shared_task
from django.utils import timezone

from apps.secrets.models import ApiCredential
from apps.secrets.schwab_oauth import refresh_token, persist_token


@shared_task(name="market.refresh_schwab_token")
def refresh_schwab_token() -> dict:
    """Proactively refresh the Schwab access token when <5 min remains.

    Fired every minute by Celery beat (see config/celery.py).
    """
    try:
        cred = ApiCredential.objects.get(provider="schwab")
    except ApiCredential.DoesNotExist:
        return {"ok": False, "reason": "not_connected"}

    if cred.expires_at and cred.expires_at > timezone.now() + timedelta(minutes=5):
        return {"ok": False, "reason": "fresh"}

    refresh_value = cred.token.get("refresh_token") if cred.token else None
    if not refresh_value:
        return {"ok": False, "reason": "no_refresh_token"}

    new_token = refresh_token(refresh_value)
    persist_token(new_token)
    return {"ok": True}
```

- [ ] **Step 16.3: Register beat schedule**

Edit `backend/config/celery.py` — append at bottom:

```python
from celery.schedules import crontab

app.conf.beat_schedule = {
    "refresh-schwab-token-every-minute": {
        "task": "market.refresh_schwab_token",
        "schedule": crontab(minute="*"),
    },
}
```

- [ ] **Step 16.4: Test + commit**

```bash
docker compose exec web pytest backend/apps/market/tests/test_tasks.py -v
docker compose restart beat   # pick up new schedule
git add backend/apps/market/tasks.py backend/apps/market/tests/test_tasks.py backend/config/celery.py
git commit -m "feat(market): scheduled Schwab token refresh via celery beat"
```

Expected: 3 passed.

---

## Task 17: Frontend — API client expansions (TDD)

**Files:**
- Modify: `frontend/src/api/client.ts`
- Create: `frontend/src/api/market.ts`
- Create: `frontend/src/api/watchlists.ts`
- Create: `frontend/src/api/schwab.ts`
- Create: `frontend/src/__tests__/api.test.ts`

- [ ] **Step 17.1: Modify `frontend/src/api/client.ts`**

Replace the file entirely:

```ts
const apiBase = import.meta.env.VITE_API_BASE_URL ?? "";

export class ApiError extends Error {
  constructor(public status: number, public code: string, message: string) {
    super(message);
  }
}

async function handle<T>(res: Response): Promise<T> {
  if (!res.ok) {
    let code = "error";
    let message = res.statusText;
    try {
      const body = await res.json();
      code = body.code ?? code;
      message = body.message ?? message;
    } catch {
      /* ignore */
    }
    throw new ApiError(res.status, code, message);
  }
  if (res.status === 204) return undefined as T;
  return (await res.json()) as T;
}

export function apiGet<T>(path: string): Promise<T> {
  return fetch(`${apiBase}${path}`, { credentials: "include" }).then(handle<T>);
}

export function apiPost<T>(path: string, body?: unknown): Promise<T> {
  return fetch(`${apiBase}${path}`, {
    method: "POST",
    credentials: "include",
    headers: body !== undefined ? { "Content-Type": "application/json" } : undefined,
    body: body !== undefined ? JSON.stringify(body) : undefined,
  }).then(handle<T>);
}

export function apiPatch<T>(path: string, body: unknown): Promise<T> {
  return fetch(`${apiBase}${path}`, {
    method: "PATCH",
    credentials: "include",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  }).then(handle<T>);
}

export function apiDelete(path: string): Promise<void> {
  return fetch(`${apiBase}${path}`, {
    method: "DELETE",
    credentials: "include",
  }).then(handle<void>);
}

export type HealthResponse = { status: "ok" };
export const fetchHealth = () => apiGet<HealthResponse>("/api/health/");
```

- [ ] **Step 17.2: Write `frontend/src/api/market.ts`**

```ts
import { apiGet } from "./client";

export type Quote = {
  last: number | null;
  bid: number | null;
  ask: number | null;
  volume: number | null;
  high: number | null;
  low: number | null;
  pct_change: number | null;
};

export type OhlcBar = {
  ts: string; open: number; high: number; low: number; close: number; volume: number;
};

export type Position = {
  ticker: string; qty: number; avg_cost: number | null; mkt_value: number | null;
  unrealized_pl: number | null; day_pl: number | null;
};

export type MarketContext = {
  spy_last: number | null; qqq_last: number | null; vix_last: number | null;
  sectors: Record<string, number | null>;
  breadth: Record<string, number | null>;
};

export const fetchQuotes = (tickers: string[]) =>
  apiGet<Record<string, Quote>>(`/api/market/quotes/?tickers=${encodeURIComponent(tickers.join(","))}`);

export const fetchOhlc = (ticker: string, timeframe: string, bars = 60) =>
  apiGet<{ ticker: string; timeframe: string; bars: OhlcBar[] }>(
    `/api/market/ohlc/?ticker=${encodeURIComponent(ticker)}&timeframe=${timeframe}&bars=${bars}`,
  );

export const fetchPositions = () => apiGet<Position[]>("/api/market/positions/");
export const fetchMarketContext = () => apiGet<MarketContext>("/api/market/context/");
```

- [ ] **Step 17.3: Write `frontend/src/api/watchlists.ts`**

```ts
import { apiDelete, apiGet, apiPatch, apiPost } from "./client";

export type WatchlistSymbol = { id: number; ticker: string; sort_order: number };
export type Watchlist = { id: number; name: string; created_at: string; symbols: WatchlistSymbol[] };

export const fetchWatchlists = () => apiGet<Watchlist[]>("/api/watchlists/");
export const fetchWatchlist = (id: number) => apiGet<Watchlist>(`/api/watchlists/${id}/`);
export const createWatchlist = (name: string) =>
  apiPost<Watchlist>("/api/watchlists/", { name });
export const renameWatchlist = (id: number, name: string) =>
  apiPatch<Watchlist>(`/api/watchlists/${id}/`, { name });
export const deleteWatchlist = (id: number) => apiDelete(`/api/watchlists/${id}/`);
export const addSymbol = (wid: number, ticker: string) =>
  apiPost<WatchlistSymbol>(`/api/watchlists/${wid}/symbols/`, { ticker });
export const removeSymbol = (wid: number, sid: number) =>
  apiDelete(`/api/watchlists/${wid}/symbols/${sid}/`);
export const reorderSymbols = (wid: number, order: number[]) =>
  apiPost<{ ok: boolean }>(`/api/watchlists/${wid}/reorder/`, { order });
```

- [ ] **Step 17.4: Write `frontend/src/api/schwab.ts`**

```ts
import { apiGet } from "./client";

export type SchwabStatus = { connected: boolean; expires_at: string | null };
export const fetchSchwabStatus = () => apiGet<SchwabStatus>("/api/schwab/status/");
export const fetchSchwabAuthorizeUrl = () => apiGet<{ url: string }>("/api/schwab/authorize/");
```

- [ ] **Step 17.5: Write api test**

Write `frontend/src/__tests__/api.test.ts`:

```ts
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { ApiError, apiGet, apiPost, apiDelete } from "../api/client";

describe("api client", () => {
  beforeEach(() => {
    vi.stubGlobal("fetch", vi.fn());
  });
  afterEach(() => {
    vi.unstubAllGlobals();
  });

  it("apiGet returns JSON on 200", async () => {
    (globalThis.fetch as any).mockResolvedValue({
      ok: true, status: 200, json: async () => ({ hello: "world" }),
    });
    const v = await apiGet<{ hello: string }>("/api/x/");
    expect(v).toEqual({ hello: "world" });
  });

  it("throws ApiError on non-2xx", async () => {
    (globalThis.fetch as any).mockResolvedValue({
      ok: false, status: 503, statusText: "bad", json: async () => ({ code: "oops", message: "nope" }),
    });
    await expect(apiGet("/api/y/")).rejects.toBeInstanceOf(ApiError);
  });

  it("apiDelete resolves void on 204", async () => {
    (globalThis.fetch as any).mockResolvedValue({ ok: true, status: 204 });
    await expect(apiDelete("/api/y/")).resolves.toBeUndefined();
  });

  it("apiPost sends JSON body", async () => {
    const mock = vi.fn().mockResolvedValue({ ok: true, status: 201, json: async () => ({ id: 1 }) });
    vi.stubGlobal("fetch", mock);
    await apiPost("/api/x/", { name: "A" });
    const [_, opts] = mock.mock.calls[0];
    expect(opts.method).toBe("POST");
    expect(opts.body).toBe(JSON.stringify({ name: "A" }));
  });
});
```

- [ ] **Step 17.6: Run tests + commit**

```bash
docker compose exec frontend npm test -- --run
git add frontend/src/api frontend/src/__tests__/api.test.ts
git commit -m "feat(frontend): typed api client + market/watchlists/schwab endpoints"
```

Expected: all previous App tests + 4 new api tests pass.

---

## Task 18: TanStack Query provider + QueryClient (TDD)

**Files:**
- Create: `frontend/src/hooks/queryClient.ts`
- Modify: `frontend/src/main.tsx` (wrap in provider)
- Create: `frontend/src/__tests__/queryClient.test.ts`

- [ ] **Step 18.1: Write failing test**

Write `frontend/src/__tests__/queryClient.test.ts`:

```ts
import { describe, expect, it } from "vitest";
import { queryClient } from "../hooks/queryClient";

describe("queryClient", () => {
  it("exposes a shared QueryClient with expected defaults", () => {
    const opts = queryClient.getDefaultOptions();
    expect(opts.queries?.staleTime).toBeGreaterThanOrEqual(0);
    expect(opts.queries?.retry).toBeDefined();
  });
});
```

- [ ] **Step 18.2: Write `frontend/src/hooks/queryClient.ts`**

```ts
import { QueryClient } from "@tanstack/react-query";

export const queryClient = new QueryClient({
  defaultOptions: {
    queries: {
      staleTime: 1000,       // 1s — live data feel
      gcTime: 60_000,
      retry: (failureCount, err: unknown) => {
        // Don't retry 4xx
        const e = err as { status?: number } | undefined;
        if (e?.status && e.status >= 400 && e.status < 500) return false;
        return failureCount < 2;
      },
      refetchOnWindowFocus: true,
    },
  },
});
```

- [ ] **Step 18.3: Wrap `main.tsx`**

Replace `frontend/src/main.tsx`:

```tsx
import { QueryClientProvider } from "@tanstack/react-query";
import { StrictMode } from "react";
import { createRoot } from "react-dom/client";
import App from "./App";
import { queryClient } from "./hooks/queryClient";
import "./styles/globals.css";

createRoot(document.getElementById("root")!).render(
  <StrictMode>
    <QueryClientProvider client={queryClient}>
      <App />
    </QueryClientProvider>
  </StrictMode>,
);
```

- [ ] **Step 18.4: Run + commit**

```bash
docker compose exec frontend npm test -- --run
git add frontend/src/hooks/queryClient.ts frontend/src/main.tsx frontend/src/__tests__/queryClient.test.ts
git commit -m "feat(frontend): TanStack Query client + provider"
```

---

## Task 19: Router + page scaffolding

**Files:**
- Create: `frontend/src/router.tsx`
- Create: `frontend/src/pages/Dashboard.tsx`, `Settings.tsx`, `WatchlistsList.tsx`, `WatchlistDetail.tsx`, `MarketTicker.tsx`
- Modify: `frontend/src/App.tsx` — swap health shell for `<RouterProvider />`

- [ ] **Step 19.1: Write `frontend/src/router.tsx`**

```tsx
import { createBrowserRouter } from "react-router-dom";
import Dashboard from "./pages/Dashboard";
import Settings from "./pages/Settings";
import WatchlistsList from "./pages/WatchlistsList";
import WatchlistDetail from "./pages/WatchlistDetail";
import MarketTicker from "./pages/MarketTicker";

export const router = createBrowserRouter([
  { path: "/", element: <Dashboard /> },
  { path: "/settings", element: <Settings /> },
  { path: "/watchlists", element: <WatchlistsList /> },
  { path: "/watchlists/:id", element: <WatchlistDetail /> },
  { path: "/market/:ticker", element: <MarketTicker /> },
]);
```

- [ ] **Step 19.2: Stub each page**

Write `frontend/src/pages/Dashboard.tsx`:

```tsx
export default function Dashboard() {
  return <main className="p-6"><h1 className="text-2xl font-semibold">Dashboard</h1></main>;
}
```

Write `frontend/src/pages/Settings.tsx`:
```tsx
export default function Settings() {
  return <main className="p-6"><h1 className="text-2xl font-semibold">Settings</h1></main>;
}
```

Write `frontend/src/pages/WatchlistsList.tsx`:
```tsx
export default function WatchlistsList() {
  return <main className="p-6"><h1 className="text-2xl font-semibold">Watchlists</h1></main>;
}
```

Write `frontend/src/pages/WatchlistDetail.tsx`:
```tsx
import { useParams } from "react-router-dom";
export default function WatchlistDetail() {
  const { id } = useParams<{ id: string }>();
  return <main className="p-6"><h1 className="text-2xl font-semibold">Watchlist {id}</h1></main>;
}
```

Write `frontend/src/pages/MarketTicker.tsx`:
```tsx
import { useParams } from "react-router-dom";
export default function MarketTicker() {
  const { ticker } = useParams<{ ticker: string }>();
  return <main className="p-6"><h1 className="text-2xl font-semibold">{ticker?.toUpperCase()}</h1></main>;
}
```

- [ ] **Step 19.3: Replace `App.tsx`**

```tsx
import { RouterProvider } from "react-router-dom";
import { router } from "./router";

export default function App() {
  return <RouterProvider router={router} />;
}
```

- [ ] **Step 19.4: Update or remove `App.test.tsx`**

The M1 App test (which checked "Stack is green") no longer applies. Replace with a smoke that routes render without crashing. Overwrite `frontend/src/__tests__/App.test.tsx`:

```tsx
import { QueryClientProvider } from "@tanstack/react-query";
import { render, screen } from "@testing-library/react";
import { MemoryRouter, RouterProvider, createMemoryRouter } from "react-router-dom";
import { describe, expect, it } from "vitest";
import { queryClient } from "../hooks/queryClient";
import Dashboard from "../pages/Dashboard";
import Settings from "../pages/Settings";

describe("pages", () => {
  it("renders Dashboard heading", () => {
    render(
      <QueryClientProvider client={queryClient}>
        <MemoryRouter><Dashboard /></MemoryRouter>
      </QueryClientProvider>,
    );
    expect(screen.getByText(/Dashboard/i)).toBeInTheDocument();
  });

  it("renders Settings heading", () => {
    render(
      <QueryClientProvider client={queryClient}>
        <MemoryRouter><Settings /></MemoryRouter>
      </QueryClientProvider>,
    );
    expect(screen.getByText(/Settings/i)).toBeInTheDocument();
  });
});
```

- [ ] **Step 19.5: Test + commit**

```bash
docker compose exec frontend npm test -- --run
git add frontend/src
git commit -m "feat(frontend): react-router with dashboard/settings/watchlists/ticker pages"
```

---

## Task 20: Schwab connection UI (`/settings`)

**Files:**
- Create: `frontend/src/components/SchwabConnectionCard.tsx`
- Create: `frontend/src/hooks/useSchwabStatus.ts`
- Modify: `frontend/src/pages/Settings.tsx`

- [ ] **Step 20.1: Hook**

Write `frontend/src/hooks/useSchwabStatus.ts`:

```ts
import { useQuery } from "@tanstack/react-query";
import { fetchSchwabStatus } from "@/api/schwab";

export const useSchwabStatus = () =>
  useQuery({
    queryKey: ["schwab", "status"],
    queryFn: fetchSchwabStatus,
    staleTime: 10_000,
  });
```

- [ ] **Step 20.2: Component**

Write `frontend/src/components/SchwabConnectionCard.tsx`:

```tsx
import { useSchwabStatus } from "@/hooks/useSchwabStatus";
import { fetchSchwabAuthorizeUrl } from "@/api/schwab";
import { formatDistanceToNow } from "date-fns";

export default function SchwabConnectionCard() {
  const { data, isLoading } = useSchwabStatus();
  if (isLoading) return <div className="p-4 rounded border border-slate-800">Checking Schwab…</div>;

  const connected = data?.connected ?? false;

  const onConnect = async () => {
    const { url } = await fetchSchwabAuthorizeUrl();
    window.location.href = url;
  };

  return (
    <div className="p-4 rounded border border-slate-800 space-y-2">
      <h2 className="text-lg font-medium">Charles Schwab</h2>
      {connected ? (
        <p className="text-emerald-400">
          Connected
          {data?.expires_at && <> · token refreshes in {formatDistanceToNow(new Date(data.expires_at))}</>}
        </p>
      ) : (
        <p className="text-rose-400">Not connected</p>
      )}
      <button
        onClick={onConnect}
        className="px-3 py-1.5 rounded bg-slate-700 hover:bg-slate-600 text-sm"
      >
        {connected ? "Reconnect" : "Connect Schwab"}
      </button>
    </div>
  );
}
```

- [ ] **Step 20.3: Wire into Settings page**

Replace `frontend/src/pages/Settings.tsx`:

```tsx
import SchwabConnectionCard from "@/components/SchwabConnectionCard";

export default function Settings() {
  return (
    <main className="p-6 max-w-3xl mx-auto space-y-4">
      <h1 className="text-2xl font-semibold">Settings</h1>
      <SchwabConnectionCard />
    </main>
  );
}
```

- [ ] **Step 20.4: Commit**

```bash
docker compose exec frontend npm test -- --run
git add frontend/src/hooks/useSchwabStatus.ts frontend/src/components/SchwabConnectionCard.tsx frontend/src/pages/Settings.tsx
git commit -m "feat(frontend): Schwab connection card on /settings"
```

---

## Task 21: Watchlist CRUD UI (`/watchlists`)

**Files:**
- Create: `frontend/src/hooks/useWatchlists.ts`
- Modify: `frontend/src/pages/WatchlistsList.tsx`

- [ ] **Step 21.1: Hook**

Write `frontend/src/hooks/useWatchlists.ts`:

```ts
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import {
  fetchWatchlists, createWatchlist, renameWatchlist, deleteWatchlist,
} from "@/api/watchlists";

export const useWatchlists = () =>
  useQuery({ queryKey: ["watchlists"], queryFn: fetchWatchlists });

export function useCreateWatchlist() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (name: string) => createWatchlist(name),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["watchlists"] }),
  });
}

export function useRenameWatchlist() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: ({ id, name }: { id: number; name: string }) => renameWatchlist(id, name),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["watchlists"] }),
  });
}

export function useDeleteWatchlist() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (id: number) => deleteWatchlist(id),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["watchlists"] }),
  });
}
```

- [ ] **Step 21.2: Page**

Replace `frontend/src/pages/WatchlistsList.tsx`:

```tsx
import { useState } from "react";
import { Link } from "react-router-dom";
import { useCreateWatchlist, useDeleteWatchlist, useWatchlists } from "@/hooks/useWatchlists";

export default function WatchlistsList() {
  const { data, isLoading } = useWatchlists();
  const create = useCreateWatchlist();
  const del = useDeleteWatchlist();
  const [name, setName] = useState("");

  return (
    <main className="p-6 max-w-3xl mx-auto space-y-4">
      <h1 className="text-2xl font-semibold">Watchlists</h1>

      <form
        className="flex gap-2"
        onSubmit={(e) => {
          e.preventDefault();
          if (!name.trim()) return;
          create.mutate(name.trim(), { onSuccess: () => setName("") });
        }}
      >
        <input
          value={name}
          onChange={(e) => setName(e.target.value)}
          placeholder="New watchlist name"
          className="flex-1 px-3 py-1.5 rounded bg-slate-900 border border-slate-700"
        />
        <button className="px-3 py-1.5 rounded bg-emerald-600 hover:bg-emerald-500">Create</button>
      </form>

      {isLoading ? (
        <p>Loading…</p>
      ) : (
        <ul className="space-y-1">
          {(data ?? []).map((w) => (
            <li key={w.id} className="flex items-center justify-between p-3 rounded border border-slate-800">
              <Link to={`/watchlists/${w.id}`} className="hover:underline">
                {w.name} <span className="text-slate-500 text-sm">({w.symbols.length} symbols)</span>
              </Link>
              <button
                onClick={() => del.mutate(w.id)}
                className="text-rose-400 text-sm hover:underline"
              >
                Delete
              </button>
            </li>
          ))}
        </ul>
      )}
    </main>
  );
}
```

- [ ] **Step 21.3: Commit**

```bash
git add frontend/src/hooks/useWatchlists.ts frontend/src/pages/WatchlistsList.tsx
git commit -m "feat(frontend): watchlists list/create/delete page"
```

---

## Task 22: Watchlist detail + symbol CRUD + live quotes

**Files:**
- Create: `frontend/src/hooks/useWatchlist.ts`
- Create: `frontend/src/hooks/useQuotes.ts`
- Create: `frontend/src/components/QuoteCell.tsx`
- Create: `frontend/src/components/WatchlistTable.tsx`
- Modify: `frontend/src/pages/WatchlistDetail.tsx`

- [ ] **Step 22.1: Hooks**

Write `frontend/src/hooks/useWatchlist.ts`:

```ts
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { addSymbol, fetchWatchlist, removeSymbol } from "@/api/watchlists";

export const useWatchlist = (id: number | null) =>
  useQuery({
    queryKey: ["watchlist", id],
    queryFn: () => fetchWatchlist(id!),
    enabled: id !== null,
  });

export function useAddSymbol(wid: number) {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (ticker: string) => addSymbol(wid, ticker),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["watchlist", wid] }),
  });
}

export function useRemoveSymbol(wid: number) {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (sid: number) => removeSymbol(wid, sid),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["watchlist", wid] }),
  });
}
```

Write `frontend/src/hooks/useQuotes.ts`:

```ts
import { useQuery } from "@tanstack/react-query";
import { fetchQuotes } from "@/api/market";

export const useQuotes = (tickers: string[], intervalMs = 3000) =>
  useQuery({
    queryKey: ["quotes", tickers.sort().join(",")],
    queryFn: () => fetchQuotes(tickers),
    enabled: tickers.length > 0,
    refetchInterval: tickers.length > 0 ? intervalMs : false,
  });
```

- [ ] **Step 22.2: Components**

Write `frontend/src/components/QuoteCell.tsx`:

```tsx
import type { Quote } from "@/api/market";

export default function QuoteCell({ q }: { q: Quote | undefined }) {
  if (!q || q.last === null) return <span className="text-slate-500">—</span>;
  const up = (q.pct_change ?? 0) >= 0;
  const pct = q.pct_change === null ? "" : `${up ? "+" : ""}${q.pct_change.toFixed(2)}%`;
  return (
    <span className="tabular-nums">
      <span>{q.last.toFixed(2)}</span>
      <span className={`ml-2 text-xs ${up ? "text-emerald-400" : "text-rose-400"}`}>{pct}</span>
    </span>
  );
}
```

Write `frontend/src/components/WatchlistTable.tsx`:

```tsx
import type { WatchlistSymbol } from "@/api/watchlists";
import { useQuotes } from "@/hooks/useQuotes";
import QuoteCell from "./QuoteCell";
import { Link } from "react-router-dom";

type Props = {
  symbols: WatchlistSymbol[];
  onRemove?: (sid: number) => void;
};

export default function WatchlistTable({ symbols, onRemove }: Props) {
  const tickers = symbols.map((s) => s.ticker);
  const { data: quotes } = useQuotes(tickers);

  return (
    <table className="w-full text-sm">
      <thead>
        <tr className="text-slate-400 text-left">
          <th className="py-2">Ticker</th>
          <th className="py-2">Last</th>
          <th className="py-2">Bid</th>
          <th className="py-2">Ask</th>
          <th className="py-2">Vol</th>
          <th />
        </tr>
      </thead>
      <tbody>
        {symbols.map((s) => {
          const q = quotes?.[s.ticker];
          return (
            <tr key={s.id} className="border-t border-slate-800">
              <td className="py-2">
                <Link to={`/market/${s.ticker}`} className="hover:underline font-medium">
                  {s.ticker}
                </Link>
              </td>
              <td className="py-2"><QuoteCell q={q} /></td>
              <td className="py-2 tabular-nums text-slate-300">{q?.bid?.toFixed(2) ?? "—"}</td>
              <td className="py-2 tabular-nums text-slate-300">{q?.ask?.toFixed(2) ?? "—"}</td>
              <td className="py-2 tabular-nums text-slate-400">{q?.volume?.toLocaleString() ?? "—"}</td>
              <td className="py-2">
                {onRemove && (
                  <button onClick={() => onRemove(s.id)} className="text-rose-400 hover:underline text-xs">
                    Remove
                  </button>
                )}
              </td>
            </tr>
          );
        })}
      </tbody>
    </table>
  );
}
```

- [ ] **Step 22.3: Page**

Replace `frontend/src/pages/WatchlistDetail.tsx`:

```tsx
import { useState } from "react";
import { useParams } from "react-router-dom";
import WatchlistTable from "@/components/WatchlistTable";
import { useAddSymbol, useRemoveSymbol, useWatchlist } from "@/hooks/useWatchlist";

export default function WatchlistDetail() {
  const { id } = useParams<{ id: string }>();
  const wid = id ? parseInt(id, 10) : null;
  const { data: wl, isLoading } = useWatchlist(wid);
  const add = useAddSymbol(wid ?? 0);
  const remove = useRemoveSymbol(wid ?? 0);
  const [ticker, setTicker] = useState("");

  if (!wid) return <main className="p-6">Invalid watchlist</main>;
  if (isLoading || !wl) return <main className="p-6">Loading…</main>;

  return (
    <main className="p-6 max-w-4xl mx-auto space-y-4">
      <h1 className="text-2xl font-semibold">{wl.name}</h1>

      <form
        className="flex gap-2"
        onSubmit={(e) => {
          e.preventDefault();
          if (!ticker.trim()) return;
          add.mutate(ticker.trim().toUpperCase(), {
            onSuccess: () => setTicker(""),
          });
        }}
      >
        <input
          value={ticker}
          onChange={(e) => setTicker(e.target.value.toUpperCase())}
          placeholder="Add ticker (e.g. SPY)"
          className="flex-1 px-3 py-1.5 rounded bg-slate-900 border border-slate-700"
        />
        <button className="px-3 py-1.5 rounded bg-emerald-600 hover:bg-emerald-500">Add</button>
      </form>
      {add.isError && (
        <p className="text-rose-400 text-sm">{(add.error as Error).message}</p>
      )}

      <WatchlistTable symbols={wl.symbols} onRemove={(sid) => remove.mutate(sid)} />
    </main>
  );
}
```

- [ ] **Step 22.4: Commit**

```bash
git add frontend/src/hooks/useWatchlist.ts frontend/src/hooks/useQuotes.ts \
        frontend/src/components/QuoteCell.tsx frontend/src/components/WatchlistTable.tsx \
        frontend/src/pages/WatchlistDetail.tsx
git commit -m "feat(frontend): watchlist detail with live quotes + symbol CRUD"
```

---

## Task 23: Positions + market context on dashboard

**Files:**
- Create: `frontend/src/hooks/usePositions.ts`, `useMarketContext.ts`
- Create: `frontend/src/components/PositionsTable.tsx`, `MarketContextStrip.tsx`
- Modify: `frontend/src/pages/Dashboard.tsx`

- [ ] **Step 23.1: Hooks**

Write `frontend/src/hooks/usePositions.ts`:

```ts
import { useQuery } from "@tanstack/react-query";
import { fetchPositions } from "@/api/market";

export const usePositions = () =>
  useQuery({
    queryKey: ["positions"],
    queryFn: fetchPositions,
    refetchInterval: 10_000,
  });
```

Write `frontend/src/hooks/useMarketContext.ts`:

```ts
import { useQuery } from "@tanstack/react-query";
import { fetchMarketContext } from "@/api/market";

export const useMarketContext = () =>
  useQuery({
    queryKey: ["market-context"],
    queryFn: fetchMarketContext,
    refetchInterval: 30_000,
  });
```

- [ ] **Step 23.2: Components**

Write `frontend/src/components/PositionsTable.tsx`:

```tsx
import { usePositions } from "@/hooks/usePositions";

export default function PositionsTable() {
  const { data, isLoading, error } = usePositions();
  if (error) return <p className="text-rose-400 text-sm">Could not load positions: {(error as Error).message}</p>;
  if (isLoading) return <p>Loading positions…</p>;
  if (!data?.length) return <p className="text-slate-400">No open positions.</p>;

  const totalPl = data.reduce((s, p) => s + (p.unrealized_pl ?? 0), 0);
  const totalDay = data.reduce((s, p) => s + (p.day_pl ?? 0), 0);

  return (
    <div>
      <table className="w-full text-sm">
        <thead>
          <tr className="text-slate-400 text-left">
            <th className="py-2">Ticker</th>
            <th className="py-2">Qty</th>
            <th className="py-2">Avg</th>
            <th className="py-2">Value</th>
            <th className="py-2">Day P/L</th>
            <th className="py-2">Unrealized</th>
          </tr>
        </thead>
        <tbody>
          {data.map((p) => (
            <tr key={p.ticker} className="border-t border-slate-800">
              <td className="py-2 font-medium">{p.ticker}</td>
              <td className="py-2 tabular-nums">{p.qty}</td>
              <td className="py-2 tabular-nums">{p.avg_cost?.toFixed(2) ?? "—"}</td>
              <td className="py-2 tabular-nums">{p.mkt_value?.toFixed(2) ?? "—"}</td>
              <td className={`py-2 tabular-nums ${(p.day_pl ?? 0) >= 0 ? "text-emerald-400" : "text-rose-400"}`}>
                {p.day_pl?.toFixed(2) ?? "—"}
              </td>
              <td className={`py-2 tabular-nums ${(p.unrealized_pl ?? 0) >= 0 ? "text-emerald-400" : "text-rose-400"}`}>
                {p.unrealized_pl?.toFixed(2) ?? "—"}
              </td>
            </tr>
          ))}
          <tr className="border-t border-slate-700 font-semibold">
            <td colSpan={4} className="py-2 text-right">Totals</td>
            <td className={`py-2 tabular-nums ${totalDay >= 0 ? "text-emerald-400" : "text-rose-400"}`}>
              {totalDay.toFixed(2)}
            </td>
            <td className={`py-2 tabular-nums ${totalPl >= 0 ? "text-emerald-400" : "text-rose-400"}`}>
              {totalPl.toFixed(2)}
            </td>
          </tr>
        </tbody>
      </table>
    </div>
  );
}
```

Write `frontend/src/components/MarketContextStrip.tsx`:

```tsx
import { useMarketContext } from "@/hooks/useMarketContext";

function Chip({ label, value, tone = "text-slate-200" }: { label: string; value: number | null; tone?: string }) {
  return (
    <div className="px-3 py-1.5 rounded border border-slate-800 bg-slate-900/50 min-w-[90px]">
      <div className="text-xs text-slate-500">{label}</div>
      <div className={`text-sm tabular-nums ${tone}`}>{value?.toFixed(2) ?? "—"}</div>
    </div>
  );
}

export default function MarketContextStrip() {
  const { data } = useMarketContext();
  if (!data) return null;
  return (
    <div className="flex flex-wrap gap-2">
      <Chip label="SPY" value={data.spy_last} />
      <Chip label="QQQ" value={data.qqq_last} />
      <Chip label="VIX" value={data.vix_last} tone="text-amber-400" />
      {Object.entries(data.sectors).map(([k, v]) => (
        <Chip key={k} label={k} value={v} />
      ))}
    </div>
  );
}
```

- [ ] **Step 23.3: Dashboard page**

Replace `frontend/src/pages/Dashboard.tsx`:

```tsx
import MarketContextStrip from "@/components/MarketContextStrip";
import PositionsTable from "@/components/PositionsTable";
import { Link } from "react-router-dom";

export default function Dashboard() {
  return (
    <main className="p-6 max-w-6xl mx-auto space-y-6">
      <header className="flex items-center justify-between">
        <h1 className="text-2xl font-semibold">Dashboard</h1>
        <nav className="text-sm space-x-4">
          <Link className="text-slate-300 hover:underline" to="/watchlists">Watchlists</Link>
          <Link className="text-slate-300 hover:underline" to="/settings">Settings</Link>
        </nav>
      </header>

      <section>
        <h2 className="text-sm uppercase tracking-wide text-slate-400 mb-2">Market context</h2>
        <MarketContextStrip />
      </section>

      <section>
        <h2 className="text-sm uppercase tracking-wide text-slate-400 mb-2">Positions</h2>
        <PositionsTable />
      </section>
    </main>
  );
}
```

- [ ] **Step 23.4: Commit**

```bash
git add frontend/src/hooks frontend/src/components/PositionsTable.tsx \
        frontend/src/components/MarketContextStrip.tsx frontend/src/pages/Dashboard.tsx
git commit -m "feat(frontend): dashboard with positions + market context"
```

---

## Task 24: Per-ticker page (quote + chart placeholder)

Tradingview `lightweight-charts` is slated for M5 (chart images). For M2, the per-ticker page shows last quote + a simple OHLC table. A proper chart lands with M5.

**Files:**
- Create: `frontend/src/hooks/useOhlc.ts`
- Modify: `frontend/src/pages/MarketTicker.tsx`

- [ ] **Step 24.1: Hook**

Write `frontend/src/hooks/useOhlc.ts`:

```ts
import { useQuery } from "@tanstack/react-query";
import { fetchOhlc } from "@/api/market";

export const useOhlc = (ticker: string, timeframe: string, bars = 60) =>
  useQuery({
    queryKey: ["ohlc", ticker, timeframe, bars],
    queryFn: () => fetchOhlc(ticker, timeframe, bars),
    enabled: !!ticker,
    refetchInterval: 30_000,
  });
```

- [ ] **Step 24.2: Page**

Replace `frontend/src/pages/MarketTicker.tsx`:

```tsx
import { useState } from "react";
import { useParams, Link } from "react-router-dom";
import { useQuotes } from "@/hooks/useQuotes";
import { useOhlc } from "@/hooks/useOhlc";
import QuoteCell from "@/components/QuoteCell";
import { format } from "date-fns";

const TIMEFRAMES = ["1m", "5m", "15m", "1h", "1d"];

export default function MarketTicker() {
  const { ticker = "" } = useParams<{ ticker: string }>();
  const T = ticker.toUpperCase();
  const [tf, setTf] = useState("1m");
  const { data: quotes } = useQuotes([T]);
  const { data: ohlc } = useOhlc(T, tf, 60);

  return (
    <main className="p-6 max-w-5xl mx-auto space-y-4">
      <div className="flex items-center justify-between">
        <h1 className="text-2xl font-semibold">{T}</h1>
        <Link to="/" className="text-sm text-slate-300 hover:underline">← Dashboard</Link>
      </div>

      <div className="text-xl"><QuoteCell q={quotes?.[T]} /></div>

      <div className="flex gap-2">
        {TIMEFRAMES.map((x) => (
          <button
            key={x}
            onClick={() => setTf(x)}
            className={`px-2 py-1 rounded text-sm ${
              tf === x ? "bg-slate-600" : "bg-slate-800 hover:bg-slate-700"
            }`}
          >
            {x}
          </button>
        ))}
      </div>

      <div className="max-h-[480px] overflow-y-auto border border-slate-800 rounded">
        <table className="w-full text-sm">
          <thead className="bg-slate-900/80 sticky top-0">
            <tr className="text-slate-400 text-left">
              <th className="px-3 py-2">Time</th>
              <th className="px-3 py-2">Open</th>
              <th className="px-3 py-2">High</th>
              <th className="px-3 py-2">Low</th>
              <th className="px-3 py-2">Close</th>
              <th className="px-3 py-2">Volume</th>
            </tr>
          </thead>
          <tbody>
            {(ohlc?.bars ?? []).slice().reverse().map((b) => (
              <tr key={b.ts} className="border-t border-slate-800">
                <td className="px-3 py-1.5 tabular-nums text-slate-400">{format(new Date(b.ts), "MMM d HH:mm")}</td>
                <td className="px-3 py-1.5 tabular-nums">{b.open.toFixed(2)}</td>
                <td className="px-3 py-1.5 tabular-nums">{b.high.toFixed(2)}</td>
                <td className="px-3 py-1.5 tabular-nums">{b.low.toFixed(2)}</td>
                <td className="px-3 py-1.5 tabular-nums">{b.close.toFixed(2)}</td>
                <td className="px-3 py-1.5 tabular-nums text-slate-400">{b.volume.toLocaleString()}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </main>
  );
}
```

- [ ] **Step 24.3: Commit**

```bash
git add frontend/src/hooks/useOhlc.ts frontend/src/pages/MarketTicker.tsx
git commit -m "feat(frontend): /market/:ticker with live quote + OHLC table"
```

---

## Task 25: End-to-end smoke + tag

- [ ] **Step 25.1: Full backend test suite**

```bash
cd /home/dan/ai-dashboard
docker compose exec web pytest -v
```

Expected: all tests pass (M1 + M2 additions).

- [ ] **Step 25.2: Full frontend test suite**

```bash
docker compose exec frontend npm test -- --run
```

Expected: all tests pass.

- [ ] **Step 25.3: Lint**

```bash
make lint
```

Expected: zero errors.

- [ ] **Step 25.4: Happy-path Schwab smoke (OPTIONAL — requires real Schwab app)**

Skip this step unless the user has configured real `SCHWAB_CLIENT_ID`/`SCHWAB_CLIENT_SECRET` in `.env`. If so:

1. Start the stack: `docker compose up -d`.
2. Navigate to `http://localhost:5173/settings`.
3. Click "Connect Schwab", complete OAuth in the browser.
4. After redirect, verify `http://localhost:8000/api/schwab/status/` → `{"connected": true, ...}`.
5. Create a watchlist with a few symbols at `/watchlists`.
6. Confirm live quotes update in the watchlist table.
7. Navigate to `/market/SPY`, verify OHLC bars load.
8. Visit `/` — positions + market context render.

If Schwab is not configured, document "Schwab smoke deferred — requires real credentials" in the commit message below and move on.

- [ ] **Step 25.5: UI smoke without Schwab (mocked via browser DevTools)**

Without Schwab configured, the `/api/market/*` endpoints return 503. The UI should show graceful error states:

- Dashboard: PositionsTable shows "Could not load positions: …"
- MarketContextStrip: silently hides
- WatchlistTable: shows `—` for quotes
- Settings: SchwabConnectionCard shows "Not connected"

Verify by opening `http://localhost:5173/` and checking each.

- [ ] **Step 25.6: Cold rebuild sanity**

```bash
docker compose down -v
docker compose build --no-cache
docker compose up -d
sleep 30
curl -s http://localhost:8000/api/health/
curl -s http://localhost:8000/api/ready/
curl -s -o /dev/null -w "%{http_code}\n" http://localhost:5173/
make test
```

Expected: all green from a cold start.

- [ ] **Step 25.7: Final commit + tag**

```bash
git status
git add -u
git commit -m "chore: M2 market data core verified" || echo "nothing to commit"

git tag -a m2-market-data -m "M2: Schwab OAuth + market data backend + watchlists UI"
git log --oneline -5
```

---

## Done

Next up: **M3 — Snapshots + AI** (capture pipeline, serializer, Claude provider end-to-end, one-shot consult mode).
