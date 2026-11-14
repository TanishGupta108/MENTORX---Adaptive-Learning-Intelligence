import { useState } from "react";
import { Link } from "react-router";
import { BarChart3 } from "lucide-react";
import { tutor } from "../api/tutor";
import { useApi } from "../hooks/useApi";
import { useProfile } from "../components/AppShell";
import { ActivityChart } from "../components/charts";
import { Disclosure } from "../components/Disclosure";
import { Button, Card, EmptyState, ErrorState, PageHeader, PageLoader, pct, ProgressBar, StatusBadge } from "../components/ui";

const KIND_LABEL: Record<string, string> = { diagnostic: "Placement check", skill_check: "Skill check", reassessment: "Skill check (again)", practice: "Practice", mixed: "Mixed practice", review: "Review" };

function Big({ label, value }: { label: string; value: string | number }) {
  return (
    <div>
      <p className="text-2xl font-semibold tracking-tight sm:text-3xl">{value}</p>
      <p className="mt-0.5 text-sm text-ink-muted">{label}</p>
    </div>
  );
}

export function ProgressPage() {
  const { profile } = useProfile();
  const a = useApi(() => tutor.analytics(), [profile.subject_code]);
  const [showPred, setShowPred] = useState(false);
  const [allHistory, setAllHistory] = useState(false);
  if (a.loading && !a.data) return <PageLoader label="Loading your progress…" />;
  if (a.error) return <ErrorState error={a.error} onRetry={a.reload} />;
  const d = a.data!;
  const t = d.totals;
  if (!t.questions) {
    return (
      <div>
        <PageHeader title="Progress" />
        <EmptyState icon={<BarChart3 className="size-8" />} title="Nothing here yet" action={<Button to="/home">Go to Home</Button>}>
          Answer a few questions and your progress will appear here.
        </EmptyState>
      </div>
    );
  }
  const mastered = d.skills.filter((s) => s.completed || s.mastery?.mastered).length;
  const goal = profile.goal;
  const history = [
    ...d.assessments.map((x) => ({ key: `a-${x.id}`, label: `${KIND_LABEL[x.kind] ?? x.kind}${x.skill ? `: ${x.skill}` : ""}`, acc: x.accuracy, n: `${x.correct}/${x.answered}`, at: x.completed_at })),
    ...d.practice.map((x) => ({ key: `p-${x.id}`, label: `${KIND_LABEL[x.kind] ?? "Practice"}${x.kind === "skill" ? `: ${x.skill}` : ""}`, acc: x.accuracy, n: `${x.answered} answered`, at: x.started_at })),
  ].sort((x, y) => y.at.localeCompare(x.at));
  const shown = allHistory ? history : history.slice(0, 5);

  return (
    <div className="space-y-6">
      <PageHeader title="Progress" subtitle={profile.subject ?? undefined} />

      <Card>
        <div className="grid grid-cols-3 gap-4">
          <Big label="questions answered" value={t.questions} />
          <Big label="correct" value={pct(t.observed_accuracy)} />
          <Big label={mastered === 1 ? "skill mastered" : "skills mastered"} value={mastered} />
        </div>
        {goal && (
          <div className="mt-6">
            <div className="mb-2 flex items-baseline justify-between gap-3 text-sm">
              <span className="font-medium">{goal.label}</span>
              <span className="text-ink-muted">
                {goal.value}/{goal.target}
              </span>
            </div>
            <ProgressBar value={goal.value} max={goal.target} tone={goal.achieved ? "strength" : "brand"} />
            {goal.achieved && <p className="mt-2 text-sm text-strength">Goal reached. Well done!</p>}
          </div>
        )}
      </Card>

      <Card>
        <h2 className="mb-3 font-semibold">Last 30 days</h2>
        <ActivityChart data={d.daily} height={220} />
      </Card>

      <Card>
        <div className="mb-3 flex flex-wrap items-center justify-between gap-3">
          <h2 className="font-semibold">Skills you’ve worked on</h2>
          <label className="flex min-h-11 cursor-pointer items-center gap-2 text-sm text-ink-muted sm:min-h-0">
            <input type="checkbox" className="size-4 accent-brand" checked={showPred} onChange={(e) => setShowPred(e.target.checked)} />
            Show predictions
          </label>
        </div>
        <div className="-mx-5 overflow-x-auto px-5">
          <table className="w-full min-w-[480px] text-sm">
            <thead>
              <tr className="border-b border-line text-left text-sm text-ink-muted">
                <th className="py-2 pr-3 font-medium">Skill</th>
                <th className="py-2 pr-3 font-medium">Status</th>
                <th className="py-2 pr-3 text-right font-medium">Correct</th>
                <th className="py-2 pr-3 text-right font-medium">Answers</th>
                {showPred && <th className="py-2 text-right font-medium">Prediction</th>}
              </tr>
            </thead>
            <tbody>
              {d.skills.map((s) => (
                <tr key={s.id} className="border-b border-line/60">
                  <td className="py-2.5 pr-3">
                    <Link to={`/skills/${s.id}`} className="font-medium hover:text-brand">
                      {s.name}
                    </Link>
                  </td>
                  <td className="py-2.5 pr-3">
                    <StatusBadge status={s.status} />
                  </td>
                  <td className="py-2.5 pr-3 text-right font-semibold">{pct(s.observed_accuracy)}</td>
                  <td className="py-2.5 pr-3 text-right text-ink-muted">{s.attempts}</td>
                  {showPred && <td className="py-2.5 text-right text-accent">{pct(s.predicted_p)}</td>}
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </Card>

      {history.length > 0 && (
        <Card>
          <h2 className="mb-2 text-[19px] font-semibold tracking-tight">History</h2>
          <ul className="text-sm">
            {shown.map((x) => (
              <li key={x.key} className="flex items-center gap-3 border-b border-line py-3 last:border-b-0">
                <span className="min-w-0 flex-1">
                  <span className="block truncate font-medium">{x.label}</span>
                  <span className="block text-xs text-ink-faint">
                    {new Date(x.at).toLocaleDateString()}, {x.n}
                  </span>
                </span>
                <span className="font-semibold tabular-nums">{pct(x.acc)}</span>
              </li>
            ))}
          </ul>
          {history.length > 5 && (
            <Button variant="ghost" size="sm" className="mt-2" onClick={() => setAllHistory((v) => !v)}>
              {allHistory ? "Show less" : `Show all (${history.length})`}
            </Button>
          )}
        </Card>
      )}

      <Disclosure title="About the predictions">
        {d.model.available ? (
          <div className="space-y-2 text-sm text-ink-muted">
            <p>
              Predictions come from {d.model.display_name ?? d.model.name}, a knowledge-tracing model trained on past students&apos; answers. They are a guess of your chance on a typical question, and never change a skill&apos;s status. Only your own answers do.
            </p>
            <p>
              Model size: {d.model.parameters?.toLocaleString() ?? "—"} parameters. On students it never saw in training: AUC {d.model.test_auc?.toFixed(3) ?? "—"}, accuracy {pct(d.model.test_accuracy, 1)}.
            </p>
          </div>
        ) : (
          <p className="text-sm text-ink-muted">No prediction model is available for this subject right now, so only your own answers are shown.</p>
        )}
      </Disclosure>
    </div>
  );
}
