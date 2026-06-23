# Themes / Narrative Tracker — Design

**Written 2026-06-22.** Feature #18. Group tickers into named narratives and track
each narrative's health (participation, leadership, relative strength). Reasons at
the theme level vs flat watchlists.

## Model — apps.market.Theme
`name` (unique), `tickers` (JSONField list, upper-cased on save), `note` (blank),
`created_at`/`updated_at`. In `market` (health is OHLCBar-driven, reuses returns.py).

## Health — market/services/themes.py::theme_health(theme, *, window_days=20)
From OHLCBar via returns.trading_day_forward_returns (batched, split-correct):
- breadth = share of members with positive return over the window,
- leadership = best & worst member,
- relative_strength = theme mean return − SPX return,
- members = per-ticker return + above/below-theme,
- coverage honest (no-price members excluded; null metrics when < 2 priced members).
Equal-weight (YAGNI; conviction/position weighting deferred).

## API
ThemeViewSet (CRUD) at /api/themes/ + GET /api/themes/<id>/health/?window_days=.

## FE
/themes page: list + create (name + comma tickers) + a health card per theme
(breadth bar, leader/laggard, RS-vs-SPX, member list). Nav + a free `g` shortcut.

## Tests
health (hand-checkable breadth + RS vs SPX, coverage-honesty), CRUD, FE vitest.

## Out of scope
market-cap/conviction weighting, per-theme auto-observe, AI narrative synthesis.
