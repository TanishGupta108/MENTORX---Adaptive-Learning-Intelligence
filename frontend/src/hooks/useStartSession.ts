import { useState } from "react";
import { useNavigate } from "react-router";
import { ApiError } from "../api/client";
import { sessions } from "../api/endpoints";
import type { SessionType } from "../api/types";

/** Start (or resume) a session and open it. */
export function useStartSession() {
  const navigate = useNavigate();
  const [busy, setBusy] = useState<string | null>(null);
  const [error, setError] = useState<string>();

  async function start(type: SessionType, concept?: string) {
    const key = `${type}:${concept ?? ""}`;
    setBusy(key);
    setError(undefined);
    try {
      const s = await sessions.start(type, concept);
      navigate(`/session/${s.id}`);
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Couldn't reach the server.");
      setBusy(null);
    }
  }

  return { start, busy, error, isBusy: (type: SessionType, concept?: string) => busy === `${type}:${concept ?? ""}` };
}
