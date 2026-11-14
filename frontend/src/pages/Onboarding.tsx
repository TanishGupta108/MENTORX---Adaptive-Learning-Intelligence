import { useMemo, useState } from "react";
import type { ReactNode } from "react";
import { useNavigate } from "react-router";
import { ArrowLeft, ArrowRight, BookMarked, Check, Gauge, Globe2, LifeBuoy, Rocket, Search, Sigma, Target, TrendingUp } from "lucide-react";
import { tutor } from "../api/tutor";
import type { GoalType, Pace, SubjectInfo } from "../api/tutor";
import { ApiError } from "../api/client";
import { useApi } from "../hooks/useApi";
import { Button, cx, ErrorState, inputClass, Logo, Spinner } from "../components/ui";

type Step = "subject" | "grade" | "pace" | "goal";

const PACES: { id: Pace; title: string; text: string; icon: typeof Target }[] = [
  { id: "more_support", title: "More support", text: "Easier questions first, with more explanation and hints.", icon: LifeBuoy },
  { id: "balanced", title: "Balanced", text: "Follow my answers and adjust as I go.", icon: Gauge },
  { id: "challenge", title: "Challenge me", text: "Harder questions sooner, with less help.", icon: Rocket },
];

const GOALS: { id: GoalType; title: string; text: string; icon: typeof Target }[] = [
  { id: "assess_overall", title: "Check what I know", text: "A short placement check across the subject.", icon: Target },
  { id: "improve_weak", title: "Improve my weak areas", text: "Find what needs work, then practise it step by step.", icon: TrendingUp },
  { id: "learn_topic", title: "Learn one topic", text: "Pick one skill and focus on it.", icon: BookMarked },
];

const GRADES: (number | null)[] = [4, 5, 6, 7, 8, null];

function Choice({ selected, onClick, icon, title, text, note, disabled, clamp }: { selected: boolean; onClick: () => void; icon?: ReactNode; title: string; text?: string; note?: string | null; disabled?: boolean; clamp?: boolean }) {
  return (
    <button
      type="button"
      onClick={onClick}
      aria-pressed={selected}
      disabled={disabled}
      className={cx("flex w-full items-center gap-4 rounded-2xl border p-4 text-left transition-colors disabled:cursor-not-allowed disabled:opacity-50 sm:p-5", selected ? "border-brand bg-brand-soft" : "border-line bg-surface hover:border-line-strong")}
    >
      {icon && <span className={cx("grid size-11 shrink-0 place-items-center rounded-xl", selected ? "bg-brand text-brand-ink" : "bg-surface-3 text-brand")}>{icon}</span>}
      <span className="flex-1">
        <span className="block font-semibold">{title}</span>
        {text && <span className={cx("mt-0.5 block text-sm text-ink-muted", clamp && "line-clamp-2")}>{text}</span>}
        {note && <span className="mt-1.5 block text-xs text-ink-faint">{note}</span>}
      </span>
      {selected && <Check className="size-5 shrink-0 text-brand" aria-hidden />}
    </button>
  );
}

