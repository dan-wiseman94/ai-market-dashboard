// frontend/src/__tests__/Field.test.tsx
import { render, screen } from "@testing-library/react";
import { describe, it, expect } from "vitest";
import Field from "@/components/settings/Field";

describe("Field", () => {
  it("associates the label with the control via htmlFor/id", () => {
    render(
      <Field label="Daily cap">
        {({ id, describedBy }) => <input id={id} aria-describedby={describedBy} />}
      </Field>,
    );
    // getByLabelText resolves only if label/control are wired correctly
    expect(screen.getByLabelText("Daily cap")).toBeInTheDocument();
  });

  it("renders a hint and wires aria-describedby to it", () => {
    render(
      <Field label="Daily cap" hint="Hard stop.">
        {({ id, describedBy }) => <input id={id} aria-describedby={describedBy} />}
      </Field>,
    );
    const input = screen.getByLabelText("Daily cap");
    const hint = screen.getByText("Hard stop.");
    expect(input.getAttribute("aria-describedby")).toContain(hint.id);
  });

  it("shows the error instead of the hint when present", () => {
    render(
      <Field label="Daily cap" hint="Hard stop." error="Bad value">
        {({ id, describedBy }) => <input id={id} aria-describedby={describedBy} />}
      </Field>,
    );
    expect(screen.getByText("Bad value")).toBeInTheDocument();
    expect(screen.queryByText("Hard stop.")).not.toBeInTheDocument();
  });
});
