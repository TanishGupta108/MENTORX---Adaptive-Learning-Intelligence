import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { mockApi } from "../test/mockApi";
import { api, ApiError, setAccessToken, setSessionExpiredHandler } from "./client";

beforeEach(() => setAccessToken("old"));
afterEach(() => {
  vi.unstubAllGlobals();
  setSessionExpiredHandler(null);
});

describe("api client", () => {
  it("sends the access token and parses JSON", async () => {
    const calls = mockApi({ "GET /me": { body: { id: "u1" } } });
    expect(await api.get("/me")).toEqual({ id: "u1" });
    expect(calls[0]!.auth).toBe("Bearer old");
  });

  it("refreshes once on 401 and retries with the new token", async () => {
    let n = 0;
    const calls = mockApi({
      "GET /me": () => (n++ === 0 ? { status: 401 } : { body: { ok: true } }),
      "POST /auth/refresh": { body: { access_token: "new", expires_in: 1800 } },
    });
    expect(await api.get("/me")).toEqual({ ok: true });
    expect(calls.map((c) => `${c.method} ${c.path}`)).toEqual([
      "GET /me",
      "POST /auth/refresh",
      "GET /me",
    ]);
    expect(calls[2]!.auth).toBe("Bearer new");
  });

  it("shares one refresh between concurrent requests", async () => {
    const seen: Record<string, number> = {};
    const calls = mockApi({
      "GET /a": () => ((seen.a = (seen.a ?? 0) + 1) === 1 ? { status: 401 } : { body: 1 }),
      "GET /b": () => ((seen.b = (seen.b ?? 0) + 1) === 1 ? { status: 401 } : { body: 2 }),
      "POST /auth/refresh": { body: { access_token: "new", expires_in: 1800 } },
    });
    expect(await Promise.all([api.get("/a"), api.get("/b")])).toEqual([1, 2]);
    expect(calls.filter((c) => c.path === "/auth/refresh")).toHaveLength(1);
  });

  it("reports an expired session when refresh fails", async () => {
    const expired = vi.fn();
    setSessionExpiredHandler(expired);
    mockApi({ "GET /me": { status: 401 }, "POST /auth/refresh": { status: 401 } });
    await expect(api.get("/me")).rejects.toBeInstanceOf(ApiError);
    expect(expired).toHaveBeenCalledOnce();
  });

  it("turns the backend's error shape into ApiError with field messages", async () => {
    mockApi({
      "POST /auth/register": {
        status: 422,
        body: {
          error: {
            code: "validation_error",
            message: "Some fields are invalid.",
            request_id: "r1",
            fields: [{ field: "password", message: "Value error, too short" }],
          },
        },
      },
    });
    const err = (await api.post("/auth/register", {}, { noRetry: true }).catch((e) => e)) as ApiError;
    expect(err.code).toBe("validation_error");
    expect(err.requestId).toBe("r1");
    expect(err.fields).toEqual({ password: "too short" });
  });

  it("hides server internals on a real 500", async () => {
    mockApi({ "GET /me": { status: 500, body: { error: { code: "internal", message: "Traceback…" } } } });
    const err = (await api.get("/me").catch((e) => e)) as ApiError;
    expect(err.message).toBe("Something went wrong on our side. Please try again.");
  });

  it("keeps the AI tutor's own 503 message", async () => {
    mockApi({ "POST /api/v2/ai/explain": { status: 503, body: { error: { code: "ai_unavailable", message: "The AI tutor is busy. Please try again." } } } });
    const err = (await api.post("/api/v2/ai/explain", {}).catch((e) => e)) as ApiError;
    expect(err.code).toBe("ai_unavailable");
    expect(err.message).toBe("The AI tutor is busy. Please try again.");
  });

  it("explains a proxy's non-JSON 502/504 as the server waking up", async () => {
    vi.stubGlobal("fetch", vi.fn(async () => new Response("<html>Bad gateway</html>", { status: 504, headers: { "Content-Type": "text/html" } })));
    const err = (await api.get("/me").catch((e) => e)) as ApiError;
    expect(err.status).toBe(504);
    expect(err.message).toBe("The server is waking up or busy. Please try again.");
  });

  it("gives up after the client timeout", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn(
        (_input: RequestInfo | URL, init?: RequestInit) =>
          new Promise<Response>((_resolve, reject) => {
            init?.signal?.addEventListener("abort", () => reject(new DOMException("Aborted", "AbortError")));
          }),
      ),
    );
    const err = (await api.post("/api/v2/ai/explain", {}, { timeoutMs: 20 }).catch((e) => e)) as ApiError;
    expect(err).toBeInstanceOf(ApiError);
    expect(err.code).toBe("client_timeout");
  });
});
