from __future__ import annotations

from datetime import UTC, datetime, timedelta
from decimal import Decimal

from django.http import HttpRequest, HttpResponse, JsonResponse, StreamingHttpResponse
from django.views.decorators.http import require_GET

from apps.costs import services


def _parse_range(request: HttpRequest) -> tuple[datetime, datetime]:
    now = datetime.now(tz=UTC)
    end_q = request.GET.get("to")
    start_q = request.GET.get("from")
    # Django's query-string parser decodes '+' as a space; restore it so that
    # timezone offsets like '+00:00' survive fromisoformat().
    end = datetime.fromisoformat(end_q.replace(" ", "+")) if end_q else now
    start = datetime.fromisoformat(start_q.replace(" ", "+")) if start_q else (end - timedelta(days=30))
    return start, end


def _dec(v) -> str:
    """Serialize a Decimal to a compact fixed-point string.

    Strips insignificant trailing zeros (beyond 2 decimal places) so that
    model-field values like Decimal('10.00') round-trip as '10.00', and
    SQL-aggregated values like Decimal('0.050000') serialize as '0.05'.
    Always keeps at least 2 decimal places.
    """
    d = v if v is not None else Decimal("0")
    if not isinstance(d, Decimal):
        d = Decimal(str(d))
    s = format(d, "f")  # plain fixed-point, no scientific notation
    if "." in s:
        integer, frac = s.split(".")
        frac = frac.rstrip("0").ljust(2, "0")  # min 2 decimal places
        return f"{integer}.{frac}"
    return s + ".00"


def _dec4(v) -> str:
    """Serialize a Decimal to exactly 4 decimal places.

    Used for aggregated cost fields where Django's Sum() returns 6-place
    Decimals and the API contract specifies 4-place strings.
    """
    d = v if v is not None else Decimal("0")
    if not isinstance(d, Decimal):
        d = Decimal(str(d))
    return str(d.quantize(Decimal("0.0001")))


@require_GET
def costs_today(_request: HttpRequest) -> JsonResponse:
    out = services.cost_breakdown_today()
    return JsonResponse({
        "total_usd": str(out["total_usd"]),
        "by_provider": [
            {**row, "cost_usd": str(row["cost_usd"])}
            for row in out["by_provider"]
        ],
    })


@require_GET
def costs_summary(request: HttpRequest) -> JsonResponse:
    start, end = _parse_range(request)
    out = services.summary(start=start, end=end)
    return JsonResponse({
        "total": _dec4(out["total"]),
        "by_provider": [{**r, "cost_usd": _dec4(r["cost_usd"])} for r in out["by_provider"]],
        "by_model": [{**r, "cost_usd": _dec4(r["cost_usd"])} for r in out["by_model"]],
        "by_thread": [{**r, "cost_usd": _dec4(r["cost_usd"])} for r in out["by_thread"]],
        "daily": [{**r, "cost_usd": _dec4(r["cost_usd"])} for r in out["daily"]],
    })


@require_GET
def costs_caps(_request: HttpRequest) -> JsonResponse:
    out = services.caps()
    out_json = [
        {
            "provider": row["provider"],
            "daily": {
                "cap": _dec(row["daily"]["cap"]),
                "spent": _dec(row["daily"]["spent"]),
                "pct": row["daily"]["pct"],
            },
            "monthly": (
                {"cap": _dec(row["monthly"]["cap"]),
                 "spent": _dec(row["monthly"]["spent"]),
                 "pct": row["monthly"]["pct"]}
                if row["monthly"] else None
            ),
        }
        for row in out
    ]
    return JsonResponse(out_json, safe=False)


@require_GET
def costs_snapshot_breakdown(_request: HttpRequest, snapshot_id: int) -> JsonResponse:
    out = services.snapshot_breakdown(snapshot_id)
    return JsonResponse(
        [{**r, "cost_share_usd": _dec(r["cost_share_usd"])} for r in out],
        safe=False,
    )


@require_GET
def costs_export_csv(request: HttpRequest) -> HttpResponse:
    import csv
    import io

    start, end = _parse_range(request)
    rows = services.csv_rows(start=start, end=end)

    def stream():
        buf = io.StringIO()
        writer = csv.writer(buf)
        for row in rows:
            writer.writerow(row)
            yield buf.getvalue()
            buf.seek(0); buf.truncate(0)

    filename = f"ai-dashboard-costs-{start.strftime('%Y%m%d')}-{end.strftime('%Y%m%d')}.csv"
    resp = StreamingHttpResponse(stream(), content_type="text/csv")
    resp["Content-Disposition"] = f'attachment; filename="{filename}"'
    return resp
