// eslint-disable-next-line @typescript-eslint/no-explicit-any
type Handler = (msg: any) => void;

export class Broker {
  private subs = new Map<string, Set<Handler>>();

  subscribe(channel: string, h: Handler): () => void {
    let set = this.subs.get(channel);
    if (!set) {
      set = new Set();
      this.subs.set(channel, set);
    }
    set.add(h);
    return () => {
      const s = this.subs.get(channel);
      s?.delete(h);
      if (s && s.size === 0) this.subs.delete(channel);
    };
  }

  // eslint-disable-next-line @typescript-eslint/no-explicit-any
  dispatch(channel: string, msg: any): void {
    this.subs.get(channel)?.forEach((h) => {
      try { h(msg); } catch { /* swallow handler errors */ }
    });
  }

  channels(): string[] {
    return Array.from(this.subs.keys());
  }
}
