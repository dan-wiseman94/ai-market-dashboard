"""Book Risk X-Ray thresholds — single source of truth, tunable later."""

DEFAULT_CONVICTION = 3  # for a Position with no linked thesis conviction

# Concentration
TOP_N = 3

# Correlation clustering
CORR_WINDOW = 60  # trading days of daily returns
CORR_MIN_BARS = 30  # min overlapping returns to correlate
CORR_THRESHOLD = 0.7  # pairwise Pearson >= this joins a cluster

# Proximity-to-invalidation: a thesis within this % of its stop is "near"
NEAR_INVALIDATION_PCT = 5.0

# Deterioration alert (vs prior snapshot)
HHI_ALERT_DELTA = 0.10
