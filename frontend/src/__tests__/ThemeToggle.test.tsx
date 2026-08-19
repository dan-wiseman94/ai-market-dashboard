import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";
import type { ReactNode } from "react";
import ThemeToggle from "@/components/ThemeToggle";
import { ThemeProvider } from "@/hooks/useTheme";

beforeEach(() => {
  localStorage.clear();
  document.documentElement.className = "dark";
  vi.stubGlobal(
    "matchMedia",
    vi.fn().mockReturnValue({
      matches: true,
      media: "",
      onchange: null,
      addEventListener: () => {},
      removeEventListener: () => {},
      addListener: () => {},
      removeListener: () => {},
      dispatchEvent: () => false,
    }),
  );
});

const wrap = (ui: ReactNode) => render(<ThemeProvider>{ui}</ThemeProvider>);

describe("ThemeToggle", () => {
  it("renders an accessible label reflecting the preference", () => {
    wrap(<ThemeToggle />);
    const btn = screen.getByTestId("theme-toggle");
    expect(btn).toHaveAttribute("data-preference", "system");
    expect(btn.getAttribute("aria-label")).toMatch(/system/i);
  });

  it("cycles the preference on click", async () => {
    const user = userEvent.setup();
    wrap(<ThemeToggle />);
    const btn = screen.getByTestId("theme-toggle");
    await user.click(btn);
    expect(btn).toHaveAttribute("data-preference", "light");
    await user.click(btn);
    expect(btn).toHaveAttribute("data-preference", "dark");
    await user.click(btn);
    expect(btn).toHaveAttribute("data-preference", "system");
  });
});
