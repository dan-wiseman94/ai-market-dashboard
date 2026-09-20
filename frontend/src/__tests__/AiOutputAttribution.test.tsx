import { render, screen } from "@testing-library/react";
import { describe, it, expect, vi } from "vitest";
import { PostMortemCard } from "@/pages/thesis-detail/PostMortemCard";
import type { PostMortem } from "@/api/thesis";

vi.mock("html2canvas", () => ({
  default: vi.fn(() => Promise.resolve({ toDataURL: () => "data:image/png;base64,x" })),
}));

const PM = (report: PostMortem["report"]): PostMortem => ({
  id: 1,
  horizon_days: 30,
  due_at: "2026-09-01T00:00:00Z",
  status: "done",
  forward_return_pct: 2.1,
  verdict: "correct",
  report,
  message_id: null,
  created_at: "2026-08-01T00:00:00Z",
  completed_at: "2026-09-01T00:00:00Z",
});

describe("PostMortemCard attribution", () => {
  it("names the provider that wrote the narrative", () => {
    render(
      <PostMortemCard
        pm={PM({
          summary: "s",
          what_worked: [],
          what_missed: [],
          lessons: [],
          would_repeat: true,
          ai: { provider: "openai", model: "gpt-5.6-sol" },
        })}
      />,
    );
    expect(screen.getByTestId("ai-attribution").textContent).toBe("OpenAI · gpt-5.6-sol");
  });

  it("stays silent for a report written before the stamp existed", () => {
    render(
      <PostMortemCard
        pm={PM({
          summary: "s",
          what_worked: [],
          what_missed: [],
          lessons: [],
          would_repeat: true,
        })}
      />,
    );
    expect(screen.queryByTestId("ai-attribution")).not.toBeInTheDocument();
  });
});
