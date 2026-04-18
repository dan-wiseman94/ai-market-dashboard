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
