import { act, renderHook } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it } from "vitest";
import { useSidebarCollapsed } from "@/hooks/useSidebarCollapsed";

const KEY = "ai-dashboard.sidebar.collapsed";

describe("useSidebarCollapsed", () => {
  beforeEach(() => window.localStorage.clear());
  afterEach(() => window.localStorage.clear());

  it("defaults to expanded (false) when nothing is persisted", () => {
    const { result } = renderHook(() => useSidebarCollapsed());
    expect(result.current[0]).toBe(false);
  });

  it("reads a persisted collapsed state from localStorage on mount", () => {
    // Seed BEFORE mount — the initial value is computed in a lazy useState initializer.
    window.localStorage.setItem(KEY, "1");
    const { result } = renderHook(() => useSidebarCollapsed());
    expect(result.current[0]).toBe(true);
  });

  it("treats any value other than \"1\" as expanded", () => {
    window.localStorage.setItem(KEY, "0");
    const { result } = renderHook(() => useSidebarCollapsed());
    expect(result.current[0]).toBe(false);
  });

  it("toggle flips the state and persists it", () => {
    const { result } = renderHook(() => useSidebarCollapsed());

    act(() => result.current[1]());
    expect(result.current[0]).toBe(true);
    expect(window.localStorage.getItem(KEY)).toBe("1");

    act(() => result.current[1]());
    expect(result.current[0]).toBe(false);
    expect(window.localStorage.getItem(KEY)).toBe("0");
  });

  it("persists the initial state on mount even before any toggle", () => {
    renderHook(() => useSidebarCollapsed());
    expect(window.localStorage.getItem(KEY)).toBe("0");
  });
});
