import { isValidElement } from "react";
import { describe, expect, it } from "vitest";
import { matchRoutes } from "react-router-dom";
import { router } from "@/router";
import { SHORTCUTS } from "@/hooks/useKeyboardShortcuts";
import PortfolioPage from "@/pages/PortfolioPage";
import FeaturesSettings from "@/pages/settings/FeaturesSettings";
import ProvidersSettings from "@/pages/settings/ProvidersSettings";
import PredictionsPage from "@/pages/PredictionsPage";
import LessonsPage from "@/pages/LessonsPage";
import CoverageIndexPage from "@/pages/CoverageIndexPage";
import CoveragePage from "@/pages/CoveragePage";

/**
 * These assertions go through `matchRoutes` rather than poking at the children
 * array, so they exercise react-router's own ranking. That is the only way to
 * prove `/coverage` and `/coverage/:ticker` coexist, and that adding a
 * `features` child before the index route did not steal `/settings`.
 */
function leafRoute(path: string) {
  const matches = matchRoutes(router.routes, path);
  return matches?.at(-1)?.route;
}

function componentAt(path: string): unknown {
  const el = leafRoute(path)?.element;
  return isValidElement(el) ? el.type : undefined;
}

function crumbAt(path: string): unknown {
  const handle = leafRoute(path)?.handle as { crumb?: unknown } | undefined;
  return handle?.crumb;
}

describe("router", () => {
  it("registers the /portfolio route -> PortfolioPage (SideNav links to it)", () => {
    expect(componentAt("/portfolio")).toBe(PortfolioPage);
  });

  it.each([
    ["/predictions", PredictionsPage, "Predictions"],
    ["/lessons", LessonsPage, "Lessons"],
    ["/coverage", CoverageIndexPage, "Coverage"],
    ["/settings/features", FeaturesSettings, "Features"],
  ])("resolves %s with its page and breadcrumb", (path, page, crumb) => {
    expect(componentAt(path)).toBe(page);
    expect(crumbAt(path)).toBe(crumb);
  });

  it("keeps /settings on the providers index even though features is listed first", () => {
    expect(componentAt("/settings")).toBe(ProvidersSettings);
  });

  it("resolves both the coverage index and the per-ticker detail", () => {
    expect(componentAt("/coverage")).toBe(CoverageIndexPage);
    expect(componentAt("/coverage/NVDA")).toBe(CoveragePage);
  });

  it("every g-chord destination is a real route", () => {
    for (const [key, { path }] of Object.entries(SHORTCUTS)) {
      expect(matchRoutes(router.routes, path), `g ${key} -> ${path}`).not.toBeNull();
    }
  });
});
