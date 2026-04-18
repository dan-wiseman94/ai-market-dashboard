import "@testing-library/jest-dom/vitest";
import { vi } from "vitest";

vi.mock("lightweight-charts", () => ({
  createChart: vi.fn(() => ({
    addCandlestickSeries: vi.fn(() => ({ setData: vi.fn() })),
    timeScale: vi.fn(() => ({ fitContent: vi.fn() })),
    resize: vi.fn(),
    remove: vi.fn(),
  })),
}));

// Polyfill ResizeObserver for recharts ResponsiveContainer in jsdom
if (typeof globalThis.ResizeObserver === "undefined") {
  globalThis.ResizeObserver = class ResizeObserver {
    observe() {}
    unobserve() {}
    disconnect() {}
  };
}
