"""Schwab OAuth endpoints."""

from __future__ import annotations

import json
import logging

import openai
from asgiref.sync import async_to_sync
from cryptography.fernet import InvalidToken
from django.conf import settings
from django.http import HttpRequest, HttpResponseRedirect, JsonResponse
from django.utils import timezone
from django.views.decorators.http import require_GET, require_http_methods
from rest_framework import viewsets
from rest_framework.decorators import action
from rest_framework.response import Response

from apps.ai.catalog import list_models as _list_catalog
from apps.ai.cost import daily_spend_usd
from apps.ai.providers import get_provider
from apps.secrets.data_source_test import test_credential
from apps.secrets.data_sources import DATA_SOURCES, get_data_source
from apps.secrets.models import ApiCredential, ProviderConfig, SchwabAppConfig
from apps.secrets.schwab_oauth import (
    SchwabNotConfigured,
    build_authorize_url,
    exchange_code_for_token,
    persist_token,
    schwab_app_credentials,
)
from apps.secrets.serializers import ProviderConfigSerializer

log = logging.getLogger(__name__)


@require_GET
def schwab_authorize(_request: HttpRequest) -> JsonResponse:
    """Returns the URL the frontend should open to begin Schwab OAuth."""
    try:
        return JsonResponse({"url": build_authorize_url()})
    except SchwabNotConfigured as exc:
        # No client_id set — fail clearly instead of emitting an authorize URL with an
        # empty client_id (which Schwab rejects with an opaque 401 invalid_client).
        return JsonResponse({"code": "schwab_not_configured", "message": str(exc)}, status=400)


@require_GET
def schwab_callback(request: HttpRequest) -> JsonResponse | HttpResponseRedirect:
    """Schwab redirects here with ?code=... after user consent."""
    code = request.GET.get("code")
    if not code:
        return JsonResponse(
            {
                "code": "missing_code",
                "message": "Schwab callback did not include a code parameter.",
            },
            status=400,
        )
    try:
        token = exchange_code_for_token(code)
    except Exception as exc:
        return JsonResponse(
            {"code": "oauth_exchange_failed", "message": str(exc)},
            status=502,
        )
    persist_token(token)
    return HttpResponseRedirect(f"{settings.FRONTEND_BASE_URL}/settings?schwab=connected")


@require_GET
def schwab_status(_request: HttpRequest) -> JsonResponse:
    try:
        cred = ApiCredential.objects.get(provider="schwab")
    except ApiCredential.DoesNotExist:
        return JsonResponse({"connected": False, "expires_at": None})
    except InvalidToken:
        # The stored token was encrypted under a key that no longer exists (DJANGO_SECRET_KEY
        # rotated or /data salt reset). Decryption fires during the .get() row fetch via
        # EncryptedJSONField.from_db_value, so this lands here rather than below. The token is
        # unusable — report not-connected so the UI prompts a reconnect (which overwrites the
        # dead row) instead of returning a 500 on every status poll.
        log.warning(
            "Schwab credential is undecryptable (encryption key rotated or salt reset); "
            "reconnect Schwab to overwrite it."
        )
        return JsonResponse({"connected": False, "expires_at": None})
    return JsonResponse(
        {
            "connected": True,
            "expires_at": cred.expires_at.isoformat() if cred.expires_at else None,
        }
    )


def _load_app_config() -> SchwabAppConfig:
    """Load the singleton, self-healing past an undecryptable row (key rotated/salt reset)
    so the user can always re-enter credentials through the UI."""
    try:
        return SchwabAppConfig.load()
    except InvalidToken:
        SchwabAppConfig.objects.all().delete()  # fast delete — doesn't decrypt
        return SchwabAppConfig.load()


def _app_config_payload(cfg: SchwabAppConfig) -> dict:
    client_id, client_secret = schwab_app_credentials()
    return {
        # DB-stored client_id (blank if Schwab is only configured via env).
        "client_id": cfg.client_id,
        "client_secret_present": bool(cfg.client_secret),
        # Whether Schwab can actually connect (DB creds OR env fallback).
        "configured": bool(client_id and client_secret),
    }


