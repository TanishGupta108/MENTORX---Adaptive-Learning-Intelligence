/** Account endpoints (/api/v1): sign-up, sign-in, session refresh and the current user.
 * The learning features live in ./tutor.ts (/api/v2). */
import { api, setAccessToken } from "./client";
import type { User } from "./types";

type Token = { access_token: string; expires_in: number };

export const auth = {
  async login(email: string, password: string) {
    const t = await api.post<Token>("/auth/login", { email, password }, { noRetry: true });
    setAccessToken(t.access_token);
  },
  async register(body: { email: string; password: string; full_name: string; privacy_accepted: boolean; timezone?: string }) {
    const t = await api.post<Token>("/auth/register", body, { noRetry: true });
    setAccessToken(t.access_token);
  },
  async logout() {
    try {
      await api.post<void>("/auth/logout", undefined, { noRetry: true });
    } finally {
      setAccessToken(null);
    }
  },
};

export const me = {
  get: (signal?: AbortSignal) => api.get<User>("/me", { signal }),
};
