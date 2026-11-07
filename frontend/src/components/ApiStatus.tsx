import { useEffect, useState } from "react";
import { getHealth } from "../api/client";

type Status = "checking" | "online" | "offline";

const LABEL: Record<Status, string> = {
  checking: "Checking API…",
  online: "API online",
  offline: "API offline",
};

const DOT: Record<Status, string> = {
  checking: "bg-ink-muted",
  online: "bg-success",
  offline: "bg-danger",
};

/** Shows whether the backend is reachable. Proves frontend ↔ backend wiring in M0. */
export function ApiStatus() {
  const [status, setStatus] = useState<Status>("checking");

  useEffect(() => {
    const controller = new AbortController();
    getHealth(controller.signal)
      .then((h) => setStatus(h.status === "ok" ? "online" : "offline"))
      .catch((err: unknown) => {
        if (!(err instanceof DOMException && err.name === "AbortError")) setStatus("offline");
      });
    return () => controller.abort();
  }, []);

  return (
    <span
      role="status"
      className="inline-flex items-center gap-2 rounded-full border border-line bg-surface px-3 py-1 text-sm text-ink-muted"
    >
      <span aria-hidden className={`h-2 w-2 rounded-full ${DOT[status]}`} />
      {LABEL[status]}
    </span>
  );
}
