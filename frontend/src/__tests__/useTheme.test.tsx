import { act, renderHook } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import type { ReactNode } from "react";
import { ThemeProvider, useTheme } from "@/hooks/useTheme";

function mockMatchMedia(dark: boolean) {
  const listeners = new Set<(e: MediaQueryListEvent) => void>();
  const mql = {
    matches: dark,
    media: "(prefers-color-scheme: dark)",
    onchange: null,
    addEventListener: (_: string, cb: (e: MediaQueryListEvent) => void) => listeners.add(cb),
    removeEventListener: (_: string, cb: (e: MediaQueryListEvent) => void) => listeners.delete(cb),
    addListener: (cb: (e: MediaQueryListEvent) => void) => listeners.add(cb),
    removeListener: (cb: (e: MediaQueryListEvent) => void) => listeners.delete(cb),
    dispatchEvent: () => false,
    _emit(next: boolean) {
      this.matches = next;
      listeners.forEach((cb) => cb({ matches: next } as MediaQueryListEvent));
    },
  };
  vi.stubGlobal("matchMedia", vi.fn().mockReturnValue(mql));
  return mql;
}

const wrapper = ({ children }: { children: ReactNode }) => <ThemeProvider>{children}</ThemeProvider>;

beforeEach(() => {
  localStorage.clear();
  document.documentElement.className = "dark";
});
afterEach(() => vi.unstubAllGlobals());

describe("useTheme", () => {
  it("defaults to system and resolves dark from the OS", () => {
    mockMatchMedia(true);
    const { result } = renderHook(() => useTheme(), { wrapper });
    expect(result.current.preference).toBe("system");
    expect(result.current.resolved).toBe("dark");
    expect(document.documentElement.classList.contains("dark")).toBe(true);
  });

  it("resolves system -> light when the OS prefers light", () => {
    mockMatchMedia(false);
    const { result } = renderHook(() => useTheme(), { wrapper });
    expect(result.current.resolved).toBe("light");
    expect(document.documentElement.classList.contains("light")).toBe(true);
  });

  it("persists an explicit preference and applies the class", () => {
    mockMatchMedia(true);
    const { result } = renderHook(() => useTheme(), { wrapper });
    act(() => result.current.setPreference("light"));
    expect(result.current.resolved).toBe("light");
    expect(localStorage.getItem("ai-dashboard.theme")).toBe("light");
    expect(document.documentElement.classList.contains("light")).toBe(true);
  });

  it("ignores OS changes when an explicit preference is set", () => {
    const mql = mockMatchMedia(true);
    const { result } = renderHook(() => useTheme(), { wrapper });
    act(() => result.current.setPreference("light"));
    act(() => mql._emit(true));
    expect(result.current.resolved).toBe("light");
  });

  it("follows OS changes while in system mode", () => {
    const mql = mockMatchMedia(true);
    const { result } = renderHook(() => useTheme(), { wrapper });
    expect(result.current.resolved).toBe("dark");
    act(() => mql._emit(false));
    expect(result.current.resolved).toBe("light");
  });

  it("cycles light -> dark -> system -> light", () => {
    mockMatchMedia(true);
    const { result } = renderHook(() => useTheme(), { wrapper });
    act(() => result.current.setPreference("light"));
    act(() => result.current.cycle());
    expect(result.current.preference).toBe("dark");
    act(() => result.current.cycle());
    expect(result.current.preference).toBe("system");
    act(() => result.current.cycle());
    expect(result.current.preference).toBe("light");
  });

  it("reads a stored preference on init", () => {
    mockMatchMedia(true);
    localStorage.setItem("ai-dashboard.theme", "light");
    const { result } = renderHook(() => useTheme(), { wrapper });
    expect(result.current.preference).toBe("light");
    expect(result.current.resolved).toBe("light");
  });
});
