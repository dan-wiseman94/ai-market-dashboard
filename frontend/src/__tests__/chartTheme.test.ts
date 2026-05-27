import { describe, expect, it } from "vitest";
import { lightweightLayout, rechartsColors } from "@/lib/chartTheme";

describe("chartTheme", () => {
  it("returns distinct lightweight-charts backgrounds per theme", () => {
    expect(lightweightLayout("dark").layout.background.color).not.toBe(
      lightweightLayout("light").layout.background.color,
    );
  });

  it("uses the expected lightweight-charts backgrounds", () => {
    expect(lightweightLayout("dark").layout.background.color.toLowerCase()).toBe("#0a0a0a");
    expect(lightweightLayout("light").layout.background.color.toLowerCase()).toBe("#f5f2ea");
  });

  it("provides distinct recharts colors per theme", () => {
    expect(rechartsColors("dark").tickText).not.toBe(rechartsColors("light").tickText);
    expect(rechartsColors("light").heatmapEmpty).toContain("0,0,0");
    expect(rechartsColors("dark").heatmapEmpty).toContain("255,255,255");
  });
});
