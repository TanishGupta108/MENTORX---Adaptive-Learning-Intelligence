import { useEffect, useState } from "react";
import { Link, useNavigate, useParams } from "react-router";
import { ArrowDown, ArrowRight, ArrowUp, Eye, Flag, HelpCircle, Lightbulb, Sparkles } from "lucide-react";
import { ApiError } from "../api/client";
import { tutor } from "../api/tutor";
import type { AnswerBody, Difficulty, PracticeAnswer, PracticeSummary, Question } from "../api/tutor";
import { useProfile } from "../components/AppShell";
import { DifficultyTag, HintBox, QuestionView } from "../components/QuestionView";
import { Button, Card, cx, ErrorState, ModeBadge, ModelEstimate, PageLoader, pct, ProgressBar, Ring, Spinner } from "../components/ui";

const LEVELS: Difficulty[] = ["easy", "medium", "hard"];

function DifficultyTrack({ level }: { level: Difficulty }) {
  return (
    <div className="flex items-center gap-1.5" aria-label={`Current difficulty: ${level}`}>
      {LEVELS.map((l, i) => (
        <span key={l} className={cx("h-1.5 w-8 rounded-full", i <= LEVELS.indexOf(level) ? (level === "hard" ? "bg-weakness" : level === "medium" ? "bg-developing" : "bg-strength") : "bg-line-strong")} />
      ))}
      <span className="ml-1 text-xs capitalize text-ink-muted">{level}</span>
    </div>
  );
}

function Summary({ s, skillId, onAgain }: { s: PracticeSummary; skillId: number; onAgain: () => void }) {
  return (
    <Card className="mx-auto max-w-2xl p-8 text-center">
      <div className="flex justify-center">
        <Ring value={s.accuracy} size={110} stroke={9} label={<span className="text-xl">{pct(s.accuracy)}</span>} color={s.accuracy >= 0.7 ? "#34d399" : s.accuracy >= 0.4 ? "#fbbf24" : "#fb7185"} />
      </div>
      <h1 className="mt-5 text-2xl font-semibold">Practice complete</h1>
      <p className="mt-1 text-ink-muted">
        You answered {s.correct} of {s.answered} correctly in this session.
      </p>
      <div className="mt-6 grid gap-3 text-left sm:grid-cols-2">
        <div className="rounded-2xl border border-line bg-surface-2 p-4">
          <p className="text-xs font-semibold uppercase tracking-wider text-ink-faint">All your answers in this skill</p>
          <p className="mt-1 text-xl font-semibold">{pct(s.skill_accuracy)}</p>
          <p className="text-xs text-ink-faint">{s.skill_attempts} answers (observed)</p>
        </div>
        <div className="rounded-2xl border border-line bg-surface-2 p-4">
          <p className="text-xs font-semibold uppercase tracking-wider text-ink-faint">Model estimate</p>
          <p className="mt-1 text-xl font-semibold text-accent">{pct(s.predicted_p)}</p>
          <ModelEstimate p={s.predicted_p} />
        </div>
      </div>
      <div className="mt-6 rounded-2xl border border-brand/30 bg-brand-soft p-4 text-left">
        <p className="font-medium">{s.next.label}</p>
        <p className="mt-1 text-sm text-ink-muted">{s.next.why}</p>
      </div>
      <div className="mt-6 flex flex-wrap justify-center gap-3">
        {s.next.action === "reassess" && <Button to={`/assess/start?kind=reassessment&skill=${skillId}`}>Take the reassessment</Button>}
        {s.next.action !== "reassess" && <Button onClick={onAgain}>Practise again</Button>}
        <Button variant="secondary" to={`/skills/${skillId}`}>
          Back to the skill
        </Button>
      </div>
    </Card>
  );
}

