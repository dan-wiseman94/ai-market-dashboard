import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, it, expect, vi, beforeEach } from "vitest";
import SchedulesPage from "@/pages/SchedulesPage";

const mockCreate = vi.fn(() => Promise.resolve());

vi.mock("@/hooks/useSchedules", () => ({
  useSchedules: () => ({ data: [], isLoading: false }),
  useToggleSchedule: () => ({ mutate: vi.fn() }),
  useDeleteSchedule: () => ({ mutate: vi.fn() }),
  useRunSchedule: () => ({ mutate: vi.fn() }),
  useCreateSchedule: () => ({ mutateAsync: mockCreate, isPending: false }),
}));
vi.mock("@/hooks/useProfiles", () => ({
  useProfiles: () => ({ data: [{ id: 1, name: "P1" }] }),
}));

beforeEach(() => mockCreate.mockClear());

describe("SchedulesPage relative-to-close", () => {
  it("shows the close-offset input only when fire_mode is relative_to_close", async () => {
    const user = userEvent.setup();
    render(<SchedulesPage />);
    await user.click(screen.getByRole("button", { name: /new schedule/i }));
    expect(screen.queryByLabelText(/minutes before close/i)).not.toBeInTheDocument();
    await user.selectOptions(screen.getByLabelText(/fire mode/i), "relative_to_close");
    expect(screen.getByLabelText(/minutes before close/i)).toBeInTheDocument();
  });

  it("submits fire_mode + close_offset_minutes", async () => {
    const user = userEvent.setup();
    render(<SchedulesPage />);
    await user.click(screen.getByRole("button", { name: /new schedule/i }));
    await user.type(screen.getByLabelText(/^name$/i), "eod");
    await user.selectOptions(screen.getByLabelText(/fire mode/i), "relative_to_close");
    await user.click(screen.getByRole("button", { name: /^create$/i }));
    expect(mockCreate).toHaveBeenCalledTimes(1);
    expect(mockCreate).toHaveBeenCalledWith(
      expect.objectContaining({ fire_mode: "relative_to_close", close_offset_minutes: 5 }),
    );
  });
});
