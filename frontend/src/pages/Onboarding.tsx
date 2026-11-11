import { useMemo, useState } from "react";
import { useNavigate } from "react-router";
import { ArrowLeft, ArrowRight, BookMarked, Check, Search, Sigma, Target, TrendingUp } from "lucide-react";
import { tutor } from "../api/tutor";
import type { GoalKind, GoalType } from "../api/tutor";
import { ApiError } from "../api/client";
import { useApi } from "../hooks/useApi";
import { Button, cx, ErrorState, inputClass, Logo, Spinner } from "../components/ui";

const GOALS: { id: GoalType; title: string; text: string; icon: typeof Target }[] = [
  { id: "assess_overall", title: "Assess my overall Mathematics knowledge", text: "A short diagnostic across the curriculum shows where you stand.", icon: Sigma },
  { id: "improve_weak", title: "Improve my weak areas", text: "Find the skills that need attention, then work on them step by step.", icon: TrendingUp },
  { id: "learn_topic", title: "Learn or practise a specific topic", text: "Pick one skill and go deep with notes, examples and practice.", icon: BookMarked },
];

const LEARNING_GOALS: { id: GoalKind; title: string; text: string; target: number | null }[] = [
  { id: "strengthen_skills", title: "Build 3 strong skills", text: "Reach 'Likely Strength' in three skills.", target: 3 },
  { id: "weekly_practice", title: "Practise regularly", text: "Answer 30 questions every 7 days.", target: 30 },
  { id: "master_skill", title: "Complete my chosen topic", text: "Pass a reassessment in the topic you picked.", target: 1 },
];

