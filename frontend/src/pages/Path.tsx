import { useState } from "react";
import { learning } from "../api/endpoints";
import { DIFFICULTY, ReasonBadge } from "../components/ReasonBadge";
import { Button, Card, EmptyState, ErrorState, MasteryBar, PageHeader, Spinner } from "../components/ui";
import { useApi } from "../hooks/useApi";
import { useStartSession } from "../hooks/useStartSession";

const TRIGGER: Record<string, string> = {
  diagnostic: "after your diagnostic",
  session: "after your last session",
  revision: "because revisions fell due",
  manual: "on request",
};

export function PathPage() {
  const path = useApi((s) => learning.path(s));
  const starter = useStartSession();
  const [refreshing, setRefreshing] = useState(false);

  return (
    <>
      <PageHeader title="Your learning path">
        Up to five concepts, chosen from your current mastery and the prerequisite graph.
      </PageHeader>
      {path.loading && !path.data && <Spinner />}
      {path.error && <ErrorState error={path.error} onRetry={path.reload} />}
      {starter.error && (
        <p role="alert" className="mb-4 text-sm text-danger">
          {starter.error}
        </p>
      )}
      {path.data && (
        <>
          <p className="mb-4 text-sm text-ink-muted">
            Updated {new Date(path.data.generated_at).toLocaleString()}{" "}
            {TRIGGER[path.data.trigger] ?? ""}.
          </p>
          {path.data.items.length === 0 ? (
            <EmptyState title="Nothing to recommend right now">
              Every concept is at or above mastery. Pick any concept to practise from the Concepts
              page.
            </EmptyState>
          ) : (
            <ol className="space-y-4">
              {path.data.items.map((i) => (
                <li key={i.concept}>
                  <Card>
                    <div className="flex flex-wrap items-start justify-between gap-3">
                      <div className="min-w-0 flex-1">
                        <p className="text-sm text-ink-muted">Step {i.position}</p>
                        <h2 className="text-lg font-semibold">
                          {i.name} <ReasonBadge reason={i.reason} />
                        </h2>
                        <p className="mt-1 text-ink-muted">{i.explanation}</p>
                      </div>
                      <Button
                        disabled={starter.busy !== null}
                        onClick={() =>
                          i.reason === "revision"
                            ? starter.start("revision")
                            : starter.start("practice", i.concept)
                        }
                      >
                        {i.reason === "revision" ? "Revise" : "Practise"}
                      </Button>
                    </div>
                    <div className="mt-3 grid gap-2 sm:grid-cols-2 sm:items-center">
                      <MasteryBar value={i.mastery} label={`${i.name} mastery`} />
                      <p className="text-sm text-ink-muted sm:text-right">
                        Suggested level: {DIFFICULTY[i.target_difficulty]}
                      </p>
                    </div>
                  </Card>
                </li>
              ))}
            </ol>
          )}
          <div className="mt-6 flex flex-wrap gap-3">
            {path.data.items.length > 0 && (
              <Button disabled={starter.busy !== null} onClick={() => starter.start("practice")}>
                Start recommended practice
              </Button>
            )}
            <Button
              variant="secondary"
              disabled={refreshing}
              onClick={async () => {
                setRefreshing(true);
                try {
                  await learning.regenerate();
                  path.reload();
                } finally {
                  setRefreshing(false);
                }
              }}
            >
              {refreshing ? "Updating…" : "Refresh path"}
            </Button>
          </div>
          {path.data.model_version && (
            <p className="mt-6 text-xs text-ink-muted">
              Mastery estimates by model {path.data.model_version}.
            </p>
          )}
        </>
      )}
    </>
  );
}