@require_http_methods(["GET", "PATCH"])
def schwab_app_config(request: HttpRequest) -> JsonResponse:
    """Read or update the Schwab app credentials (client_id + secret) from the UI.

    GET  → {client_id, client_secret_present, configured}
    PATCH {client_id?, client_secret_write?} → persists to the encrypted singleton.
    The secret is write-only: a blank/absent client_secret_write leaves it unchanged.
    """
    cfg = _load_app_config()
    if request.method == "PATCH":
        try:
            body = json.loads(request.body or "{}")
        except json.JSONDecodeError:
            return JsonResponse(
                {"code": "invalid_json", "message": "Request body must be JSON."}, status=400
            )
        if "client_id" in body:
            cfg.client_id = (body.get("client_id") or "").strip()
        secret = body.get("client_secret_write")
        if secret:  # only overwrite when a non-empty value is supplied
            cfg.client_secret = secret.strip()
        cfg.save()
    return JsonResponse(_app_config_payload(cfg))


class ProviderConfigViewSet(viewsets.ModelViewSet):
    queryset = ProviderConfig.objects.all()
    serializer_class = ProviderConfigSerializer
    lookup_field = "provider"

    @action(detail=True, methods=["post"], url_path="probe")
    def probe(self, request, provider=None):
        """List models from the endpoint — also a reachability/compat test.

        Persists any base_url/api_key in the body first, so the stored
        model list always corresponds to the saved endpoint.
        """
        cfg = self.get_object()
        base_url = request.data.get("base_url")
        api_key_write = request.data.get("api_key_write")
        dirty = False
        if base_url is not None:
            cfg.base_url = base_url
            dirty = True
        if api_key_write:
            cfg.api_key = api_key_write
            dirty = True
        if dirty:
            cfg.save()

        if not cfg.base_url:
            return Response({"ok": False, "error": "Base URL is required."}, status=400)

        if cfg.provider not in ("local", "openai"):
            return Response(
                {"ok": False, "error": "Model discovery isn't supported for this provider."}
            )

        provider_obj = get_provider(cfg.provider, api_key=cfg.api_key, base_url=cfg.base_url)
        try:
            models = async_to_sync(provider_obj.list_models)(timeout=5.0)
        except Exception as exc:
            return Response({"ok": False, "error": _friendly_probe_error(exc, cfg.base_url)})

        cfg.discovered_models = models
        cfg.models_synced_at = timezone.now()
        cfg.save(update_fields=["discovered_models", "models_synced_at", "updated_at"])
        return Response(
            {"ok": True, "models": models, "synced_at": cfg.models_synced_at.isoformat()}
        )


def _friendly_probe_error(exc: Exception, base_url: str) -> str:
    # APITimeoutError subclasses APIConnectionError — check it first.
    if isinstance(exc, openai.APITimeoutError):
        return f"Timed out reaching {base_url}."
    if isinstance(exc, (openai.AuthenticationError, openai.PermissionDeniedError)):
        return "Endpoint requires an API key."
    if isinstance(exc, openai.APIConnectionError):
        return (
            f"Couldn't reach {base_url}. Is the server running? "
            "On Linux use http://host.docker.internal:<port>/v1."
        )
    return "Reached the server, but it doesn't respond like an OpenAI-compatible API."


@require_GET
def ai_models(request: HttpRequest) -> JsonResponse:
    provider = request.GET.get("provider")
    models = _list_catalog(provider)
    return JsonResponse(
        {
            "models": [
                {
                    "id": m.id,
                    "name": m.name,
                    "provider": m.provider,
                    "input_per_mtok": m.input_per_mtok,
                    "output_per_mtok": m.output_per_mtok,
                    "cached_per_mtok": m.cached_per_mtok,
                    "context_window": m.context_window,
                    "supports_vision": m.supports_vision,
                }
                for m in models
            ],
        }
    )


@require_GET
def ai_usage(_request: HttpRequest) -> JsonResponse:
    return JsonResponse(
        {
            "today": {p: str(daily_spend_usd(p)) for p in ["claude", "openai", "local"]},
        }
    )


# ---------------------------------------------------------------------------
# Data-source credentials — the settings "Data sources" GUI
# ---------------------------------------------------------------------------


def _ds_err(code: str, message: str, status: int) -> JsonResponse:
    return JsonResponse({"code": code, "message": message}, status=status)


