import type { DomainEvents, Unsubscribe } from "./types";

type Handler<T> = (payload: T) => void | Promise<void>;

export class TypedEventBus<Events extends object = DomainEvents> {
  private readonly handlers = new Map<keyof Events, Set<Handler<never>>>();

  subscribe<K extends keyof Events>(type: K, handler: Handler<Events[K]>): Unsubscribe {
    const handlers = this.handlers.get(type) ?? new Set();
    handlers.add(handler as Handler<never>);
    this.handlers.set(type, handlers);
    return () => {
      handlers.delete(handler as Handler<never>);
      if (!handlers.size) this.handlers.delete(type);
    };
  }

  publish<K extends keyof Events>(type: K, payload: Events[K]): void {
    for (const handler of [...(this.handlers.get(type) ?? [])]) {
      Promise.resolve(handler(payload as never)).catch(() => {
        // Subscribers are isolated just like the backend's bounded SSE queues.
      });
    }
  }

  clear(): void {
    this.handlers.clear();
  }
}
