"""Pattern rules that guess a market key from a bare ticker string.

Precedence inside calendar_for(): explicit override > classify() > default.
classify() itself is ordered: futures > crypto > international suffix > default.
"""

from __future__ import annotations

# Known CME future roots (index/commodity). Extend as needed.
_CME_ROOTS = {"ES", "NQ", "RTY", "YM", "CL", "GC", "SI", "ZB", "ZN", "ZF", "NG", "HG"}
_CFE_ROOTS = {"VX"}
_CRYPTO_BASES = {"BTC", "ETH", "SOL", "XRP", "DOGE", "ADA", "LTC", "BCH"}
_CRYPTO_QUOTE_SUFFIXES = ("-USD", "-USDT", "-USDC", "-EUR")


def classify(symbol: str) -> str:
    s = (symbol or "").strip().upper()
    if not s:
        return "us_equity"

    root = s[1:] if s.startswith("/") else s

    # Futures (leading slash or a known root)
    if s.startswith("/") or root in _CME_ROOTS or root in _CFE_ROOTS:
        if root in _CFE_ROOTS:
            return "cfe_futures"
        return "cme_futures"

    # Crypto (quote-currency suffix or a known base symbol)
    if any(s.endswith(suf) for suf in _CRYPTO_QUOTE_SUFFIXES):
        return "crypto"
    if s in _CRYPTO_BASES:
        return "crypto"

    # International equity suffixes
    if s.endswith(".L"):
        return "lse"
    if s.endswith(".T"):
        return "jpx"

    return "us_equity"
