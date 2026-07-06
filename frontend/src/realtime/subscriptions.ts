type Handler = (msg: unknown) => void;

export class Broker {
  private subs = new Map<string, Set<Handler>>();

  subscribe(channel: string, handler: Handler): () => void {
    let set = this.subs.get(channel);
    if (!set) {
      set = new Set();
      this.subs.set(channel, set);
    }
    set.add(handler);
    return () => {
      const current = this.subs.get(channel);
      if (!current) return;
      current.delete(handler);
      if (current.size === 0) this.subs.delete(channel);
    };
  }

  dispatch(channel: string, msg: unknown): void {
    this.subs.get(channel)?.forEach((handler) => {
      try {
        handler(msg);
      } catch {
        // isolate handler failures so other subscribers still receive the message
      }
    });
  }

  channels(): string[] {
    return Array.from(this.subs.keys());
  }
}
