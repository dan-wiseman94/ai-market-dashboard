"""Pure option-chain analytics: P/C ratios, max-pain, IV skew, ATM term structure, dealer GEX.

All functions are defensive:
- Missing/None greeks on a contract → that contract is skipped for metrics that need it.
- Empty input → empty/None result; never raises.

Input contract shape (matches _normalize_contract in chain.py):
    {
        "strike":  str | None,   # formatted float string e.g. "515.00"
        "volume":  int | None,
        "oi":      int | None,
        "delta":   str | None,   # formatted float string e.g. "0.72" or "-0.28"
        "gamma":   str | None,
        "iv":      str | None,   # formatted float string (Schwab's "volatility" field)
        # plus "side": "call"|"put" and "expiry": str  -- added by callers before passing in
    }

GEX sign convention (DOCUMENTED HEURISTIC — not gospel):
    Dealers are assumed to be on the OPPOSITE side of retail options buyers:
    - Retail buys calls  → dealers are short calls → dealers hedge by BUYING delta → sell on down moves
      but from a gamma perspective, dealers are long gamma on calls (positive delta hedge adjustments)
    - Retail buys puts   → dealers are short puts  → dealers hedge by SELLING delta
      from a gamma perspective, dealers are short gamma on puts (negative delta hedge adjustments)
    Therefore: call GEX = +gamma * OI * 100 * spot
               put  GEX = -gamma * OI * 100 * spot
    Total GEX > 0 → dealers tend to dampen volatility (buy dips, sell rips).
    Total GEX < 0 → dealers tend to amplify volatility (sell dips, buy rips).
    The "zero-gamma flip strike" is where total per-strike GEX transitions from positive to negative;
    below this level, dealer hedging is destabilising.
    This is a widely-used heuristic; actual dealer positioning is unobservable.
"""

from __future__ import annotations


def _to_float(v: object) -> float | None:
    """Parse a raw value (str, int, float, None) to float; return None on failure."""
    if v is None or v == "":
        return None
    try:
        return float(v)  # type: ignore[arg-type]
    except (TypeError, ValueError):
        return None


# ---------------------------------------------------------------------------
# Top-level entry point
# ---------------------------------------------------------------------------


def chain_analytics(
    contracts: list[dict],
    *,
    spot: float | None = None,
) -> dict:
    """Compute option-chain analytics from a flat list of per-contract dicts.

    Each dict must have at minimum:
        "side":   "call" | "put"
        "expiry": str          (ISO date, e.g. "2026-04-25")
        "strike": str | None
        "volume": int | None
        "oi":     int | None
        "delta":  str | None
        "gamma":  str | None
        "iv":     str | None

    spot is the underlying price; derived from the contracts' own data by callers when
    not passed explicitly. Required for GEX. If None, GEX totals are None.

    Returns:
    {
        "put_call": {"volume_ratio": float|None, "oi_ratio": float|None},
        "max_pain":  float|None,
        "iv_skew_25d": float|None,
        "term_structure": [{"expiry": str, "atm_iv": float|None}, ...],
        "gex": {
            "total":      float|None,
            "flip_strike": float|None,
            "convention": "dealers long calls / short puts (heuristic)",
        },
    }
    """
    return {
        "put_call": _put_call(contracts),
        "max_pain": _max_pain(contracts),
        "iv_skew_25d": _iv_skew_25d(contracts),
        "term_structure": _term_structure(contracts, spot=spot),
        "gex": _gex(contracts, spot=spot),
    }


# ---------------------------------------------------------------------------
# P/C ratios
# ---------------------------------------------------------------------------


def _put_call(contracts: list[dict]) -> dict:
    call_vol = put_vol = 0.0
    call_oi = put_oi = 0.0
    for c in contracts:
        side = c.get("side")
        vol = _to_float(c.get("volume")) or 0.0
        oi = _to_float(c.get("oi")) or 0.0
        if side == "call":
            call_vol += vol
            call_oi += oi
        elif side == "put":
            put_vol += vol
            put_oi += oi

    vol_ratio = (put_vol / call_vol) if call_vol > 0 else None
    oi_ratio = (put_oi / call_oi) if call_oi > 0 else None
    return {
        "volume_ratio": round(vol_ratio, 4) if vol_ratio is not None else None,
        "oi_ratio": round(oi_ratio, 4) if oi_ratio is not None else None,
    }


# ---------------------------------------------------------------------------
# Max-pain strike
# ---------------------------------------------------------------------------


def _max_pain(contracts: list[dict]) -> float | None:
    """Max-pain strike for the nearest expiry.

    For each candidate strike K, computes total payout to option holders if the
    underlying expires exactly at K:
        sum_calls(max(K - strike_c, 0) * OI_c) + sum_puts(max(strike_p - K, 0) * OI_p)
    Returns the K that minimises this sum.
    """
    # Gather nearest expiry
    expiries = sorted({c.get("expiry") for c in contracts if c.get("expiry")})
    if not expiries:
        return None
    nearest = expiries[0]

    near = [c for c in contracts if c.get("expiry") == nearest]
    if not near:
        return None

    # Collect unique valid strikes
    strikes: list[float] = []
    for c in near:
        s = _to_float(c.get("strike"))
        if s is not None:
            strikes.append(s)
    strikes = sorted(set(strikes))
    if not strikes:
        return None

    min_pain: float | None = None
    min_strike: float | None = None

    for k in strikes:
        total_pain = 0.0
        for c in near:
            s = _to_float(c.get("strike"))
            oi = _to_float(c.get("oi")) or 0.0
            if s is None:
                continue
            side = c.get("side")
            if side == "call":
                total_pain += max(k - s, 0.0) * oi
            elif side == "put":
                total_pain += max(s - k, 0.0) * oi

        if min_pain is None or total_pain < min_pain:
            min_pain = total_pain
            min_strike = k

    return min_strike


