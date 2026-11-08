import { vi } from "vitest";

type Handler = (body: unknown, url: URL) => { status?: number; body?: unknown } | undefined;

/**
 * Replace fetch with a router: keys are "METHOD /path" (path without /api/v1 and query).
 * Unmatched requests fail the test loudly. Returns the list of calls for assertions.
 */
export function mockApi(routes: Record<string, Handler | { status?: number; body?: unknown }>) {
  const calls: { method: string; path: string; body: unknown; auth: string | null }[] = [];
  const fetchMock = vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
    const url = new URL(String(input), "http://localhost");
    const method = (init?.method ?? "GET").toUpperCase();
    const path = url.pathname.replace(/^\/api\/v1/, "");
    const body = init?.body ? JSON.parse(String(init.body)) : undefined;
    const headers = new Headers(init?.headers);
    calls.push({ method, path, body, auth: headers.get("Authorization") });
    const route = routes[`${method} ${path}`];
    if (!route) throw new Error(`Unmocked request: ${method} ${path}`);
    const res = typeof route === "function" ? route(body, url) ?? {} : route;
    const status = res.status ?? 200;
    return new Response(status === 204 ? null : JSON.stringify(res.body ?? {}), {
      status,
      headers: { "Content-Type": "application/json" },
    });
  });
  vi.stubGlobal("fetch", fetchMock);
  return calls;
}

export const user = {
  id: "u1",
  email: "asha@example.com",
  full_name: "Asha Rao",
  role: "student",
  daily_goal: 10,
  timezone: "Asia/Kolkata",
  consent_research: false,
  created_at: "2026-11-08T10:00:00Z",
  enrolled_subjects: ["ML"],
};

export const loggedIn = {
  "POST /auth/refresh": { body: { access_token: "tok", expires_in: 1800 } },
  "GET /me": { body: user },
};
