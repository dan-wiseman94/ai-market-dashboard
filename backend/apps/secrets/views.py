"""Schwab OAuth endpoints."""

from __future__ import annotations

import logging

import openai
from asgiref.sync import async_to_sync
from cryptography.fernet import InvalidToken
from django.conf import settings
from django.http import HttpRequest, HttpResponseRedirect, JsonResponse
from django.utils import timezone
from django.views.decorators.http import require_GET
from rest_framework import viewsets
from rest_framework.decorators import action
from rest_framework.response import Response

from apps.ai.catalog import list_models as _list_catalog
from apps.ai.cost import daily_spend_usd
from apps.ai.providers import get_provider
from apps.secrets.models import ApiCredential, ProviderConfig
from apps.secrets.schwab_oauth import (
    SchwabNotConfigured,
    build_authorize_url,
    exchange_code_for_token,
    persist_token,
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