export function OnboardingPage() {
  const navigate = useNavigate();
  const subjects = useApi(() => tutor.subjects().catch(() => [] as SubjectInfo[]), []);
  const [subjectCode, setSubjectCode] = useState<string | null>(null);
  const catalog = useApi(() => tutor.catalog(), []);
  const [stepIndex, setStepIndex] = useState(0);
  const [grade, setGrade] = useState<number | null | undefined>(undefined);
  const [pace, setPace] = useState<Pace>("balanced");
  const [goal, setGoal] = useState<GoalType | null>(null);
  const [skillId, setSkillId] = useState<number | null>(null);
  const [query, setQuery] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string>();

  const list = subjects.data ?? [];
  const chosen = list.find((s) => s.code === subjectCode) ?? list.find((s) => s.current) ?? list[0];
  // grades only for subjects that have them (Mathematics); assume yes when /subjects isn't available
  const hasGrades = chosen ? chosen.grades : true;
  const steps: Step[] = [...(list.length >= 2 ? (["subject"] as Step[]) : []), ...(hasGrades ? (["grade"] as Step[]) : []), "pace", "goal"];
  const step = steps[Math.min(stepIndex, steps.length - 1)]!;
  const last = stepIndex >= steps.length - 1;

  // The topic list comes from the current subject (Mathematics until onboarding is saved), so a
  // topic can only be picked here for that subject; others pick one from Skills afterwards.
  const topicsAvailable = !catalog.data || !chosen || catalog.data.subject.code === chosen.code;
  const skills = useMemo(() => (catalog.data?.domains ?? []).flatMap((d) => d.skills), [catalog.data]);
  const filtered = skills.filter((s) => `${s.code} ${s.name} ${s.domain_name}`.toLowerCase().includes(query.toLowerCase()));

  const canNext =
    step === "subject" ? Boolean(subjectCode ?? chosen) : step === "grade" ? grade !== undefined : step === "pace" ? true : goal !== null && (goal !== "learn_topic" || skillId !== null);

  function next() {
    setError(undefined);
    if (goal === "learn_topic" && !topicsAvailable) setGoal(null);
    setStepIndex((i) => i + 1);
  }

  async function finish() {
    if (!goal) return;
    setBusy(true);
    setError(undefined);
    try {
      await tutor.onboard({
        goal_type: goal,
        focus_skill_id: goal === "learn_topic" ? skillId : null,
        goal_kind: "weekly_practice",
        goal_target: 30,
        subject_code: chosen?.code ?? "MATH",
        grade: hasGrades ? (grade ?? null) : null,
        pace_preference: pace,
      });
    } catch (e) {
      setError(e instanceof ApiError ? e.message : "Something went wrong. Please try again.");
      setBusy(false);
      return;
    }
    try {
      const a = goal === "learn_topic" && skillId ? await tutor.startAssessment("skill_check", skillId) : await tutor.startAssessment("diagnostic");
      navigate(`/assess/${a.id}`, { replace: true });
    } catch {
      navigate("/home", { replace: true });
    }
  }

  return (
    <div className="min-h-screen">
      <div className="mx-auto flex max-w-2xl items-center justify-between px-5 py-6">
        <Logo />
        <div className="flex items-center gap-2" role="progressbar" aria-valuemin={1} aria-valuemax={steps.length} aria-valuenow={stepIndex + 1} aria-label={`Step ${stepIndex + 1} of ${steps.length}`}>
          {steps.map((s, i) => (
            <span key={s} className={cx("h-1.5 rounded-full transition-all", i <= stepIndex ? "w-8 bg-brand" : "w-4 bg-line-strong")} />
          ))}
        </div>
      </div>

      <main className="mx-auto max-w-2xl px-5 pb-16">
        {subjects.loading && <Spinner label="Getting things ready…" />}

        {!subjects.loading && step === "subject" && (
          <section className="animate-rise">
            <p className="text-sm font-medium text-brand">Welcome to MENTORX</p>
            <h1 className="mt-2 text-2xl font-semibold tracking-tight sm:text-3xl">What would you like to learn?</h1>
            <p className="mt-2 text-ink-muted">You can switch subjects any time.</p>
            <div className="mt-6 space-y-3">
              {list.map((s) => (
                <Choice key={s.code} selected={chosen?.code === s.code} onClick={() => setSubjectCode(s.code)} icon={s.code === "GEO" ? <Globe2 className="size-5" /> : <Sigma className="size-5" />} title={s.name} text={s.description} note={s.code === "GEO" ? s.attribution : null} clamp />
              ))}
            </div>
          </section>
        )}

        {!subjects.loading && step === "grade" && (
          <section className="animate-rise">
            {stepIndex === 0 && <p className="text-sm font-medium text-brand">Welcome to MENTORX</p>}
            <h1 className="mt-2 text-2xl font-semibold tracking-tight sm:text-3xl">Which grade are you in?</h1>
            <p className="mt-2 text-ink-muted">We use it to pick your first questions. You can change it later.</p>
            <div className="mt-6 grid grid-cols-3 gap-3">
              {GRADES.map((g) => (
                <button
                  key={g ?? "unsure"}
                  type="button"
                  aria-pressed={grade === g}
                  onClick={() => setGrade(g)}
                  className={cx("min-h-14 rounded-2xl border text-base font-semibold", grade === g ? "border-brand bg-brand-soft" : "border-line bg-surface hover:border-line-strong")}
                >
                  {g === null ? "Not sure" : `Grade ${g}`}
                </button>
              ))}
            </div>
          </section>
        )}

        {!subjects.loading && step === "pace" && (
          <section className="animate-rise">
            {stepIndex === 0 && <p className="text-sm font-medium text-brand">Welcome to MENTORX</p>}
            <h1 className="mt-2 text-2xl font-semibold tracking-tight sm:text-3xl">How do you like to learn?</h1>
            <p className="mt-2 text-ink-muted">MENTORX still adjusts to your answers. You can change this later.</p>
            <div className="mt-6 space-y-3">
              {PACES.map((p) => (
                <Choice key={p.id} selected={pace === p.id} onClick={() => setPace(p.id)} icon={<p.icon className="size-5" />} title={p.title} text={p.text} />
              ))}
            </div>
          </section>
        )}

        {!subjects.loading && step === "goal" && (
          <section className="animate-rise">
            <h1 className="mt-2 text-2xl font-semibold tracking-tight sm:text-3xl">What would you like to do first?</h1>
            <div className="mt-6 space-y-3">
              {GOALS.map((g) => (
                <Choice
                  key={g.id}
                  selected={goal === g.id}
                  onClick={() => setGoal(g.id)}
                  icon={<g.icon className="size-5" />}
                  title={g.title}
                  text={g.id === "learn_topic" && !topicsAvailable ? "You can pick a topic from Skills after this short setup." : g.text}
                  disabled={g.id === "learn_topic" && !topicsAvailable}
                />
              ))}
            </div>
            {goal === "learn_topic" && (
              <div className="mt-6">
                <label htmlFor="topic-search" className="mb-2 block text-sm font-medium">
                  Which topic?
                </label>
                {catalog.loading && <Spinner label="Loading topics…" />}
                {catalog.error && <ErrorState error={catalog.error} onRetry={catalog.reload} />}
                {catalog.data && (
                  <>
                    <div className="relative">
                      <Search className="pointer-events-none absolute left-3 top-3.5 size-4 text-ink-faint" aria-hidden />
                      <input id="topic-search" type="search" className={cx(inputClass, "pl-9")} placeholder="Search topics" value={query} onChange={(e) => setQuery(e.target.value)} />
                    </div>
                    <div className="mt-3 max-h-72 space-y-1.5 overflow-y-auto pr-1">
                      {filtered.map((s) => (
                        <button
                          key={s.id}
                          type="button"
                          aria-pressed={skillId === s.id}
                          onClick={() => setSkillId(s.id)}
                          className={cx("flex min-h-11 w-full items-center justify-between gap-3 rounded-xl border px-3.5 py-2.5 text-left text-sm", skillId === s.id ? "border-brand bg-brand-soft" : "border-line hover:bg-surface-2")}
                        >
                          <span className="font-medium">{s.name}</span>
                          <span className="shrink-0 text-xs text-ink-faint">{s.domain_name}</span>
                        </button>
                      ))}
                      {!filtered.length && <p className="px-1 text-sm text-ink-muted">No topics match.</p>}
                    </div>
                  </>
                )}
              </div>
            )}
            {goal && (
              <p className="mt-6 text-sm text-ink-muted">
                Next: {goal === "learn_topic" ? "a few questions in your topic" : "a short placement check (about 10 questions, no time limit)"}.
              </p>
            )}
          </section>
        )}

        {error && (
          <p className="mt-4 text-sm text-danger" role="alert">
            {error}
          </p>
        )}

        <div className="mt-10 flex items-center justify-between">
          <Button variant="ghost" onClick={() => setStepIndex((s) => Math.max(0, s - 1))} disabled={stepIndex === 0 || busy} icon={<ArrowLeft className="size-4" />}>
            Back
          </Button>
          {!last ? (
            <Button onClick={next} disabled={!canNext || subjects.loading}>
              Continue <ArrowRight className="size-4" />
            </Button>
          ) : (
            <Button onClick={() => void finish()} loading={busy} disabled={!canNext} size="lg">
              Start <ArrowRight className="size-4" />
            </Button>
          )}
        </div>
      </main>
    </div>
  );
}