def _schwab_connected() -> bool:
    """True when a Schwab OAuth credential row exists and decrypts (mirrors schwab_status)."""
    try:
        ApiCredential.objects.get(provider="schwab")
    except (ApiCredential.DoesNotExist, InvalidToken):
        return False
    return True


def _credential_status(provider: str) -> dict:
    """Which credential fields are present for ``provider`` — never the values.

    An undecryptable row (encryption key rotated / salt reset) reports as
    not-configured so the UI lets the user re-enter the key (overwriting it).
    """
    try:
        cred = ApiCredential.objects.get(provider=provider)
    except (ApiCredential.DoesNotExist, InvalidToken):
        return {"configured": False, "fields_present": []}
    token = cred.token or {}
    present = [k for k in ("api_key", "api_secret") if token.get(k)]
    return {"configured": bool(present), "fields_present": present}


def _data_source_payload(ds: dict, present: set[str]) -> dict:
    keys = ("provider", "label", "auth", "fields", "blurb", "signup_url", "docs_url")
    entry = {k: ds[k] for k in keys}
    if ds["auth"] == "none":
        entry["status"] = {"configured": True, "fields_present": []}  # keyless → always on
    elif ds["provider"] not in present:
        entry["status"] = {"configured": False, "fields_present": []}  # no row → skip the query
    elif ds["auth"] == "oauth":
        entry["status"] = {"configured": _schwab_connected(), "fields_present": []}
    else:
        entry["status"] = _credential_status(ds["provider"])
    return entry


@require_GET
def data_sources(_request: HttpRequest) -> JsonResponse:
    """List every market-data provider + whether it's configured (no secrets returned)."""
    # One cheap query for which providers have a row (no token decryption); only the
    # providers that actually have a credential pay for a per-row status lookup.
    present = set(ApiCredential.objects.values_list("provider", flat=True))
    return JsonResponse(
        {"data_sources": [_data_source_payload(ds, present) for ds in DATA_SOURCES]}
    )


@require_http_methods(["PUT", "DELETE"])
def data_source_detail(request: HttpRequest, provider: str) -> JsonResponse:
    """Save (PUT) or clear (DELETE) the API key(s) for one key-based data source.

    PUT body carries ``{"<field>_write": "..."}`` per the source's ``fields``. Values
    are write-only; a blank/absent field leaves an existing value unchanged (so you can
    rotate the key without re-entering the secret). Responses never echo a stored value.
    """
    ds = get_data_source(provider)
    if ds is None:
        return _ds_err("unknown_provider", f"Unknown data source '{provider}'.", 404)
    if ds["auth"] in ("none", "oauth"):
        return _ds_err("not_key_managed", f"{ds['label']} isn't configured with a key here.", 400)

    if request.method == "DELETE":
        ApiCredential.objects.filter(provider=provider).delete()
        return JsonResponse(_credential_status(provider))

    try:
        body = json.loads(request.body or "{}")
    except json.JSONDecodeError:
        return _ds_err("invalid_json", "Request body must be JSON.", 400)

    # Merge over any existing token so a partial PUT keeps untouched fields.
    try:
        existing = dict(ApiCredential.objects.get(provider=provider).token or {})
    except (ApiCredential.DoesNotExist, InvalidToken):
        existing = {}
    for field in ds["fields"]:
        value = (body.get(f"{field}_write") or "").strip()
        if value:
            existing[field] = value

    primary = ds["fields"][0]
    if not existing.get(primary):
        return _ds_err("missing_key", f"{primary}_write is required.", 400)

    ApiCredential.objects.update_or_create(provider=provider, defaults={"token": existing})
    return JsonResponse(_credential_status(provider))


@require_http_methods(["POST"])
def data_source_test(_request: HttpRequest, provider: str) -> JsonResponse:
    """Probe the saved credential for one key-based source. Returns ``{ok, message}``."""
    ds = get_data_source(provider)
    if ds is None:
        return _ds_err("unknown_provider", f"Unknown data source '{provider}'.", 404)
    if ds["auth"] in ("none", "oauth"):
        return _ds_err("not_key_managed", f"{ds['label']} has no key to test.", 400)
    return JsonResponse(test_credential(provider))
