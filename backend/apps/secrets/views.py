"""Schwab OAuth endpoints."""

from __future__ import annotations

from django.conf import settings
from django.http import HttpRequest, HttpResponseRedirect, JsonResponse
from django.views.decorators.http import require_GET
from rest_framework import viewsets

from apps.ai.catalog import list_models as _list_catalog
from apps.ai.cost import daily_spend_usd
from apps.secrets.models import ApiCredential, ProviderConfig
from apps.secrets.schwab_oauth import (
    build_authorize_url,
    exchange_code_for_token,
    persist_token,
)
from apps.secrets.serializers import ProviderConfigSerializer


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
