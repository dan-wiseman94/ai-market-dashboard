# E2E test suite

Six-lane comprehensive suite. Full design: `docs/superpowers/specs/2026-04-18-e2e-comprehensive-design.md`.

## Lane layout

| Lane     | Dir               | What it tests                               | Run locally          |
|----------|-------------------|---------------------------------------------|----------------------|
| UI       | `e2e/ui/`         | Playwright browser journeys                 | `make e2e-ui`        |
| API      | `e2e/api/`        | httpx contract against DRF endpoints        | `make e2e-api`       |
| WS       | `e2e/ws/`         | Channels WebSocket event assertions         | `make e2e-ws`        |
| Visual   | `e2e/visual/`     | Page-level screenshot diffs                 | `make e2e-visual`    |
| A11y     | `e2e/a11y/`       | axe-core scans per route + keyboard-only    | `make e2e-a11y`      |
| Perf     | `e2e/perf/`       | Lighthouse budgets (prod overlay)           | `make e2e-perf`      |

`make e2e` runs ui/api/ws/visual/a11y together. Perf is separate because it
needs the prod overlay.

## Workflow

```
# First time
make e2e-up                              # build + start stack with overlay

# Iterate
make e2e-one t=ui/test_snapshots_capture_gold.py
HEADED=1 make e2e-one t=ui/test_snapshots_capture_gold.py   # visual debug

# Update visual baselines
make e2e-visual-update
git diff e2e/visual/__screenshots__/

# Tear down
make e2e-down
```

## Troubleshooting

- **"Mocked response" in a non-mock test** — the e2e overlay is still up. Stop it: `make e2e-down`.
- **Visual baseline missing** — first-run creates it. Commit the new PNGs.
- **Perf test fails on LCP** — check `e2e/perf/artifacts/` for the Lighthouse HTML report; budgets live in `e2e/perf/budgets.json`.
- **Flaky UI test** — don't add `@pytest.mark.flaky` without a linked issue. See `tools/flake_audit.py` (Phase 8).
