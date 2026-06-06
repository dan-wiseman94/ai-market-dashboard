import { isValidElement } from "react";
import { describe, expect, it } from "vitest";
import { router } from "@/router";
import PortfolioPage from "@/pages/PortfolioPage";

describe("router", () => {
  it("registers the /portfolio route -> PortfolioPage (SideNav links to it)", () => {
    const root = router.routes.find((r) => r.path === "/");
    const portfolio = root?.children?.find((c) => c.path === "portfolio");
    expect(portfolio).toBeDefined();
    expect(isValidElement(portfolio!.element) && portfolio!.element.type).toBe(PortfolioPage);
  });
});
