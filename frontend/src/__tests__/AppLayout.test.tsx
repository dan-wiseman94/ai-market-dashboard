import { render, screen } from "@testing-library/react";
import { createMemoryRouter, RouterProvider } from "react-router-dom";
import AppLayout from "@/components/layout/AppLayout";
import { beforeEach } from "vitest";
import userEvent from "@testing-library/user-event";

test("AppLayout renders Outlet children", () => {
  const router = createMemoryRouter(
    [{ path: "/", element: <AppLayout />, children: [
      { index: true, element: <div>child-page</div> },
    ]}],
    { initialEntries: ["/"] },
  );
  render(<RouterProvider router={router} />);
  expect(screen.getByText("child-page")).toBeInTheDocument();
});

test("TopNav renders primary route links", () => {
  const router = createMemoryRouter(
    [{ path: "/", element: <AppLayout />, children: [{ index: true, element: <div>x</div> }] }],
    { initialEntries: ["/"] },
  );
  render(<RouterProvider router={router} />);
  expect(screen.getByRole("link", { name: /dashboard/i })).toHaveAttribute("href", "/");
  expect(screen.getByRole("link", { name: /snapshot/i })).toHaveAttribute("href", "/snapshot");
  expect(screen.getByRole("link", { name: /threads/i })).toHaveAttribute("href", "/threads");
  expect(screen.getByRole("link", { name: /triggers/i })).toHaveAttribute("href", "/triggers");
  expect(screen.getByRole("link", { name: /schedules/i })).toHaveAttribute("href", "/schedules");
  expect(screen.getByRole("link", { name: /costs/i })).toHaveAttribute("href", "/costs");
});

beforeEach(() => localStorage.clear());

test("SideNav toggles and persists collapsed state", async () => {
  const router = createMemoryRouter(
    [{ path: "/", element: <AppLayout />, children: [{ index: true, element: <div>x</div> }] }],
    { initialEntries: ["/"] },
  );
  const { unmount } = render(<RouterProvider router={router} />);
  const toggle = screen.getByRole("button", { name: /toggle sidebar/i });
  expect(screen.getByText("Trading")).toBeVisible();

  await userEvent.click(toggle);
  expect(localStorage.getItem("ai-dashboard.sidebar.collapsed")).toBe("1");
  expect(screen.queryByText("Trading")).not.toBeInTheDocument();

  unmount();
  render(<RouterProvider router={router} />);
  expect(screen.queryByText("Trading")).not.toBeInTheDocument();
});
