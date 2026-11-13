import { Link } from "react-router";
import { ArrowRight, Check, Compass, X } from "lucide-react";
import { tutor } from "../api/tutor";
import type { Status, TraceStep } from "../api/tutor";
import { useApi } from "../hooks/useApi";
import { useProfile } from "../components/AppShell";
import { Disclosure } from "../components/Disclosure";
import { StartButton } from "../components/StartAction";
import { Button, Card, EmptyState, ErrorState, ModelEstimate, PageHeader, PageLoader, STATUS_META, StatusBadge } from "../components/ui";

const ORDER: Status[] = ["likely_strength", "developing", "potential_weakness", "needs_assessment"];

const KIND_LABEL: Record<TraceStep["kind"], string> = {
  start: "Starting point",
  model: "Most useful next",
  prerequisite: "Building block",
};

export function SelectionTrace({ steps }: { steps: TraceStep[] }) {
  return (
    <ol className="space-y-2">
      {steps.map((t) => (
        <li key={t.position} className="flex gap-3 rounded-xl bg-surface-2/60 p-3">
          <span className="grid size-7 shrink-0 place-items-center rounded-full bg-surface-3 text-xs font-semibold">{t.position}</span>
          <div className="min-w-0 flex-1">
            <p className="flex flex-wrap items-center gap-2 text-sm font-medium">
              {t.skill}
              <span className="rounded-md bg-accent/10 px-1.5 py-0.5 text-[11px] font-medium text-accent">{KIND_LABEL[t.kind]}</span>
            </p>
            <p className="mt-0.5 text-xs text-ink-muted">{t.reason}</p>
          </div>
          {t.correct !== null && (
            <span className="shrink-0" aria-label={t.correct ? "correct" : "incorrect"}>
              {t.correct ? <Check className="size-4 text-strength" /> : <X className="size-4 text-weakness" />}
            </span>
          )}
        </li>
      ))}
    </ol>
  );
}

export function DiagnosisPage() {
  const { profile } = useProfile();
  const d = useApi(() => tutor.diagnosis(), [profile.subject_code]);
  if (d.loading && !d.data) return <PageLoader label="Looking at your answers…" />;
  if (d.error) return <ErrorState error={d.error} onRetry={d.reload} />;
  const data = d.data!;
  if (!data.assessment) {
    return (
      <EmptyState icon={<Compass className="size-8" />} title="No placement check yet" action={<Button to="/assess/start?kind=diagnostic">Start the placement check</Button>}>
        Take the short placement check first, so MENTORX knows where to start.
      </EmptyState>
    );
  }

  return (
    <div className="space-y-6">
      <PageHeader title="Your learning profile is ready." subtitle={data.headline} actions={<Button to="/home" icon={<ArrowRight className="size-4" />}>Go to Home</Button>} />

      <Card>
        <p className="text-lg font-semibold">
          {data.assessment.correct} of {data.assessment.answered} correct
        </p>
        <ul className="mt-3 flex flex-wrap gap-x-5 gap-y-2 text-sm">
          {ORDER.map((s) => (
            <li key={s} className="flex items-center gap-2">
              <span className={`size-2 rounded-full ${STATUS_META[s].dot}`} aria-hidden />
              <span className="font-semibold">{data.counts[s] ?? 0}</span>
              <span className="text-ink-muted">{STATUS_META[s].label}</span>
            </li>
          ))}
        </ul>
      </Card>

      <section aria-labelledby="assessed">
        <h2 id="assessed" className="mb-3 text-sm font-semibold uppercase tracking-wider text-ink-faint">
          Skills in your check
        </h2>
        <ul className="divide-y divide-line/60 rounded-2xl border border-line bg-surface">
          {data.assessed.map((s) => (
            <li key={s.id} className="flex flex-col gap-2 px-4 py-3 sm:flex-row sm:items-center sm:gap-3">
              <Link to={`/skills/${s.id}`} className="min-w-0 flex-1 font-medium hover:text-brand">
                {s.name}
                <span className="block text-sm font-normal text-ink-muted">
                  {s.correct} of {s.attempts} correct
                </span>
              </Link>
              <div className="flex items-center justify-between gap-3">
                <StatusBadge status={s.status} />
                <StartButton action={{ endpoint: "practice", skill_id: s.id, guided: s.status !== "likely_strength" }} variant="secondary" size="sm" />
              </div>
            </li>
          ))}
        </ul>
      </section>

      {data.selection_trace.length > 0 && (
        <Disclosure title="How were the questions chosen?">
          <p className="mb-3 text-sm text-ink-muted">The check adapts: after each answer it picks the question that tells us the most, and a wrong answer leads to a check of a building block.</p>
          <SelectionTrace steps={data.selection_trace} />
        </Disclosure>
      )}

      {data.model_estimates_for_unassessed.length > 0 && (
        <Disclosure title="Predictions for skills you haven't tried">
          <p className="mb-3 text-sm text-ink-muted">These skills stay &quot;{STATUS_META.needs_assessment.label}&quot; until you answer questions in them. The model&apos;s guess is shown only as a hint of where to look next.</p>
          <ul className="space-y-1">
            {data.model_estimates_for_unassessed.map((s) => (
              <li key={s.id}>
                <Link to={`/skills/${s.id}`} className="flex min-h-11 flex-wrap items-center justify-between gap-2 rounded-xl px-3 py-2 hover:bg-surface-2">
                  <span className="font-medium">{s.name}</span>
                  <span className="flex items-center gap-3">
                    <StatusBadge status={s.status} />
                    <ModelEstimate p={s.predicted_p} />
                  </span>
                </Link>
              </li>
            ))}
          </ul>
        </Disclosure>
      )}
    </div>
  );
}
