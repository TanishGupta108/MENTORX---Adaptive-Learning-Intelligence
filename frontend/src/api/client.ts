/** Minimal typed API client. From M5 on, types are generated from the backend's OpenAPI schema. */

const BASE_URL = (import.meta.env.VITE_API_URL ?? "http://localhost:8000").replace(/\/$/, "");

export class ApiError extends Error {
  constructor(
    public readonly status: number,
    message: string,
  ) {
    super(message);
  }
}

export async function apiGet<T>(path: string, init?: RequestInit): Promise<T> {
  const res = await fetch(`${BASE_URL}/api/v1${path}`, {
    ...init,
    headers: { Accept: "application/json", ...init?.headers },
  });
  if (!res.ok) {
    throw new ApiError(res.status, `GET ${path} failed with ${res.status}`);
  }
  return (await res.json()) as T;
}

export type HealthResponse = { status: string };

export const getHealth = (signal?: AbortSignal) => apiGet<HealthResponse>("/health", { signal });
