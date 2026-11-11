import { Activity as ActivityIcon, ArrowRight, BookOpen, CalendarClock, ClipboardCheck, Flame, Goal, Layers3, LineChart, Map, Play, Sparkles, Target, TrendingUp } from "lucide-react";
import { Link } from "react-router";
import { tutor } from "../api/tutor";
import type { Activity, Recommendation, Status } from "../api/tutor";
import { useApi } from "../hooks/useApi";
import { ActivityChart } from "../components/charts";
import { Button, Card, CardTitle, EmptyState, ErrorState, ModeBadge, ModelEstimate, PageLoader, ProgressBar, Stat, STATUS_META, StatusBadge, timeAgo } from "../components/ui";

function greeting() {
  const h = new Date().getHours();
  return h < 12 ? "Good morning" : h < 17 ? "Good afternoon" : "Good evening";
}

const REASON_LABEL: Record<string, string> = {
  focus: "Your focus",
  weakness: "Needs attention",
  developing: "Keep building",
  needs_assessment: "Check this next",
  revision: "Time to review",
  prerequisite: "Building block",
  next_objective: "Next objective",
};

export function RecommendationCard({ rec, highlight = false }: { rec: Recommendation; highlight?: boolean }) {
  return (
    <div className={`flex h-full flex-col rounded-2xl border p-4 ${highlight ? "border-brand/40 bg-brand-soft" : "border-line bg-surface-2/60"}`}>
      <div className="flex items-center justify-between gap-2">
        <span className="text-[11px] font-semibold uppercase tracking-wider text-brand">{REASON_LABEL[rec.reason_code] ?? "Recommended"}</span>
        <StatusBadge status={rec.skill.status} />
      </div>
      <p className="mt-2 font-semibold">{rec.skill.name}</p>
      <p className="mt-1 flex-1 text-sm text-ink-muted">{rec.reason}</p>
      <div className="mt-3 flex flex-wrap gap-1.5">
        {rec.activities.slice(0, 3).map((a) => (
          <span key={a} className="rounded-md bg-surface-3 px-2 py-0.5 text-xs text-ink-muted">
            {a}
          </span>
        ))}
      </div>
      <Button to={`/skills/${rec.skill.id}`} variant={highlight ? "primary" : "secondary"} size="sm" className="mt-4 self-start" icon={<Play className="size-3.5" />}>
        Start learning
      </Button>
    </div>
  );
}

const ACT_ICON: Record<string, typeof Target> = { diagnostic: ClipboardCheck, skill_check: ClipboardCheck, reassessment: TrendingUp, practice: Target, resource: BookOpen };

export function ActivityList({ items }: { items: Activity[] }) {
  if (!items.length) return <p className="text-sm text-ink-muted">Nothing yet. Your assessments, practice and completed resources will appear here.</p>;
  return (
    <ul className="space-y-1">
      {items.map((a) => {
        const Icon = ACT_ICON[a.kind] ?? ActivityIcon;
        const to = a.skill_id ? `/skills/${a.skill_id}` : a.kind === "diagnostic" ? "/diagnosis" : "/analytics";
        return (
          <li key={`${a.kind}-${a.id}`}>
            <Link to={to} className="flex items-center gap-3 rounded-xl px-2 py-2.5 hover:bg-surface-2">
              <span className="grid size-9 shrink-0 place-items-center rounded-lg bg-surface-3 text-brand">
                <Icon className="size-4" />
              </span>
              <span className="min-w-0 flex-1">
                <span className="block truncate text-sm font-medium">{a.title}</span>
                <span className="block text-xs text-ink-faint">{a.detail}</span>
              </span>
              <span className="shrink-0 text-xs text-ink-faint">{timeAgo(a.at)}</span>
            </Link>
          </li>
        );
      })}
    </ul>
  );
}