export function PracticePage() {
  const { id = "" } = useParams();
  const navigate = useNavigate();
  const { profile } = useProfile();
  const [q, setQ] = useState<Question | null>(null);
  const [fb, setFb] = useState<PracticeAnswer | null>(null);
  const [hint, setHint] = useState<{ text: string; source: string } | null>(null);
  const [summary, setSummary] = useState<PracticeSummary | null>(null);
  const [loading, setLoading] = useState(true);
  const [submitting, setSubmitting] = useState(false);
  const [err, setErr] = useState<string>();
  const [fatal, setFatal] = useState<Error | null>(null);
  const [whyOpen, setWhyOpen] = useState(false);

  async function load() {
    setLoading(true);
    setFb(null);
    setHint(null);
    setErr(undefined);
    setWhyOpen(false);
    try {
      setQ(await tutor.practiceNext(id));
    } catch (e) {
      if (e instanceof ApiError && e.code === "practice_closed") {
        navigate("/dashboard", { replace: true });
        return;
      }
      setFatal(e as Error);
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => {
    void load();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [id]);

  async function submit(body: AnswerBody, reveal = false) {
    setSubmitting(true);
    setErr(undefined);
    try {
      const r = await tutor.practiceAnswer(id, { ...body, reveal });
      setFb(r);
    } catch (e) {
      setErr(e instanceof ApiError ? e.message : "Couldn't submit. Please try again.");
    } finally {
      setSubmitting(false);
    }
  }

  async function getHint() {
    try {
      setHint(await tutor.practiceHint(id));
    } catch (e) {
      setErr(e instanceof ApiError ? e.message : "Couldn't load a hint.");
    }
  }

  async function finishEarly() {
    const r = await tutor.practiceEnd(id);
    if (r.summary) setSummary(r.summary);
    else navigate(q ? `/skills/${q.skill.id}` : "/dashboard");
  }

  async function again() {
    if (!q) return;
    const p = await tutor.startPractice(q.skill.id, true);
    setSummary(null);
    navigate(`/practice/${p.id}`, { replace: true });
  }

  if (fatal) return <ErrorState error={fatal} onRetry={() => { setFatal(null); void load(); }} />;
  if (summary && q) return <Summary s={summary} skillId={q.skill.id} onAgain={again} />;
  if (!q) return <PageLoader label="Choosing a question for you…" />;

  const level = (fb ? fb.difficulty_next : (q.selection?.requested as Difficulty)) ?? "easy";
  const answered = fb ? fb.answered : (q.position ?? 1) - 1;
  const showHintButton = profile.hints_enabled && !fb && !hint;

  return (
    <div className="mx-auto max-w-3xl">
      <div className="mb-5 flex flex-wrap items-center justify-between gap-3">
        <div>
          <Link to={`/skills/${q.skill.id}`} className="text-sm text-ink-muted hover:text-ink">
            ← {q.skill.name}
          </Link>
          <div className="mt-1.5 flex flex-wrap items-center gap-3">
            {q.mode && <ModeBadge mode={q.mode} />}
            <DifficultyTrack level={level} />
          </div>
        </div>
        <Button variant="ghost" size="sm" onClick={finishEarly} icon={<Flag className="size-4" />}>
          Finish session
        </Button>
      </div>
      <div className="mb-5 flex items-center gap-3">
        <ProgressBar value={answered} max={q.total ?? 8} />
        <span className="shrink-0 text-sm text-ink-muted">
          {Math.min((q.position ?? 1), q.total ?? 8)}/{q.total}
        </span>
      </div>

      <Card className="p-6 sm:p-8">
        <div className="mb-5 flex flex-wrap items-center gap-2 text-xs">
          <DifficultyTag level={q.selection?.served === "review" ? "review" : q.difficulty} />
          <button type="button" onClick={() => setWhyOpen((o) => !o)} className="flex items-center gap-1 text-ink-muted hover:text-ink">
            <HelpCircle className="size-3.5" /> Why this question?
          </button>
        </div>
        {whyOpen && q.selection && (
          <div className="mb-5 rounded-xl border border-line bg-surface-2 p-3 text-sm text-ink-muted">
            <p>{q.selection.how}</p>
            {q.selection.fallback_note && <p className="mt-1 text-developing">{q.selection.fallback_note}</p>}
          </div>
        )}
        {q.selection?.fallback_note && !whyOpen && <p className="mb-4 rounded-xl bg-developing/10 px-3 py-2 text-xs text-developing">{q.selection.fallback_note}</p>}

        {loading ? (
          <Spinner />
        ) : (
          <QuestionView
            question={q}
            onSubmit={(b) => submit(b)}
            submitting={submitting}
            locked={Boolean(fb)}
            feedback={fb ? { correct: fb.correct, correct_answer: fb.correct_answer, message: fb.message } : null}
            error={err}
          />
        )}

        {hint && !fb && <div className="mt-5"><HintBox text={hint.text} source={hint.source} /></div>}

        {!fb && (
          <div className="mt-5 flex flex-wrap gap-2 border-t border-line pt-4">
            {showHintButton && (
              <Button variant="soft" size="sm" onClick={getHint} icon={<Lightbulb className="size-4" />}>
                {q.mode === "foundation" || q.mode === "guided" ? "Need a hint?" : "Hint"}
              </Button>
            )}
            <Button variant="ghost" size="sm" onClick={() => submit({ item_id: q.item_id }, true)} icon={<Eye className="size-4" />} disabled={submitting}>
              I'm stuck: show me the answer
            </Button>
          </div>
        )}

        {fb && (
          <div className="mt-6 space-y-4">
            {fb.difficulty_change && (
              <p className={cx("flex items-center gap-2 text-sm", fb.difficulty_change === "up" ? "text-strength" : "text-accent")}>
                {fb.difficulty_change === "up" ? <ArrowUp className="size-4" /> : <ArrowDown className="size-4" />}
                Next question: {fb.difficulty_next}
              </p>
            )}
            {fb.hint_used && fb.correct && <p className="flex items-center gap-2 text-xs text-ink-faint"><Sparkles className="size-3.5" /> Correct with a hint. Great; next time try it without one.</p>}
            <div className="flex justify-end">
              {fb.complete ? (
                <Button size="lg" onClick={() => setSummary(fb.summary)} icon={<Flag className="size-4" />}>
                  See summary
                </Button>
              ) : (
                <Button size="lg" onClick={load} icon={<ArrowRight className="size-4" />}>
                  Next question
                </Button>
              )}
            </div>
          </div>
        )}
      </Card>
    </div>
  );
}
