/**
 * Typed API client.
 *
 * - Same-origin by default (`/api/v1/...`): the Vite dev server proxies to the backend, and in
 *   production Vercel rewrites `/api` to it. Same origin lets the refresh token live in a
 *   Strict, HttpOnly cookie that JavaScript never sees.
 * - The short-lived access token is kept in memory only (not localStorage), so an XSS bug
 *   can't steal a long-lived credential.
 * - On a 401, the client refreshes once (shared by concurrent requests) and retries.
 */

const BASE_URL = (import.meta.env.VITE_API_URL ?? "").replace(/\/$/, "");

/** "/me" -> /api/v1/me (auth and account); "/api/v2/..." is used as given (the tutor API). */
function apiUrl(path: string) {
  return `${BASE_URL}${path.startsWith("/api/") ? path : `/api/v1${path}`}`;
}

export class ApiError extends Error {
  constructor(
    public readonly status: number,
    public readonly code: string,
    message: string,
    public readonly requestId?: string,
    /** Per-field messages for 422 validation errors, keyed by field name. */
    public readonly fields: Record<string, string> = {},
  ) {
    super(message);
    this.name = "ApiError";
  }
}

let accessToken: string | null = null;
let onSessionExpired: (() => void) | null = null;
let refreshing: Promise<boolean> | null = null;

export function setAccessToken(token: string | null) {
  accessToken = token;
}

export function hasAccessToken() {
  return accessToken !== null;
}

/** Called when the session can't be refreshed (e.g. logged out elsewhere). */
export function setSessionExpiredHandler(handler: (() => void) | null) {
  onSessionExpired = handler;
}

type TokenResponse = { access_token: string; expires_in: number };

async function parseError(res: Response): Promise<ApiError> {
  let code = "http_error";
  let message = `Request failed (${res.status}).`;
  let requestId: string | undefined;
  const fields: Record<string, string> = {};
  try {
    const body = (await res.json()) as {
      error?: {
        code?: string;
        message?: string;
        request_id?: string;
        fields?: { field: string; message: string }[];
      };
    };
    if (body.error) {
      code = body.error.code ?? code;
      message = body.error.message ?? message;
      requestId = body.error.request_id;
      for (const f of body.error.fields ?? []) {
        fields[f.field] = f.message.replace(/^Value error, /, "");
      }
    }
  } catch {
    // non-JSON error (e.g. a proxy's HTML page): keep the generic message
  }
  if (res.status >= 500) message = "Something went wrong on our side. Please try again.";
  return new ApiError(res.status, code, message, requestId, fields);
}

/** Exchange the refresh cookie for a new access token. Returns false if there is no session. */
export function refreshSession(): Promise<boolean> {
  refreshing ??= (async () => {
    try {
      const res = await fetch(`${BASE_URL}/api/v1/auth/refresh`, {
        method: "POST",
        credentials: "include",
      });
      if (!res.ok) {
        accessToken = null;
        return false;
      }
      accessToken = ((await res.json()) as TokenResponse).access_token;
      return true;
    } catch {
      return false;
    } finally {
      refreshing = null;
    }
  })();
  return refreshing;
}

export type RequestOptions = {
  body?: unknown;
  signal?: AbortSignal;
  /** Don't try to refresh on 401 (used by the auth endpoints themselves). */
  noRetry?: boolean;
};

export async function request<T>(method: string, path: string, opts: RequestOptions = {}) {
  const send = () =>
    fetch(apiUrl(path), {
      method,
      credentials: "include",
      signal: opts.signal,
      headers: {
        Accept: "application/json",
        ...(opts.body !== undefined ? { "Content-Type": "application/json" } : {}),
        ...(accessToken ? { Authorization: `Bearer ${accessToken}` } : {}),
      },
      body: opts.body !== undefined ? JSON.stringify(opts.body) : undefined,
    });

  let res = await send();
  if (res.status === 401 && !opts.noRetry) {
    if (await refreshSession()) {
      res = await send();
    } else {
      onSessionExpired?.();
    }
  }
  if (!res.ok) throw await parseError(res);
  if (res.status === 204) return undefined as T;
  return (await res.json()) as T;
}

/** Download a file from the API with the user's credentials (e.g. CSV exports). */
export async function downloadFile(path: string, filename: string) {
  const send = () =>
    fetch(apiUrl(path), {
      credentials: "include",
      headers: accessToken ? { Authorization: `Bearer ${accessToken}` } : {},
    });
  let res = await send();
  if (res.status === 401 && (await refreshSession())) res = await send();
  if (!res.ok) throw await parseError(res);
  const url = URL.createObjectURL(await res.blob());
  const a = document.createElement("a");
  a.href = url;
  a.download = filename;
  document.body.appendChild(a);
  a.click();
  a.remove();
  URL.revokeObjectURL(url);
}

export const api = {
  get: <T>(path: string, opts?: RequestOptions) => request<T>("GET", path, opts),
  post: <T>(path: string, body?: unknown, opts?: RequestOptions) =>
    request<T>("POST", path, { ...opts, body }),
  put: <T>(path: string, body?: unknown, opts?: RequestOptions) =>
    request<T>("PUT", path, { ...opts, body }),
  patch: <T>(path: string, body?: unknown, opts?: RequestOptions) =>
    request<T>("PATCH", path, { ...opts, body }),
  delete: <T>(path: string, body?: unknown, opts?: RequestOptions) =>
    request<T>("DELETE", path, { ...opts, body }),
};
