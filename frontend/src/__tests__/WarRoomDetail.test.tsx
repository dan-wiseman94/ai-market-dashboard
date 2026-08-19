import { screen, waitFor } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

import * as client from "@/api/client";
import WarRoomDetailPage from "@/pages/WarRoomDetailPage";
import { renderWithProviders } from "./testUtils";

vi.mock("react-router-dom", async (orig) => {
  const m = await orig<typeof import("react-router-dom")>();
  return { ...m, useParams: () => ({ id: "1" }) };
});

describe("WarRoomDetailPage", () => {
  it("renders persona columns + verdict", async () => {
    vi.spyOn(client, "apiGet").mockResolvedValue({
      id: 1, created_at: "x", subject_kind: "free", subject_label: "NVDA into earnings",
      params: { structure: "rebuttal" },
      verdict: { verdict: "bull case stronger", confidence: 0.62, strongest_bull: "capex", strongest_bear: "valuation", what_would_change_my_mind: "guidance cut" },
      confidence: 0.62, status: "done", error: "", thread_id: 1,
      messages: [
        { role: "assistant", content: { persona: "bull", text: "AI capex is durable." } },
        { role: "assistant", content: { persona: "bear", text: "Valuation is stretched." } },
        { role: "assistant", content: { persona: "skeptic", text: "Both ignore rates." } },
        { role: "assistant", content: { kind: "warroom_verdict", verdict: "bull case stronger", confidence: 0.62 } },
      ],
    });
    renderWithProviders(<WarRoomDetailPage />);
    await waitFor(() => expect(screen.getByText(/AI capex is durable/)).toBeInTheDocument());
    expect(screen.getByText(/Valuation is stretched/)).toBeInTheDocument();
    expect(screen.getByText(/Both ignore rates/)).toBeInTheDocument();
    expect(screen.getByText(/bull case stronger/)).toBeInTheDocument();
  });
});
