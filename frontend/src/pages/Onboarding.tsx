import { useState } from "react";
import { Navigate, useNavigate } from "react-router";
import { ApiError } from "../api/client";
import { sessions, subjects, SUBJECT } from "../api/endpoints";
import { useAuth } from "../auth/AuthContext";
import { Button, ErrorState, Spinner } from "../components/ui";
import { useApi } from "../hooks/useApi";

export function OnboardingPage() {
  const { user, reloadUser } = useAuth();
  const navigate = useNavigate();
  const list = useApi((s) => subjects.list(s));
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string>();
  const subject = list.data?.find((s) => s.code === SUBJECT);

  if (user?.enrolled_subjects.includes(SUBJECT) && !busy) return <Navigate to="/dashboard" replace />;

  async function start(takeDiagnostic: boolean) {
    setBusy(true);
    setError(undefined);
    try {
      await subjects.enroll(SUBJECT);
      if (takeDiagnostic) {
        const s = await sessions.start("diagnostic");
        await reloadUser();
        navigate(`/session/${s.id}`, { replace: true });
      } else {
        await reloadUser();
        navigate("/dashboard", { replace: true });
      }
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Couldn't reach the server.");
      setBusy(false);
    }
  }

  return (
    <main className="mx-auto max-w-xl px-4 py-10 sm:py-16">
      <p className="text-lg font-semibold tracking-tight">
        MENTOR<span className="text-brand">X</span>
      </p>
      <h1 className="mt-10 text-3xl font-semibold tracking-tight">
        Welcome{user ? `, ${user.full_name.split(" ")[0]}` : ""}.
      </h1>
      {list.loading && <Spinner />}
      {list.error && <ErrorState error={list.error} onRetry={list.reload} />}
      {subject && (
        <>
          <p className="mt-3 text-ink-muted">
            You're starting <strong className="text-ink">{subject.name}</strong>:{" "}
            {subject.concept_count} concepts, from the foundations to neural networks.
          </p>
          <section className="mt-8 rounded-xl border border-line bg-surface p-5">
            <h2 className="font-semibold">First, a short diagnostic</h2>
            <ul className="mt-3 list-disc space-y-2 pl-5 text-sm text-ink-muted">
              <li>
                {subject.concept_count} questions, one per concept, in order. About 15 minutes.
              </li>
              <li>You won't see right or wrong until the end, so it measures, not teaches.</li>
              <li>
                If you don't know, choose <em>"I don't know yet"</em> rather than guessing. It gives
                a more accurate starting point.
              </li>
              <li>You can stop at any time and come back. Your answers so far are kept.</li>
            </ul>
            {error && (
              <p role="alert" className="mt-4 text-sm text-danger">
                {error}
              </p>
            )}
            <div className="mt-6 flex flex-wrap gap-3">
              <Button disabled={busy} onClick={() => start(true)}>
                {busy ? "Starting…" : "Start the diagnostic"}
              </Button>
              <Button variant="ghost" disabled={busy} onClick={() => start(false)}>
                Skip for now
              </Button>
            </div>
          </section>
        </>
      )}
    </main>
  );
}
