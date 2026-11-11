import { ArrowRight, BrainCircuit, CheckCircle2, Compass, Info, Sparkles } from "lucide-react";
import { tutor } from "../api/tutor";
import type { Status } from "../api/tutor";
import { useApi } from "../hooks/useApi";
import { SkillCard } from "../components/SkillCard";
import { RecommendationCard } from "./Dashboard";
import { Button, Card, CardTitle, EmptyState, ErrorState, PageHeader, PageLoader, pct, Ring, STATUS_META } from "../components/ui";

const ORDER: Status[] = ["likely_strength", "developing", "potential_weakness", "needs_assessment"];
const EXPLAIN: Record<Status, string> = {
  likely_strength: "Your answers here were consistently right.",
  developing: "A mix of right and wrong answers, or too little evidence to be sure.",
  potential_weakness: "Your answers suggest this needs more practice.",
  needs_assessment: "Not tested yet. We won't guess a weakness without evidence.",
};

export function DiagnosisPage() {
  const d = useApi(() => tutor.diagnosis(), []);
  if (d.loading) return <PageLoader label="Analysing your answers…" />;
  if (d.error) return <ErrorState error={d.error} onRetry={d.reload} />;
  const data = d.data!;
  if (!data.assessment) {
    return (
      <EmptyState icon={<Compass className="size-8" />} title="No assessment yet" action={<Button to="/assess/start?kind=diagnostic">Start the diagnostic</Button>}>
        Take the diagnostic first, so MENTORX can build your learning profile.
      </EmptyState>
    );
  }
  const acc = data.assessment.answered ? data.assessment.correct / data.assessment.answered : 0;

  return (
    <div className="space-y-6">
      <PageHeader eyebrow="AI skill diagnosis" title="Your learning profile is ready." subtitle={data.headline} actions={<Button to="/dashboard" icon={<ArrowRight className="size-4" />}>Go to my dashboard</Button>} />

      <div className="grid gap-4 lg:grid-cols-[320px_1fr]">
        <Card className="flex items-center gap-5">
          <Ring value={acc} size={92} stroke={8} label={pct(acc)} />
          <div>
            <p className="text-sm text-ink-muted">Assessment result</p>
            <p className="text-xl font-semibold">
              {data.assessment.correct} of {data.assessment.answered} correct
            </p>
            <p className="mt-1 text-xs text-ink-faint">Observed in this assessment</p>
          </div>
        </Card>
        <div className="grid grid-cols-2 gap-3 sm:grid-cols-4">
          {ORDER.map((s) => (
            <div key={s} className="rounded-2xl border border-line bg-surface p-4">
              <span className={`inline-block size-2 rounded-full ${STATUS_META[s].dot}`} />
              <p className="mt-2 text-2xl font-semibold">{data.counts[s] ?? 0}</p>
              <p className="text-xs text-ink-muted">{STATUS_META[s].label}</p>
            </div>
          ))}
        </div>
      </div>

      <Card>
        <CardTitle icon={<CheckCircle2 className="size-4" />} title="Skills you were assessed on" subtitle="Each label comes from your answers. The model estimate is shown separately and is a prediction, not a verified result." />
        <div className="grid gap-3 md:grid-cols-2">
          {data.assessed.map((s) => (
            <SkillCard key={s.id} skill={s} explain={EXPLAIN[s.status]} />
          ))}
        </div>
      </Card>

      {data.recommendations.length > 0 && (
        <Card>
          <CardTitle icon={<Sparkles className="size-4" />} title="Recommended for you" subtitle="Where to start, and why" />
          <div className="grid gap-3 lg:grid-cols-3">
            {data.recommendations.map((r) => (
              <RecommendationCard key={r.skill.id} rec={r} />
            ))}
          </div>
        </Card>
      )}

      <Card>
        <CardTitle icon={<BrainCircuit className="size-4" />} title="Skills that need assessment" subtitle={`${data.counts.needs_assessment ?? 0} skills haven't been tested yet, so they stay "Needs Assessment" whatever the model predicts.`} />
        {data.model_estimates_for_unassessed.length > 0 ? (
          <>
            <p className="mb-3 flex items-center gap-2 text-sm text-ink-muted">
              <Info className="size-4 text-accent" /> From your answers so far, the {data.model.display_name ?? "model"} expects these could be your harder topics. A short skill check would confirm it.
            </p>
            <div className="grid gap-3 md:grid-cols-2">
              {data.model_estimates_for_unassessed.map((s) => (
                <SkillCard key={s.id} skill={s} />
              ))}
            </div>
          </>
        ) : (
          <p className="text-sm text-ink-muted">{data.model.available ? "No model estimates yet." : "The model isn't available right now. Only your observed results are shown."}</p>
        )}
      </Card>
    </div>
  );
}
