/**
 * dependency-cruiser — frontend architecture contracts (the FE mirror of the backend's
 * import-linter). Errors gate CI; warnings are advisory. Run: `pnpm depcruise`.
 *
 * Encoded invariants (gating — errors fail CI):
 *   - no-circular: import cycles are forbidden (they break tree-shaking + reasoning).
 *   - api-stays-below-ui: the data layer (src/api) must not import UI (pages/components),
 *     so API clients stay reusable and the dependency arrow points one way (verified true
 *     as of 2026-06-04). This is the FE analogue of "providers are private to apps.ai".
 *
 * Dead-MODULE detection is deliberately left to knip (which does it better — it understands
 * entry points and barrels); depcruise's no-orphans over-warned on test/story-only importers
 * here, so it owns ARCHITECTURE (cycles + layering) and knip owns dead code.
 */
module.exports = {
  forbidden: [
    {
      name: "no-circular",
      severity: "error",
      comment: "Circular imports break tree-shaking and make load order fragile.",
      from: {},
      to: { circular: true },
    },
    {
      name: "api-stays-below-ui",
      severity: "error",
      comment: "Data layer (src/api) must not import UI (src/pages, src/components).",
      from: { path: "^src/api/" },
      to: { path: "^src/(pages|components)/" },
    },
  ],
  options: {
    doNotFollow: { path: "node_modules" },
    tsConfig: { fileName: "tsconfig.json" },
    tsPreCompilationDeps: true,
    exclude: { path: "(^|/)__tests__/|\\.test\\.tsx?$|\\.stories\\.tsx?$" },
    enhancedResolveOptions: { exportsFields: ["exports"], conditionNames: ["import", "require"] },
  },
};
