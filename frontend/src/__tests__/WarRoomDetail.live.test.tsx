import { act, screen, waitFor } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import * as client from "@/api/client";
import WarRoomDetailPage from "@/pages/WarRoomDetailPage";
import { type FakeWebSocketController, installFakeWebSocket, renderWithProviders } from "./testUtils";

vi.mock("react-router-dom", async (orig) => {
  const m = await orig<typeof import("react-router-dom")>();
  return { ...m, useParams: () => ({ id: "7" }) };
});

let fake: FakeWebSocketController;
beforeEach(() => {
  fake = installFakeWebSocket();
});
afterEach(() => {
  fake.restore();
  vi.restoreAllMocks();
});

describe("WarRoomDetailPage — live streaming", () => {
  it("streams persona tokens into the courtroom while the debate is running", async () => {
    vi.spyOn(client, "apiGet").mockResolvedValue({
      id: 7, created_at: "x", subject_kind: "free", subject_label: "NVDA",
      params: {}, verdict: {}, confidence: null, status: "running", error: "",
      thread_id: 5, messages: [],
    });
    renderWithProviders(<WarRoomDetailPage />);

    // Once the running run loads, the page subscribes to its thread channel.
    await waitFor(() => expect(fake.find("/ws/threads/5/")).toBeDefined());
    const sock = fake.find("/ws/threads/5/")!;

    act(() => {
      sock.emitOpen();
      sock.emitMessage({ event: "message_started", message_id: 1, seq: 1 });
      sock.emitMessage({ event: "text_delta", message_id: 1, text: "Capex is ", seq: 2 });
      sock.emitMessage({ event: "text_delta", message_id: 1, text: "durable.", seq: 3 });
    });

    const live = await screen.findByTestId("warroom-live");
    expect(live.textContent).toContain("Capex is durable.");
  });
});
