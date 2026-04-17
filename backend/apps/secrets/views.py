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
