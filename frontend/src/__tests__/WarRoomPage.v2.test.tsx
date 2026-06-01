import { screen, waitFor } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

import * as client from "@/api/client";
import WarRoomPage from "@/pages/WarRoomPage";
import { renderWithProviders } from "./testUtils";

describe("WarRoomPage v2 controls", () => {
  it("renders voice-mode + grounding controls", async () => {
    vi.spyOn(client, "apiGet").mockResolvedValue([]);
    renderWithProviders(<WarRoomPage />);
    await waitFor(() => expect(screen.getByText(/War Room/)).toBeInTheDocument());
    // a multi-provider option + a grounded toggle are present
    expect(screen.getByText(/multi-provider/i)).toBeInTheDocument();
    expect(screen.getByText(/grounded/i)).toBeInTheDocument();
  });
});
