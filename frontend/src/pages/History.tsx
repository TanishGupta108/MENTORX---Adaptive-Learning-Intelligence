import { Link } from "react-router";
import { sessions } from "../api/endpoints";
import type { Session } from "../api/types";
import { Card, EmptyState, ErrorState, PageHeader, pct, Spinner } from "../components/ui";
import { useApi } from "../hooks/useApi";
import { useConceptNames } from "../hooks/useConcepts";
import { MasteryDelta } from "./Session";

const TYPE = { diagnostic: "Diagnostic", practice: "Practice", revision: "Revision" };
const STATUS = { active: "In progress", completed: "Completed", abandoned: "Replaced" };

export function HistoryPage() {
  const list = useApi((s) => sessions.list(s));
  const names = useConceptNames();

  return (
    <>
      <PageHeader title="History">Your last 50 sessions.</PageHeader>
      {list.loading && !list.data && <Spinner />}
      {list.error && <ErrorState error={list.error} onRetry={list.reload} />}
      {list.data?.length === 0 && (
        <EmptyState title="No sessions yet">Start with the diagnostic from your dashboard.</EmptyState>
      )}
      {list.data && list.data.length > 0 && (
        <ul className="space-y-3">
          {list.data.map((s) => (
            <li key={s.id}>
              <SessionRow s={s} names={names} />
            </li>
          ))}
        </ul>
      )}
    </>
  );
}

function SessionRow({ s, names }: { s: Session; names: Record<string, string> }) {
  const focus = s.focus_concept ? names[s.focus_concept] ?? s.focus_concept : null;
  return (
    <Card>
      <div className="flex flex-wrap items-baseline justify-between gap-2">
        <h2 className="font-semibold">
          {TYPE[s.type]}
          {focus ? `: ${focus}` : ""}
        </h2>
        <p className="text-sm text-ink-muted">
          {new Date(s.started_at).toLocaleString(undefined, { dateStyle: "medium", timeStyle: "short" })}
        </p>
      </div>
      <p className="mt-1 text-sm text-ink-muted">
        {STATUS[s.status]} · {s.answered} of {s.target} answered
        {s.answered > 0 && s.correct != null ? ` · ${pct(s.correct / s.answered)} correct` : ""}
        {s.status === "active" && (
          <>
            {" · "}
            <Link to={`/session/${s.id}`} className="font-medium text-brand">
              Resume
            </Link>
          </>
        )}
      </p>
      {s.changes && s.changes.length > 0 && (
        <ul className="mt-2 space-y-0.5 text-sm">
          {s.changes.map((c) => (
            <li key={c.concept}>
              <MasteryDelta change={c} name={names[c.concept]} />
            </li>
          ))}
        </ul>
      )}
    </Card>
  );
}
