from django.http import HttpRequest, JsonResponse
from django.views.decorators.http import require_GET

from apps.costs.services import cost_breakdown_today


@require_GET
def costs_today(_request: HttpRequest) -> JsonResponse:
    out = cost_breakdown_today()
    return JsonResponse({
        "total_usd": str(out["total_usd"]),
        "by_provider": [
            {
                "provider": row["provider"],
                "cost_usd": str(row["cost_usd"]),
                "input_tokens": row["input_tokens"],
                "output_tokens": row["output_tokens"],
                "cached_tokens": row["cached_tokens"],
                "runs": row["runs"],
            }
            for row in out["by_provider"]
        ],
    })
