import { Link } from "react-router";
import { ArrowRight, CheckCircle2, Compass, Route } from "lucide-react";
import { tutor } from "../api/tutor";
import type { PathStep } from "../api/tutor";
import { useApi } from "../hooks/useApi";
import { Button, Card, cx, EmptyState, ErrorState, ModeBadge, ModelEstimate, PageHeader, PageLoader, pct, ProgressBar, STATUS_META } from "../components/ui";

function StepRow({ step, index, current }: { step: PathStep; index: number; current: boolean }) {
  const s = step.skill;
  const meta = STATUS_META[s.status];
  return (
    <li className="relative pl-14">
      <span className={cx("absolute left-0 top-1 grid size-10 place-items-center rounded-2xl border text-sm font-semibold", current ? "border-brand bg-brand text-brand-ink shadow-[0_0_0_6px_#8b8cff22]" : step.path_status === "Completed" ? "border-strength/40 bg-strength/10 text-strength" : "border-line bg-surface-2 text-ink-muted")}>
        {step.path_status === "Completed" ? <CheckCircle2 className="size-5" /> : index + 1}
      </span>
      <div className={cx("rounded-2xl border p-5", current ? "border-brand/40 bg-brand-soft" : "border-line bg-surface")}>
        <div className="flex flex-wrap items-start justify-between gap-3">
          <div className="min-w-0">
            <p className={cx("text-[11px] font-semibold uppercase tracking-wider", current ? "text-brand" : meta.text)}>{step.path_status}</p>
            <h3 className="mt-1 text-lg font-semibold">{s.name}</h3>
            <p className="text-xs text-ink-faint">
              {s.code} · {s.domain_name}
            </p>
          </div>
          <ModeBadge mode={s.mode} />
        </div>
        {step.reason && <p className="mt-3 text-sm text-ink-muted">{step.reason}</p>}
        <div className="mt-4 grid gap-4 text-sm sm:grid-cols-3">
          <div>
            <p className="text-xs text-ink-faint">Practice progress</p>
            <p className="mt-0.5 font-medium">{s.attempts ? `${s.correct}/${s.attempts} correct (${pct(s.observed_accuracy)})` : "Not started"}</p>
          </div>
          <div>
            <p className="text-xs text-ink-faint">Learning resources</p>
            <div className="mt-1.5 flex items-center gap-2">
              <ProgressBar value={step.resources_done} max={Math.max(step.resources_total, 1)} />
              <span className="shrink-0 text-xs text-ink-muted">
                {step.resources_done}/{step.resources_total}
              </span>
            </div>
          </div>
          <div>
            <p className="text-xs text-ink-faint">Model estimate</p>
            <ModelEstimate p={s.predicted_p} className="mt-1" />
          </div>
        </div>
        <div className="mt-4 flex flex-wrap items-center justify-between gap-3">
          {step.next_activity && <p className="text-sm">Next: <span className="font-medium">{step.next_activity}</span></p>}
          <Button size="sm" variant={current ? "primary" : "secondary"} to={`/skills/${s.id}`} icon={<ArrowRight className="size-4" />}>
            Open
          </Button>
        </div>
      </div>
    </li>
  );
}

export function PathPage() {
  const p = useApi(() => tutor.path(), []);
  if (p.loading) return <PageLoader />;
  if (p.error) return <ErrorState error={p.error} onRetry={p.reload} />;
  const { steps, completed } = p.data!;
  return (
    <div>
      <PageHeader eyebrow="Mathematics learning journey" title="Your learning path" subtitle="Updated after every assessment and practice session. You can open any topic at any time." actions={<Button variant="secondary" to="/skills" icon={<Compass className="size-4" />}>Explore all topics</Button>} />
      {steps.length === 0 && completed.length === 0 ? (
        <EmptyState icon={<Route className="size-8" />} title="Your path appears after the diagnostic" action={<Button to="/assess/start?kind=diagnostic">Start the diagnostic</Button>}>
          MENTORX builds your path from your own answers.
        </EmptyState>
      ) : (
        <div className="grid gap-8 lg:grid-cols-[1fr_300px]">
          <ol className="relative space-y-5 before:absolute before:bottom-4 before:left-5 before:top-4 before:w-px before:bg-line">
            {steps.map((s, i) => (
              <StepRow key={s.skill.id} step={s} index={i} current={i === 0} />
            ))}
          </ol>
          <aside className="space-y-4">
            <Card>
              <h2 className="font-semibold">Completed</h2>
              {completed.length ? (
                <ul className="mt-3 space-y-2">
                  {completed.map((c) => (
                    <li key={c.skill.id}>
                      <Link to={`/skills/${c.skill.id}`} className="flex items-center gap-2 rounded-xl bg-surface-2 px-3 py-2.5 text-sm hover:bg-surface-3">
                        <CheckCircle2 className="size-4 shrink-0 text-strength" />
                        <span className="min-w-0 flex-1 truncate">{c.skill.name}</span>
                        <span className="text-xs text-ink-faint">{pct(c.skill.reassessed_accuracy)}</span>
                      </Link>
                    </li>
                  ))}
                </ul>
              ) : (
                <p className="mt-2 text-sm text-ink-muted">Pass a reassessment (80%+) to complete a skill.</p>
              )}
            </Card>
            <Card>
              <h2 className="font-semibold">How the path is ordered</h2>
              <ol className="mt-3 ml-4 list-decimal space-y-1.5 text-sm text-ink-muted">
                <li>Your chosen focus topic</li>
                <li>Potential weaknesses, backed by your answers</li>
                <li>Skills due for revision</li>
                <li>Developing skills</li>
                <li>Untested building blocks and core skills</li>
              </ol>
            </Card>
          </aside>
        </div>
      )}
    </div>
  );
}
