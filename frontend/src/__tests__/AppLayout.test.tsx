import { render, screen } from "@testing-library/react";
import { createMemoryRouter, RouterProvider } from "react-router-dom";
import AppLayout from "@/components/layout/AppLayout";

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