export function OnboardingPage() {
  const navigate = useNavigate();
  const catalog = useApi(() => tutor.catalog(), []);
  const [step, setStep] = useState(0);
  const [goal, setGoal] = useState<GoalType | null>(null);
  const [skillId, setSkillId] = useState<number | null>(null);
  const [learning, setLearning] = useState<GoalKind>("strengthen_skills");
  const [query, setQuery] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string>();

  const skills = useMemo(() => (catalog.data?.domains ?? []).flatMap((d) => d.skills), [catalog.data]);
  const filtered = skills.filter((s) => `${s.code} ${s.name} ${s.domain_name}`.toLowerCase().includes(query.toLowerCase()));

  async function finish() {
    if (!goal) return;
    setBusy(true);
    setError(undefined);
    try {
      const kind = learning === "master_skill" && goal !== "learn_topic" ? "strengthen_skills" : learning;
      await tutor.onboard({ goal_type: goal, focus_skill_id: goal === "learn_topic" ? skillId : null, goal_kind: kind, goal_target: LEARNING_GOALS.find((g) => g.id === kind)?.target });
      if (goal === "learn_topic" && skillId) navigate(`/assess/start?kind=skill_check&skill=${skillId}`, { replace: true });
      else navigate("/assess/start?kind=diagnostic", { replace: true });
    } catch (e) {
      setError(e instanceof ApiError ? e.message : "Something went wrong. Please try again.");
    } finally {
      setBusy(false);
    }
  }

  const canNext = step === 0 ? goal !== null : step === 1 ? goal !== "learn_topic" || skillId !== null : true;

  return (
    <div className="min-h-screen">
      <div className="mx-auto flex max-w-3xl items-center justify-between px-5 py-6">
        <Logo />
        <div className="flex items-center gap-2" aria-label={`Step ${step + 1} of 3`}>
          {[0, 1, 2].map((i) => (
            <span key={i} className={cx("h-1.5 rounded-full transition-all", i <= step ? "w-8 bg-brand" : "w-4 bg-line-strong")} />
          ))}
        </div>
      </div>

      <main className="mx-auto max-w-3xl px-5 pb-16">
        {step === 0 && (
          <section className="animate-rise">
            <p className="text-sm font-medium text-brand">Welcome to MENTORX 👋</p>
            <h1 className="mt-2 text-3xl font-semibold tracking-tight">What would you like to achieve?</h1>
            <p className="mt-2 text-ink-muted">We'll shape your first session around it. You can change this later.</p>
            <div className="mt-8 space-y-3">
              {GOALS.map((g) => (
                <button
                  key={g.id}
                  type="button"
                  onClick={() => setGoal(g.id)}
                  className={cx(
                    "flex w-full items-center gap-4 rounded-2xl border p-5 text-left transition-colors",
                    goal === g.id ? "border-brand bg-brand-soft" : "border-line bg-surface hover:border-line-strong",
                  )}
                  aria-pressed={goal === g.id}
                >
                  <span className={cx("grid size-11 shrink-0 place-items-center rounded-xl", goal === g.id ? "bg-brand text-brand-ink" : "bg-surface-3 text-brand")}>
                    <g.icon className="size-5" />
                  </span>
                  <span className="flex-1">
                    <span className="block font-semibold">{g.title}</span>
                    <span className="mt-0.5 block text-sm text-ink-muted">{g.text}</span>
                  </span>
                  {goal === g.id && <Check className="size-5 text-brand" />}
                </button>
              ))}
            </div>
          </section>
        )}

        {step === 1 && (
          <section className="animate-rise">
            <h1 className="text-3xl font-semibold tracking-tight">Your subject</h1>
            <p className="mt-2 text-ink-muted">Mathematics is the subject available in this version. More subjects can be added later.</p>
            {catalog.loading && <Spinner label="Loading the curriculum…" />}
            {catalog.error && <ErrorState error={catalog.error} onRetry={catalog.reload} />}
            {catalog.data && (
              <div className="mt-6 rounded-3xl border border-brand/40 bg-surface p-6">
                <div className="flex items-start gap-4">
                  <span className="grid size-12 shrink-0 place-items-center rounded-2xl bg-gradient-to-br from-brand to-accent text-brand-ink">
                    <Sigma className="size-6" />
                  </span>
                  <div className="flex-1">
                    <h2 className="text-xl font-semibold">{catalog.data.subject.name}</h2>
                    <p className="mt-1 text-sm text-ink-muted">{catalog.data.subject.description}</p>
                    <p className="mt-3 text-sm">
                      <span className="font-semibold">{catalog.data.n_skills}</span> skills ·{" "}
                      <span className="font-semibold">{catalog.data.n_questions.toLocaleString()}</span> practice questions
                    </p>
                  </div>
                </div>
                {goal !== "learn_topic" ? (
                  <div className="mt-5 flex flex-wrap gap-2">
                    {catalog.data.domains.map((d) => (
                      <span key={d.code} className="rounded-full border border-line bg-surface-2 px-3 py-1 text-xs text-ink-muted">
                        {d.name} · {d.skills.length}
                      </span>
                    ))}
                  </div>
                ) : (
                  <div className="mt-6">
                    <p className="mb-2 text-sm font-medium">Which topic do you want to learn?</p>
                    <div className="relative">
                      <Search className="pointer-events-none absolute left-3 top-3.5 size-4 text-ink-faint" />
                      <input className={cx(inputClass, "pl-9")} placeholder="Search skills, e.g. percent, equations, circles" value={query} onChange={(e) => setQuery(e.target.value)} />
                    </div>
                    <div className="mt-3 max-h-80 space-y-1.5 overflow-y-auto pr-1">
                      {filtered.map((s) => (
                        <button
                          key={s.id}
                          type="button"
                          onClick={() => setSkillId(s.id)}
                          className={cx(
                            "flex w-full items-center justify-between gap-3 rounded-xl border px-3.5 py-2.5 text-left text-sm",
                            skillId === s.id ? "border-brand bg-brand-soft" : "border-line hover:bg-surface-2",
                          )}
                        >
                          <span>
                            <span className="font-medium">{s.name}</span>
                            <span className="ml-2 text-xs text-ink-faint">{s.code} · {s.domain_name}</span>
                          </span>
                          <span className="shrink-0 text-xs text-ink-faint">{s.n_items} questions</span>
                        </button>
                      ))}
                    </div>
                  </div>
                )}
              </div>
            )}
          </section>
        )}

        {step === 2 && (
          <section className="animate-rise">
            <h1 className="text-3xl font-semibold tracking-tight">Choose a learning goal</h1>
            <p className="mt-2 text-ink-muted">Your dashboard tracks progress toward it.</p>
            <div className="mt-8 grid gap-3 sm:grid-cols-3">
              {LEARNING_GOALS.filter((g) => g.id !== "master_skill" || goal === "learn_topic").map((g) => (
                <button
                  key={g.id}
                  type="button"
                  onClick={() => setLearning(g.id)}
                  className={cx("rounded-2xl border p-5 text-left", learning === g.id ? "border-brand bg-brand-soft" : "border-line bg-surface hover:border-line-strong")}
                  aria-pressed={learning === g.id}
                >
                  <Target className="size-5 text-brand" />
                  <p className="mt-3 font-semibold">{g.title}</p>
                  <p className="mt-1 text-sm text-ink-muted">{g.text}</p>
                </button>
              ))}
            </div>
            <div className="mt-8 rounded-2xl border border-line bg-surface p-5 text-sm text-ink-muted">
              <p className="font-medium text-ink">Next: {goal === "learn_topic" ? "a short skill check" : "your diagnostic assessment"}</p>
              <p className="mt-1">
                {goal === "learn_topic"
                  ? "A few questions in your chosen topic, from easier to harder, so we know where to start."
                  : "About ten questions from different areas of mathematics. Answer as well as you can; there's no time limit."}
              </p>
            </div>
            {error && <p className="mt-4 text-sm text-danger" role="alert">{error}</p>}
          </section>
        )}

        <div className="mt-10 flex items-center justify-between">
          <Button variant="ghost" onClick={() => setStep((s) => s - 1)} disabled={step === 0} icon={<ArrowLeft className="size-4" />}>
            Back
          </Button>
          {step < 2 ? (
            <Button onClick={() => setStep((s) => s + 1)} disabled={!canNext}>
              Continue <ArrowRight className="size-4" />
            </Button>
          ) : (
            <Button onClick={finish} loading={busy} size="lg">
              Start {goal === "learn_topic" ? "skill check" : "diagnostic"} <ArrowRight className="size-4" />
            </Button>
          )}
        </div>
      </main>
    </div>
  );
}
