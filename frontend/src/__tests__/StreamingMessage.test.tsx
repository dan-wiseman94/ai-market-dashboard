import { render, screen } from "@testing-library/react";
import { describe, it, expect } from "vitest";
import StreamingMessage from "@/components/StreamingMessage";

describe("StreamingMessage", () => {
  it("user role shows You eyebrow and plain text body", () => {
    render(<StreamingMessage role="user" text="Hello world" />);
    expect(screen.getByText("You")).toBeInTheDocument();
    expect(screen.getByText("Hello world")).toBeInTheDocument();
  });

  it("user role with empty text shows (empty) placeholder", () => {
    render(<StreamingMessage role="user" text="" />);
    expect(screen.getByText("(empty)")).toBeInTheDocument();
  });

  it("assistant role with text renders the text content", () => {
    render(<StreamingMessage role="assistant" text="Market looks bullish" />);
    expect(screen.getByText("Market looks bullish")).toBeInTheDocument();
  });

  it("assistant role with provider shows capitalized provider name", () => {
    render(
      <StreamingMessage role="assistant" text="Hello" provider="openai" />,
    );
    expect(screen.getByText(/Openai/)).toBeInTheDocument();
  });

  it("assistant with no provider shows Assistant placeholder", () => {
    render(<StreamingMessage role="assistant" text="Hello" />);
    expect(screen.getByText("Assistant")).toBeInTheDocument();
  });

  it("assistant with status=streaming shows ledger-pulse element", () => {
    const { container } = render(
      <StreamingMessage role="assistant" text="thinking" status="streaming" />,
    );
    const pulseEl = container.querySelector(".ledger-pulse");
    expect(pulseEl).not.toBeNull();
  });

  it("assistant with cost prop shows formatted cost pill", () => {
    render(
      <StreamingMessage role="assistant" text="Done" cost="0.0042" />,
    );
    expect(screen.getByText("$0.0042")).toBeInTheDocument();
  });

  it("assistant with bare=true omits ledger-surface class from inner div", () => {
    const { container } = render(
      <StreamingMessage role="assistant" text="Done" bare={true} />,
    );
    const inner = container.querySelector(".ledger-surface");
    expect(inner).toBeNull();
  });
});
