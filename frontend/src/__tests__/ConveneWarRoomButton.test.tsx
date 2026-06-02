import { fireEvent, screen, waitFor } from "@testing-library/react";
import { afterEach, describe, expect, it } from "vitest";

import { ConveneWarRoomButton } from "@/components/ConveneWarRoomButton";
import { LocationProbe, mockApi, renderWithProviders } from "./testUtils";

describe("ConveneWarRoomButton", () => {
  let restore: (() => void) | null = null;
  afterEach(() => {
    restore?.();
    restore = null;
  });

  it("convenes with the subject id and navigates to the new run", async () => {
    let path = "";
    const m = mockApi({ "POST /api/warroom/runs/convene/": { id: 9 } });
    restore = m.restore;
    renderWithProviders(<div />, {
      initialEntries: ["/"],
      routes: [
        {
          path: "/",
          element: (
            <>
              <ConveneWarRoomButton subject={{ coverage_note_id: 4 }} />
              <LocationProbe onChange={(p) => (path = p)} />
            </>
          ),
        },
        { path: "/warroom/:id", element: <LocationProbe onChange={(p) => (path = p)} /> },
      ],
    });

    fireEvent.click(screen.getByRole("button", { name: /Convene War Room/i }));

    await waitFor(() => expect(path).toBe("/warroom/9"));
    const post = m.calls.find((c) => c.url.includes("/convene/"));
    expect(post!.body).toMatchObject({ coverage_note_id: 4 });
  });
});
