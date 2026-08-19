"""Anomaly-sweep parameters."""

TOP_K = 3  # max investigations originated per sweep
COOLDOWN_HOURS = 12  # don't re-investigate the same (ticker, anomaly_type) within this window
DAILY_ORIGINATION_CAP = 12  # max DeskEntry investigations per day (cost backstop)

GAP_PCT = 3.0
PCT_CHANGE = 5.0
NEAR_52W_PCT = 2.0

COVERAGE_STALE_DAYS = 14
COVERAGE_MOVE_PCT = 8.0
EARNINGS_WITHIN_DAYS = 3
