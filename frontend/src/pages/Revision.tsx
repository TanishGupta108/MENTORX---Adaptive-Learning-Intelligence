import { learning } from "../api/endpoints";
import { Button, Card, EmptyState, ErrorState, PageHeader, pct, Spinner } from "../components/ui";
import { useApi } from "../hooks/useApi";
import { useStartSession } from "../hooks/useStartSession";

function ago(iso: string | null) {
  if (!iso) return "";
  const days = Math.floor((Date.now() - new Date(iso).getTime()) / 86_400_000);
  return days < 1 ? "today" : `${days} day${days === 1 ? "" : "s"} ago`;
}

export function RevisionPage() {
  const q = useApi((s) => learning.revision(s));
  const starter = useStartSession();

  return (
    <>
      <PageHeader title="Revision">
        A concept is due when you once reached 80% on it and the model now predicts you've slipped
        below {q.data ? pct(q.data.threshold) : "60%"}.
      </PageHeader>
      {q.loading && !q.data && <Spinner />}
      {q.error && <ErrorState error={q.error} onRetry={q.reload} />}
      {starter.error && (
        <p role="alert" className="mb-4 text-sm text-danger">
          {starter.error}
        </p>
      )}
      {q.data && (
        <div className="grid gap-6 lg:grid-cols-2">
          <Card title="Due now">
            {q.data.due.length === 0 ? (
              <EmptyState title="Nothing is due">
                Keep practising. Concepts appear here once you've mastered them and time has passed.
              </EmptyState>
            ) : (
              <>
                <ul className="divide-y divide-line">
                  {q.data.due.map((r) => (
                    <li key={r.concept} className="py-3">
                      <p className="font-medium">{r.name}</p>
                      <p className="text-sm text-ink-muted">
                        Peaked at {pct(r.peak)}, now {pct(r.mastery)} (down{" "}
                        {Math.round(r.drop * 100)} pts) · last practised {ago(r.last_practised_at)}
                      </p>
                    </li>
                  ))}
                </ul>
                <Button
                  className="mt-4"
                  disabled={starter.busy !== null}
                  onClick={() => starter.start("revision")}
                >
                  {starter.busy ? "Starting…" : "Start a 5-question revision"}
                </Button>
              </>
            )}
          </Card>
          <Card title="Coming up">
            {q.data.upcoming.length === 0 ? (
              <EmptyState title="Nothing to forecast yet">
                Forecasts appear for concepts you've reached 80% on.
              </EmptyState>
            ) : (
              <>
                <ul className="divide-y divide-line">
                  {q.data.upcoming.map((u) => (
                    <li key={u.concept} className="flex items-center justify-between gap-3 py-3">
                      <div>
                        <p className="font-medium">{u.name}</p>
                        <p className="text-sm text-ink-muted">Now {pct(u.mastery)}</p>
                      </div>
                      <p className="text-right text-sm">
                        {u.due_in_days == null
                          ? `Not within ${q.data!.horizon_days} days`
                          : `Due in about ${u.due_in_days} day${u.due_in_days === 1 ? "" : "s"}`}
                      </p>
                    </li>
                  ))}
                </ul>
                <p className="mt-3 text-xs text-ink-muted">
                  Forecast from the model, assuming no further practice. Checked on days 1, 2, 3, 5,
                  7, 10, 14, 21, 30, 45, 60, 90, 120, 150 and 180.
                </p>
              </>
            )}
          </Card>
        </div>
      )}
    </>
  );
}
