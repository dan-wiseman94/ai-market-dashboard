import { describe, expect, it, vi } from "vitest";
import { Broker } from "../realtime/subscriptions";

describe("Broker", () => {
  it("delivers messages to all subscribers of a channel and stops after unsubscribe", () => {
    const broker = new Broker();
    const handler = vi.fn();
    const unsubscribe = broker.subscribe("thread.1", handler);

    broker.dispatch("thread.1", { event: "text_delta", text: "hi" });
    expect(handler).toHaveBeenCalledWith({ event: "text_delta", text: "hi" });

    unsubscribe();
    broker.dispatch("thread.1", { event: "x" });
    expect(handler).toHaveBeenCalledTimes(1);
  });

  it("isolates subscribers across channels", () => {
    const broker = new Broker();
    const onThread1 = vi.fn();
    const onThread2 = vi.fn();
    broker.subscribe("thread.1", onThread1);
    broker.subscribe("thread.2", onThread2);

    broker.dispatch("thread.1", { event: "one" });
    expect(onThread1).toHaveBeenCalledTimes(1);
    expect(onThread2).not.toHaveBeenCalled();
  });
});
