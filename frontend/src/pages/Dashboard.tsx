import { Link } from "react-router";
import { dashboard, learning } from "../api/endpoints";
import type { Dashboard } from "../api/types";
import { useAuth } from "../auth/AuthContext";
import { ActivityHeatmap, TrendChart } from "../components/charts";
import { ReasonBadge } from "../components/ReasonBadge";
import {
  Button,
  ButtonLink,
  Card,
  EmptyState,
  ErrorState,
  MasteryBar,
  PageHeader,
  pct,
  Spinner,
  Stat,
} from "../components/ui";
import { useApi } from "../hooks/useApi";
import { useStartSession } from "../hooks/useStartSession";

const SESSION_LABEL = { diagnostic: "diagnostic", practice: "practice session", revision: "revision" };

export function DashboardPage() {
  const { user } = useAuth();
  const summary = useApi((s) => dashboard.summary(s));
  const path = useApi((s) => learning.path(s));
  const revision = useApi((s) => learning.revision(s));
  const trends = useApi((s) => dashboard.trends(30, s));
  const activity = useApi((s) => dashboard.activity(12, s));
  const starter = useStartSession();

  if (summary.loading && !summary.data) return <Spinner />;
  if (summary.error) return <ErrorState error={summary.error} onRetry={summary.reload} />;
  const d = summary.data as Dashboard;

  return (
    <>
      <PageHeader title={`Hi, ${user?.full_name.split(" ")[0] ?? "there"}`}>
        Here's where you stand in Machine Learning.
      </PageHeader>

      {starter.error && (
        <p role="alert" className="mb-4 text-sm text-danger">
          {starter.error}
        </p>
      )}

      {d.active_sessions.map((s) => (
        <div
          key={s.id}
          className="mb-4 flex flex-wrap items-center justify-between gap-3 rounded-xl border border-brand/40 bg-brand/5 p-4"
        >
          <p>
            You have an unfinished {SESSION_LABEL[s.type]} ({s.answered} of {s.target} answered).
          </p>
          <ButtonLink to={`/session/${s.id}`}>Resume</ButtonLink>
        </div>
      ))}

      {!d.diagnostic_completed && !d.active_sessions.some((s) => s.type === "diagnostic") && (
        <Card className="mb-6 border-brand/40">
          <h2 className="font-semibold">Take the diagnostic to get your starting profile</h2>
          <p className="mt-1 text-sm text-ink-muted">
            {d.concepts_total} questions, one per concept. Your learning path and dashboard fill in
            from your answers.
          </p>
          <Button
            className="mt-4"
            disabled={starter.busy !== null}
            onClick={() => starter.start("diagnostic")}
          >
            Start the diagnostic
          </Button>
        </Card>
      )}

      <div className="grid grid-cols-2 gap-3 lg:grid-cols-4">
        <Stat
          label="Mean mastery"
          value={d.mean_mastery == null ? "—" : pct(d.mean_mastery)}
          hint={
            d.concepts_assessed
              ? `across ${d.concepts_assessed} assessed concept${d.concepts_assessed === 1 ? "" : "s"}`
              : "after your first answers"
          }
        />
        <Stat
          label="Concepts mastered"
          value={`${d.concepts_mastered} / ${d.concepts_total}`}
          hint={`mastery ≥ ${pct(d.mastered_threshold)}`}
        />
        <Stat label="Questions answered" value={d.questions_answered} />
        <Stat
          label="Accuracy"
          value={d.accuracy == null ? "—" : pct(d.accuracy)}
          hint={`${d.sessions_completed} session${d.sessions_completed === 1 ? "" : "s"} completed`}
        />
      </div>

      <div className="mt-6 grid gap-6 lg:grid-cols-3">
        <Card
          className="lg:col-span-2"
          title="Next up"
          action={
            <Link to="/path" className="text-sm font-medium text-brand">
              Full path
            </Link>
          }
        >
          {path.loading && !path.data && <Spinner />}
          {path.error && <ErrorState error={path.error} onRetry={path.reload} />}
          {path.data && path.data.items.length === 0 && (
            <EmptyState title="Nothing to recommend right now">
              Every concept is at or above mastery. Practise any concept from the concept map.
            </EmptyState>
          )}
          {path.data && path.data.items.length > 0 && (
            <>
              <ol className="space-y-3">
                {path.data.items.slice(0, 3).map((i) => (
                  <li key={i.concept} className="flex flex-wrap items-start justify-between gap-3">
                    <div className="min-w-0 flex-1">
                      <p className="font-medium">
                        {i.name} <ReasonBadge reason={i.reason} />
                      </p>
                      <p className="mt-0.5 text-sm text-ink-muted">{i.explanation}</p>
                    </div>
                    <Button
                      variant="secondary"
                      disabled={starter.busy !== null}
                      onClick={() =>
                        starter.start(i.reason === "revision" ? "revision" : "practice", i.reason === "revision" ? undefined : i.concept)
                      }
                    >
                      Practise
                    </Button>
                  </li>
                ))}
              </ol>
              <Button
                className="mt-5"
                disabled={starter.busy !== null}
                onClick={() => starter.start("practice")}
              >
                {starter.isBusy("practice") ? "Starting…" : "Start recommended practice"}
              </Button>
            </>
          )}
        </Card>

        <Card
          title="Revision"
          action={
            <Link to="/revision" className="text-sm font-medium text-brand">
              Details
            </Link>
          }
        >
          {revision.loading && !revision.data && <Spinner />}
          {revision.error && <ErrorState error={revision.error} onRetry={revision.reload} />}
          {revision.data &&
            (revision.data.due.length ? (
              <>
                <p>
                  <strong>{revision.data.due.length}</strong> concept
                  {revision.data.due.length === 1 ? " is" : "s are"} due for revision.
                </p>
                <ul className="mt-2 space-y-1 text-sm text-ink-muted">
                  {revision.data.due.slice(0, 3).map((r) => (
                    <li key={r.concept}>
                      {r.name}: {pct(r.peak)} → {pct(r.mastery)}
                    </li>
                  ))}
                </ul>
                <Button
                  className="mt-4"
                  disabled={starter.busy !== null}
                  onClick={() => starter.start("revision")}
                >
                  Revise now (5 questions)
                </Button>
              </>
            ) : (
              <EmptyState title="Nothing due">
                Concepts become due when you've reached 80% and the model predicts you've dropped
                below 60%.
              </EmptyState>
            ))}
        </Card>
      </div>

      <div className="mt-6 grid gap-6 lg:grid-cols-2">
        <Card title="Strongest">
          <ConceptRanking items={d.strongest} />
        </Card>
        <Card title="Most room to grow">
          <ConceptRanking items={d.weakest} />
        </Card>
      </div>

      <div className="mt-6 grid gap-6 lg:grid-cols-2">
        <Card title="Last 30 days">
          {trends.error && <ErrorState error={trends.error} onRetry={trends.reload} />}
          {trends.data &&
            (trends.data.points.some((p) => p.answered > 0 || p.mean_mastery != null) ? (
              <TrendChart trends={trends.data} />
            ) : (
              <EmptyState title="No activity yet">Your progress chart starts with your first answer.</EmptyState>
            ))}
        </Card>
        <Card title="Activity">
          {activity.error && <ErrorState error={activity.error} onRetry={activity.reload} />}
          {activity.data && <ActivityHeatmap activity={activity.data} />}
        </Card>
      </div>
    </>
  );
}

function ConceptRanking({ items }: { items: Dashboard["strongest"] }) {
  if (!items.length)
    return (
      <EmptyState title="Not enough answers yet">
        Concepts appear here after 3 or more answers on them.
      </EmptyState>
    );
  return (
    <ul className="space-y-3">
      {items.map((c) => (
        <li key={c.concept}>
          <p className="text-sm font-medium">{c.name}</p>
          <MasteryBar value={c.mastery} label={`${c.name} mastery`} />
        </li>
      ))}
    </ul>
  );
}
