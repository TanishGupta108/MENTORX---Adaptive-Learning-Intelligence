import "@testing-library/jest-dom/vitest";
import { cleanup, configure } from "@testing-library/react";
import { afterEach } from "vitest";

// Vitest runs without globals, so Testing Library can't register its own cleanup.
afterEach(() => cleanup());

// Signed-in screens wait on a chain of mocked requests (refresh, /me, profile, page data) and
// lazy-loaded chunks; on a busy machine the default 1 s for findBy* is too tight.
configure({ asyncUtilTimeout: 5000 });

// Recharts' ResponsiveContainer measures its parent; jsdom has no layout engine.
class ResizeObserverStub {
  observe() {}
  unobserve() {}
  disconnect() {}
}
globalThis.ResizeObserver ??= ResizeObserverStub as unknown as typeof ResizeObserver;
