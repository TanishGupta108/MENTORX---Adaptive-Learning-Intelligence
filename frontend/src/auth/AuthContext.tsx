import { createContext, useCallback, useContext, useEffect, useMemo, useState } from "react";
import type { ReactNode } from "react";
import { hasAccessToken, refreshSession, setSessionExpiredHandler } from "../api/client";
import { auth, me } from "../api/endpoints";
import type { User } from "../api/types";

type AuthState = {
  /** undefined = still checking for an existing session; null = logged out. */
  user: User | null | undefined;
  login: (email: string, password: string) => Promise<void>;
  register: (body: Parameters<typeof auth.register>[0]) => Promise<void>;
  logout: () => Promise<void>;
  reloadUser: () => Promise<void>;
  setUser: (u: User | null) => void;
};

const AuthContext = createContext<AuthState | null>(null);

export function AuthProvider({ children }: { children: ReactNode }) {
  const [user, setUser] = useState<User | null | undefined>(undefined);

  const reloadUser = useCallback(async () => {
    setUser(await me.get());
  }, []);

  useEffect(() => {
    let cancelled = false;
    setSessionExpiredHandler(() => setUser(null));
    // Restore the session from the refresh cookie, if there is one.
    (async () => {
      const ok = hasAccessToken() || (await refreshSession());
      if (cancelled) return;
      if (!ok) return setUser(null);
      try {
        const u = await me.get();
        if (!cancelled) setUser(u);
      } catch {
        if (!cancelled) setUser(null);
      }
    })();
    return () => {
      cancelled = true;
      setSessionExpiredHandler(null);
    };
  }, []);

  const value = useMemo<AuthState>(
    () => ({
      user,
      setUser,
      reloadUser,
      async login(email, password) {
        await auth.login(email, password);
        await reloadUser();
      },
      async register(body) {
        await auth.register(body);
        await reloadUser();
      },
      async logout() {
        await auth.logout().catch(() => undefined);
        setUser(null);
      },
    }),
    [user, reloadUser],
  );
  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>;
}

export function useAuth() {
  const ctx = useContext(AuthContext);
  if (!ctx) throw new Error("useAuth must be used inside <AuthProvider>");
  return ctx;
}
