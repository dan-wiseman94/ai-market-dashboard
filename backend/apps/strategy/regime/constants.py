"""Regime classifier thresholds — single source of truth, tunable later."""

VIX_LOW = 14.0
VIX_ELEVATED = 20.0
VIX_STRESS = 30.0
VIX_PERCENTILE_WINDOW = 252  # trading days of $VIX history for the percentile
# When VIX sits at/above this percentile of its own trailing window it is "extreme
# relative to its own regime" — classify_volatility escalates the absolute label one
# notch (Low->Normal, Normal->Elevated), capped at Elevated. Top-decile by default.
VIX_PERCENTILE_ELEVATED = 0.90

# Trend ($SPX moving averages)
MA_FAST = 50
MA_SLOW = 200

# Breadth (advance/decline ratio + TRIN)
BREADTH_BROAD = 0.60
BREADTH_NARROW = 0.40
TRIN_DETERIORATING = 2.0

# Leadership (offensive vs defensive sector ETF N-day return spread, pct points)
OFFENSIVE_ETFS = ["XLK", "XLY", "XLC"]
DEFENSIVE_ETFS = ["XLU", "XLP", "XLV"]
LEADERSHIP_SPREAD = 1.0
SECTOR_RETURN_WINDOW = 20  # trading days

COMPOSITE_RISK_ON = 2
COMPOSITE_RISK_OFF = -2

UNKNOWN = "Unknown"
