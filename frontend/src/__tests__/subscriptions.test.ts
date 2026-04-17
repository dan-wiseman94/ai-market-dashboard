import { describe, expect, it, vi } from "vitest";
import { Broker } from "../realtime/subscriptions";

describe("Broker", () => {
  it("fans out messages to subscribers of the same channel", () => {
    const b = new Broker();
    const handler = vi.fn();
    const unsub = b.subscribe("thread.1", handler);

    b.dispatch("thread.1", { event: "text_delta", text: "hi" });
    expect(handler).toHaveBeenCalledWith({ event: "text_delta", text: "hi" });

    unsub();
    b.dispatch("thread.1", { event: "x" });
    expect(handler).toHaveBeenCalledTimes(1);
  });

  it("does not leak messages across channels", () => {
    const b = new Broker();
    const a = vi.fn();
    const z = vi.fn();
    b.subscribe("thread.1", a);
    b.subscribe("thread.2", z);

    b.dispatch("thread.1", { event: "one" });
    expect(a).toHaveBeenCalledTimes(1);
    expect(z).not.toHaveBeenCalled();
  });
});
