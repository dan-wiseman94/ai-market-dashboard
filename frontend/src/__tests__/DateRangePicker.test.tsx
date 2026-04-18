import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { vi, test, expect } from "vitest";
import DateRangePicker from "@/components/costs/DateRangePicker";

test("selecting 'Last 7 days' sets from 7 days ago and to now", async () => {
  const onChange = vi.fn();
  render(<DateRangePicker value={{ from: "", to: "" }} onChange={onChange} />);
  await userEvent.selectOptions(screen.getByLabelText(/range/i), "7d");
  expect(onChange).toHaveBeenCalled();
  const arg = onChange.mock.calls[0][0];
  const fromDate = new Date(arg.from);
  const toDate = new Date(arg.to);
  const days = (toDate.getTime() - fromDate.getTime()) / 86400000;
  expect(Math.round(days)).toBe(7);
});