# ---------------------------------------------------------------------------
# 25-delta IV skew
# ---------------------------------------------------------------------------


def _iv_skew_25d(contracts: list[dict]) -> float | None:
    """IV(25-delta put) - IV(25-delta call) for the nearest expiry.

    Picks the call contract whose |delta| is closest to 0.25 and the put
    contract whose |delta| is closest to 0.25.  Returns None if either side
    cannot be found.
    """
    expiries = sorted({c.get("expiry") for c in contracts if c.get("expiry")})
    if not expiries:
        return None
    nearest = expiries[0]

    near = [c for c in contracts if c.get("expiry") == nearest]

    calls = [c for c in near if c.get("side") == "call"]
    puts = [c for c in near if c.get("side") == "put"]

    def _best_25d(legs: list[dict]) -> float | None:
        best_delta_diff: float | None = None
        best_iv: float | None = None
        for c in legs:
            delta = _to_float(c.get("delta"))
            iv = _to_float(c.get("iv"))
            if delta is None or iv is None:
                continue
            diff = abs(abs(delta) - 0.25)
            if best_delta_diff is None or diff < best_delta_diff:
                best_delta_diff = diff
                best_iv = iv
        return best_iv

    call_iv = _best_25d(calls)
    put_iv = _best_25d(puts)

    if call_iv is None or put_iv is None:
        return None
    return round(put_iv - call_iv, 4)


# ---------------------------------------------------------------------------
# ATM term structure
# ---------------------------------------------------------------------------


def _term_structure(contracts: list[dict], *, spot: float | None) -> list[dict]:
    """ATM IV per expiry (strike closest to underlying), sorted by expiry.

    Each entry: {"expiry": str, "atm_iv": float | None}.

    When spot is None and no contracts carry an underlying field, atm_iv for
    every expiry will be None.  Callers should supply spot.
    """
    expiries = sorted({c.get("expiry") for c in contracts if c.get("expiry")})
    if not expiries:
        return []

    result = []
    for exp in expiries:
        exp_contracts = [c for c in contracts if c.get("expiry") == exp]
        atm_iv = _atm_iv_for_expiry(exp_contracts, spot=spot)
        result.append({"expiry": exp, "atm_iv": atm_iv})
    return result


def _atm_iv_for_expiry(contracts: list[dict], *, spot: float | None) -> float | None:
    """Return the IV of the contract whose strike is closest to spot.

    Uses calls preferentially (calls + puts at the same strike have very similar
    ATM IV; pick calls to avoid put skew bias at the money).
    If spot is None, returns None.
    """
    if spot is None:
        return None

    calls = [c for c in contracts if c.get("side") == "call"]
    candidates = calls if calls else contracts

    best_dist: float | None = None
    best_iv: float | None = None
    for c in candidates:
        s = _to_float(c.get("strike"))
        iv = _to_float(c.get("iv"))
        if s is None or iv is None:
            continue
        dist = abs(s - spot)
        if best_dist is None or dist < best_dist:
            best_dist = dist
            best_iv = iv
    return best_iv


# ---------------------------------------------------------------------------
# Dealer GEX (gamma exposure)
# ---------------------------------------------------------------------------


def _gex(contracts: list[dict], *, spot: float | None) -> dict:
    """Dealer gamma exposure profile.

    Per contract: gex = +-gamma * OI * 100 * spot
        call: positive (dealers long calls → long gamma)
        put:  negative (dealers short puts → short gamma)

    Returns total GEX and the zero-gamma flip strike (where per-strike GEX
    transitions from positive to negative, using linear interpolation between
    the bracketing strikes).  Both are None when spot is unavailable or no
    contracts have usable gamma.

    See module docstring for the sign-convention heuristic.
    """
    _CONVENTION = "dealers long calls / short puts (heuristic)"

    if spot is None:
        return {"total": None, "flip_strike": None, "convention": _CONVENTION}

    # Accumulate per-strike GEX (all expiries combined — reflects total dealer
    # hedging pressure at each strike level).
    strike_gex: dict[float, float] = {}
    total = 0.0
    has_any = False

    for c in contracts:
        gamma = _to_float(c.get("gamma"))
        oi = _to_float(c.get("oi")) or 0.0
        s = _to_float(c.get("strike"))
        side = c.get("side")
        if gamma is None or s is None or side not in ("call", "put"):
            continue

        raw_gex = gamma * oi * 100.0 * spot
        signed = raw_gex if side == "call" else -raw_gex
        strike_gex[s] = strike_gex.get(s, 0.0) + signed
        total += signed
        has_any = True

    if not has_any:
        return {"total": None, "flip_strike": None, "convention": _CONVENTION}

    flip = _find_flip_strike(strike_gex)
    return {
        "total": round(total, 2),
        "flip_strike": round(flip, 2) if flip is not None else None,
        "convention": _CONVENTION,
    }


def _find_flip_strike(strike_gex: dict[float, float]) -> float | None:
    """Return the strike where cumulative per-strike GEX changes sign.

    Uses linear interpolation between the last positive and first negative
    strike (sorted ascending).  Returns None if no sign change exists.
    """
    strikes = sorted(strike_gex.keys())
    if not strikes:
        return None

    # Walk ascending; find first pair where sign changes from positive to negative.
    for i in range(len(strikes) - 1):
        k0, k1 = strikes[i], strikes[i + 1]
        g0, g1 = strike_gex[k0], strike_gex[k1]
        if g0 >= 0 and g1 < 0:
            # Linear interpolation: 0 = g0 + (g1 - g0) * t, t ∈ [0,1]
            t = g0 / (g0 - g1)
            return k0 + t * (k1 - k0)

    return None
