import { Link } from "react-router";
import { Activity, BarChart3, BookOpen, BrainCircuit, ClipboardCheck, Lightbulb, Target, TrendingUp } from "lucide-react";
import { tutor } from "../api/tutor";
import { useApi } from "../hooks/useApi";
import { ActivityChart, SkillComparisonChart, TimelineChart } from "../components/charts";
import { ActivityList } from "./Dashboard";
import { Card, CardTitle, EmptyState, ErrorState, ModeBadge, PageHeader, PageLoader, pct, ProgressBar, Stat, StatusBadge } from "../components/ui";

const KIND_LABEL: Record<string, string> = { diagnostic: "Diagnostic", skill_check: "Skill check", reassessment: "Reassessment" };

export function AnalyticsPage() {
  const a = useApi(() => tutor.analytics(), []);
  if (a.loading) return <PageLoader />;
  if (a.error) return <ErrorState error={a.error} onRetry={a.reload} />;
  const d = a.data!;
  const t = d.totals;
  if (!t.questions) {
    return (
      <div>
        <PageHeader title="Performance analytics" />
        <EmptyState icon={<BarChart3 className="size-8" />} title="No data yet">Answer a few questions and your analytics will appear here.</EmptyState>
      </div>
    );
  }
  const timeline = [
    ...d.assessments.map((x) => ({ at: x.completed_at, label: `${KIND_LABEL[x.kind]}${x.skill ? `: ${x.skill}` : ""}`, accuracy: x.accuracy, kind: x.kind })),
    ...d.practice.map((x) => ({ at: x.started_at, label: `Practice: ${x.skill}`, accuracy: x.accuracy, kind: "practice" })),
  ].sort((x, y) => x.at.localeCompare(y.at));

  return (
    <div className="space-y-6">
      <PageHeader eyebrow="Performance analytics" title="Am I actually improving?" subtitle="Everything here is your observed performance. The model's predictions are labelled and drawn separately." />

      <section className="grid grid-cols-2 gap-3 lg:grid-cols-4">
        <Stat label="Observed accuracy" value={pct(t.observed_accuracy)} hint={`${t.correct} of ${t.questions} questions`} icon={<Target className="size-4" />} />
        <Stat label="Assessment accuracy" value={pct(t.assessment_accuracy)} hint={`${t.assessments} assessments`} icon={<ClipboardCheck className="size-4" />} />
        <Stat label="Practice accuracy" value={pct(t.practice_accuracy)} hint={`${t.practice_sessions} sessions`} icon={<TrendingUp className="size-4" />} />
        <Stat label="Hints used" value={pct(t.hint_rate)} hint="of all answers" icon={<Lightbulb className="size-4" />} />
      </section>

      <Card>
        <CardTitle icon={<Activity className="size-4" />} title="Learning activity" subtitle="Questions per day and observed accuracy, last 30 days" />
        <ActivityChart data={d.daily} height={260} />
      </Card>

      <div className="grid gap-6 lg:grid-cols-2">
        <Card>
          <CardTitle icon={<BrainCircuit className="size-4" />} title="Skill-wise performance" subtitle="Green: your observed accuracy. Dashed blue: model estimate (a prediction)." />
          <SkillComparisonChart skills={d.skills} />
        </Card>
        <Card>
          <CardTitle icon={<TrendingUp className="size-4" />} title="Improvement over time" subtitle="Accuracy in each assessment and practice session, in order" />
          {timeline.length > 1 ? <TimelineChart points={timeline} /> : <p className="text-sm text-ink-muted">Complete a couple of sessions to see a trend.</p>}
        </Card>
      </div>

      <Card>
        <CardTitle title="Skills you've worked on" />
        <div className="overflow-x-auto">
          <table className="w-full min-w-[640px] text-sm">
            <thead>
              <tr className="border-b border-line text-left text-xs uppercase tracking-wider text-ink-faint">
                <th className="py-2 pr-3 font-medium">Skill</th>
                <th className="py-2 pr-3 font-medium">Diagnosis</th>
                <th className="py-2 pr-3 font-medium">Observed</th>
                <th className="py-2 pr-3 font-medium">Answers</th>
                <th className="py-2 pr-3 font-medium">Model estimate</th>
                <th className="py-2 font-medium">Mode</th>
              </tr>
            </thead>
            <tbody>
              {d.skills.map((s) => (
                <tr key={s.id} className="border-b border-line/60">
                  <td className="py-2.5 pr-3">
                    <Link to={`/skills/${s.id}`} className="font-medium hover:text-brand">{s.name}</Link>
                    <span className="block text-xs text-ink-faint">{s.code}</span>
                  </td>
                  <td className="py-2.5 pr-3"><StatusBadge status={s.status} /></td>
                  <td className="py-2.5 pr-3 font-semibold">{pct(s.observed_accuracy)}</td>
                  <td className="py-2.5 pr-3 text-ink-muted">{s.correct}/{s.attempts}</td>
                  <td className="py-2.5 pr-3 text-accent">{pct(s.predicted_p)}</td>
                  <td className="py-2.5"><ModeBadge mode={s.mode} /></td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </Card>

      <div className="grid gap-6 lg:grid-cols-2">
        <Card>
          <CardTitle icon={<ClipboardCheck className="size-4" />} title="Assessments and practice" />
          <ul className="space-y-2 text-sm">
            {[...d.assessments.map((x) => ({ key: x.id, label: `${KIND_LABEL[x.kind]}${x.skill ? ` · ${x.skill}` : ""}`, acc: x.accuracy, n: `${x.correct}/${x.answered}`, at: x.completed_at, extra: x.outcome?.replace("_", " ") })), ...d.practice.map((x) => ({ key: x.id, label: `Practice · ${x.skill}`, acc: x.accuracy, n: `${x.answered} answered`, at: x.started_at, extra: `${x.mode} mode` }))]
              .sort((x, y) => y.at.localeCompare(x.at))
              .slice(0, 12)
              .map((x) => (
                <li key={x.key} className="flex items-center gap-3 rounded-xl bg-surface-2/60 px-3 py-2.5">
                  <span className="min-w-0 flex-1">
                    <span className="block truncate font-medium">{x.label}</span>
                    <span className="block text-xs text-ink-faint">
                      {new Date(x.at).toLocaleDateString()} · {x.n}
                      {x.extra ? ` · ${x.extra}` : ""}
                    </span>
                  </span>
                  <span className="font-semibold">{pct(x.acc)}</span>
                </li>
              ))}
          </ul>
        </Card>
        <div className="space-y-6">
          <Card>
            <CardTitle icon={<BookOpen className="size-4" />} title="Resource completion" />
            <div className="flex items-center gap-3">
              <ProgressBar value={t.resources_completed} max={Math.max(t.resources_total, 1)} tone="strength" />
              <span className="shrink-0 text-sm">
                {t.resources_completed}/{t.resources_total}
              </span>
            </div>
          </Card>
          <Card>
            <CardTitle icon={<Activity className="size-4" />} title="Recent learning activity" />
            <ActivityList items={d.activity} />
          </Card>
        </div>
      </div>
      {d.model.available && (
        <p className="text-center text-xs text-ink-faint">
          Model: {d.model.display_name}, {d.model.parameters?.toLocaleString()} parameters, test AUC {d.model.test_auc?.toFixed(3)} and accuracy {pct(d.model.test_accuracy, 1)} on held-out FoundationalASSIST students.
        </p>
      )}
    </div>
  );
}
