import { render, screen } from "@testing-library/react";
import { describe, it, expect } from "vitest";
import SettingsSection from "@/components/settings/SettingsSection";

describe("SettingsSection", () => {
  it("renders a heading with the title and the children", () => {
    render(
      <SettingsSection title="AI Providers" description="Keys and caps.">
        <div>body content</div>
      </SettingsSection>,
    );
    expect(screen.getByRole("heading", { name: "AI Providers" })).toBeInTheDocument();
    expect(screen.getByText("Keys and caps.")).toBeInTheDocument();
    expect(screen.getByText("body content")).toBeInTheDocument();
  });

  it("renders an optional header action", () => {
    render(
      <SettingsSection title="Backups" action={<button>Back up now</button>}>
        <div />
      </SettingsSection>,
    );
    expect(screen.getByRole("button", { name: "Back up now" })).toBeInTheDocument();
  });
});
