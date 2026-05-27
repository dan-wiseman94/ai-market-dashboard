"""Account positions service."""

from __future__ import annotations

from apps.market import cache
from apps.market.schwab_client import get_schwab_client, schwab_json


def fetch_positions() -> list[dict]:
    return cache.get_or_fetch(
        "market:positions",
        ttl_seconds=cache.ttl_for_kind("positions"),
        fetcher=_fetch_from_schwab,
    )


def _fetch_from_schwab() -> list[dict]:
    client = get_schwab_client()
    # schwab_json raises SchwabAuthError on a 401/403 before we treat the body
    # as a list of accounts — a JSON error object would otherwise yield string
    # keys here and crash on `.get`.
    accounts = schwab_json(client.get_accounts(fields=client.Account.Fields.POSITIONS))

    out: list[dict] = []
    for acct_blob in accounts:
        if not isinstance(acct_blob, dict):
            continue
        for p in acct_blob.get("securitiesAccount", {}).get("positions", []):
            out.append(
                {
                    "ticker": p.get("instrument", {}).get("symbol", ""),
                    "qty": p.get("longQuantity", 0) - p.get("shortQuantity", 0),
                    "avg_cost": p.get("averagePrice"),
                    "mkt_value": p.get("marketValue"),
                    "unrealized_pl": p.get("longOpenProfitLoss") or p.get("shortOpenProfitLoss"),
                    "day_pl": p.get("currentDayProfitLoss"),
                }
            )
    return out
