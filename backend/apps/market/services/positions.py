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
    client.get_account_numbers()

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