export function DashboardPage() {
  const d = useApi(() => tutor.dashboard(), []);
  if (d.loading) return <PageLoader label="Getting your dashboard ready…" />;
  if (d.error) return <ErrorState error={d.error} onRetry={d.reload} />;
  const data = d.data!;
  const map = data.skill_map;
  const mapOrder: Status[] = ["potential_weakness", "developing", "likely_strength"];
  const cont = data.continue;

  return (
    <div className="space-y-6">
      <header className="flex flex-col gap-1">
        <h1 className="text-2xl font-semibold tracking-tight sm:text-[28px]">
          {greeting()}, {data.name}
        </h1>
        <p className="text-ink-muted">Let's make progress today.</p>
      </header>

      {!data.diagnostic_completed ? (
        <Card className="border-brand/40 bg-gradient-to-br from-brand-soft to-transparent p-7">
          <div className="flex flex-col gap-5 md:flex-row md:items-center md:justify-between">
            <div>
              <p className="text-xs font-semibold uppercase tracking-wider text-brand">Step 1</p>
              <h2 className="mt-1 text-xl font-semibold">Let's find out what you already know</h2>
              <p className="mt-1 max-w-xl text-ink-muted">Your personal plan, skill map and recommendations appear after a short diagnostic of about 10 questions.</p>
            </div>
            <Button size="lg" to="/assess/start?kind=diagnostic" icon={<ArrowRight className="size-4" />}>
              Start the diagnostic
            </Button>
          </div>
        </Card>
      ) : (
        cont && (
          <Card className="relative overflow-hidden border-brand/30 p-0">
            <div className="pointer-events-none absolute -right-20 -top-20 size-72 rounded-full bg-brand/15 blur-3xl" />
            <div className="relative flex flex-col gap-6 p-6 md:flex-row md:items-center md:justify-between md:p-7">
              <div className="min-w-0">
                <p className="flex items-center gap-2 text-xs font-semibold uppercase tracking-wider text-brand">
                  <Play className="size-3.5" /> Continue learning
                </p>
                <h2 className="mt-2 text-xl font-semibold sm:text-2xl">{cont.skill.name}</h2>
                <p className="mt-1.5 max-w-2xl text-sm text-ink-muted">{cont.reason}</p>
                <div className="mt-3 flex flex-wrap items-center gap-2">
                  <StatusBadge status={cont.skill.status} />
                  <ModeBadge mode={cont.skill.mode} />
                  <ModelEstimate p={cont.skill.predicted_p} />
                </div>
              </div>
              <Button size="lg" to={`/skills/${cont.skill.id}`} icon={<ArrowRight className="size-4" />} className="shrink-0">
                Continue
              </Button>
            </div>
          </Card>
        )
      )}

      <section aria-label="Your learning overview" className="grid grid-cols-2 gap-3 lg:grid-cols-5">
        <Stat label="Skills assessed" value={data.overview.skills_assessed} hint={`of ${data.overview.skills_available} available`} icon={<Layers3 className="size-4" />} />
        <Stat label="Likely strengths" value={data.overview.likely_strengths} icon={<Sparkles className="size-4 text-strength" />} />
        <Stat label="Need improvement" value={data.overview.needs_improvement} hint="Potential weakness + developing" icon={<Target className="size-4 text-developing" />} />
        <Stat label="Practice sessions" value={data.overview.practice_sessions} hint="completed" icon={<Flame className="size-4 text-weakness" />} />
        <Stat label="This week" value={data.overview.questions_this_week} hint="questions answered" icon={<ActivityIcon className="size-4 text-accent" />} />
      </section>

      <div className="grid gap-6 lg:grid-cols-[1.6fr_1fr]">
        <Card>
          <CardTitle icon={<Sparkles className="size-4" />} title="Recommended for you" subtitle="Picked from your evidence. Each one says why." action={<Link to="/path" className="text-sm text-brand hover:underline">Learning path →</Link>} />
          {data.recommendations.length ? (
            <div className="grid gap-3 md:grid-cols-2">
              {data.recommendations.slice(0, 4).map((r, i) => (
                <RecommendationCard key={r.skill.id} rec={r} highlight={i === 0} />
              ))}
            </div>
          ) : (
            <EmptyState title="No recommendations yet">Complete the diagnostic to get personalised recommendations.</EmptyState>
          )}
        </Card>

        <div className="space-y-6">
          <Card>
            <CardTitle icon={<Goal className="size-4" />} title="Learning goal" action={<Link to="/profile" className="text-sm text-brand hover:underline">Change</Link>} />
            {data.goal ? (
              <div>
                <p className="font-medium">{data.goal.label}</p>
                <div className="mt-3 flex items-center gap-3">
                  <ProgressBar value={data.goal.value} max={data.goal.target} tone={data.goal.achieved ? "strength" : "brand"} />
                  <span className="shrink-0 text-sm font-semibold">
                    {data.goal.value}/{data.goal.target}
                  </span>
                </div>
                {data.goal.achieved && <p className="mt-2 text-sm text-strength">Goal reached. Brilliant work! 🎉</p>}
              </div>
            ) : (
              <p className="text-sm text-ink-muted">No goal set.</p>
            )}
          </Card>

          {data.revision_due.length > 0 && (
            <Card>
              <CardTitle icon={<CalendarClock className="size-4" />} title="Due for revision" />
              <ul className="space-y-2">
                {data.revision_due.map((s) => (
                  <li key={s.id}>
                    <Link to={`/skills/${s.id}`} className="flex items-center justify-between rounded-xl bg-surface-2 px-3 py-2.5 text-sm hover:bg-surface-3">
                      {s.name}
                      <ArrowRight className="size-4 text-ink-faint" />
                    </Link>
                  </li>
                ))}
              </ul>
            </Card>
          )}

          <Card>
            <CardTitle icon={<ActivityIcon className="size-4" />} title="Recent activity" />
            <ActivityList items={data.activity} />
          </Card>
        </div>
      </div>

      <div className="grid gap-6 lg:grid-cols-[1fr_1.2fr]">
        <Card>
          <CardTitle icon={<Map className="size-4" />} title="Your skill map" subtitle={`${data.unassessed_count} skills still need assessment`} action={<Link to="/skills" className="text-sm text-brand hover:underline">All skills →</Link>} />
          <div className="space-y-4">
            {mapOrder.map((st) => {
              const list = map[st] ?? [];
              return (
                <div key={st}>
                  <p className={`mb-2 flex items-center gap-2 text-xs font-semibold uppercase tracking-wider ${STATUS_META[st].text}`}>
                    <span className={`size-1.5 rounded-full ${STATUS_META[st].dot}`} /> {STATUS_META[st].label} · {list.length}
                  </p>
                  {list.length ? (
                    <div className="flex flex-wrap gap-2">
                      {list.map((s) => (
                        <Link key={s.id} to={`/skills/${s.id}`} className="rounded-lg border border-line bg-surface-2 px-2.5 py-1.5 text-xs hover:border-line-strong" title={`${s.name}: ${s.correct}/${s.attempts} correct`}>
                          {s.name.length > 38 ? `${s.name.slice(0, 36)}…` : s.name}
                        </Link>
                      ))}
                    </div>
                  ) : (
                    <p className="text-xs text-ink-faint">None yet</p>
                  )}
                </div>
              );
            })}
          </div>
        </Card>

        <Card>
          <CardTitle icon={<LineChart className="size-4" />} title="Learning progress" subtitle="Questions answered and your observed accuracy, last 14 days" />
          {data.progress.some((p) => p.attempts > 0) ? <ActivityChart data={data.progress} /> : <p className="text-sm text-ink-muted">Your progress chart appears after your first answers.</p>}
          {data.model.available && (
            <p className="mt-3 text-xs text-ink-faint">
              Model predictions come from {data.model.display_name} (test AUC {data.model.test_auc?.toFixed(3)} on held-out students) and are always shown separately from your observed results.
            </p>
          )}
        </Card>
      </div>
    </div>
  );
}
