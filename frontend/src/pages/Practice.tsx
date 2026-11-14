import { useEffect, useState } from "react";
import { Link, useLocation, useNavigate, useParams } from "react-router";
import { ArrowRight, Bot, Eye, Flag, Lightbulb, Sparkles } from "lucide-react";
import { ApiError } from "../api/client";
import { tutor } from "../api/tutor";
import type { AnswerBody, Hint, PracticeAnswer, PracticeKind, PracticeSummary, Question } from "../api/tutor";
import { AI_THINKING, AiErrorNote, AiExplain, AiLabel, toAiError, useAiEnabled } from "../components/AiTutor";
import type { AiError } from "../components/AiTutor";
import { useProfile } from "../components/AppShell";
import { Disclosure } from "../components/Disclosure";
import { DifficultyTag, HintBox, plainHint, QuestionView } from "../components/QuestionView";
import { launchFor, useLauncher } from "../components/StartAction";
import { WhyButton } from "../components/WhyButton";
import { Button, Card, cx, ErrorState, PageLoader, pct, Ring, Spinner } from "../components/ui";

function ProgressDots({ total, results, current }: { total: number; results: (boolean | null)[]; current: number }) {
  const n = Math.max(total, results.length, 1);
  return (
    <ol className="flex flex-wrap items-center gap-1.5" aria-label={`Question ${Math.min(current + 1, n)} of ${n}`}>
      {Array.from({ length: n }, (_, i) => {
        const r = results[i];
        return (
          <li
            key={i}
            className={cx(
              "size-2.5 rounded-full",
              r === true && "bg-strength",
              r === false && "bg-weakness",
              r === null && "bg-ink-faint",
              r === undefined && (i === current ? "bg-brand ring-2 ring-brand/40 ring-offset-2 ring-offset-canvas" : "bg-line-strong"),
            )}
          />
        );
      })}
    </ol>
  );
}

const TITLES: Record<PracticeKind, string> = { skill: "Practice complete", mixed: "Mixed practice complete", review: "Review complete" };

function Summary({ s, kind, skillId }: { s: PracticeSummary; kind: PracticeKind; skillId: number | null }) {
  const { launch, busy, error } = useLauncher();
  const next = launchFor(s.next.action, skillId, s.next.skill_id);
  return (
    <Card className="mx-auto max-w-xl p-8 text-center">
      <div className="flex justify-center">
        <Ring value={s.accuracy} size={110} stroke={9} label={<span className="text-xl">{pct(s.accuracy)}</span>} color={s.accuracy >= 0.7 ? "#34d399" : s.accuracy >= 0.4 ? "#fbbf24" : "#fb7185"} />
      </div>
      <h1 className="mt-5 text-2xl font-semibold">{TITLES[kind]}</h1>
      <p className="mt-1 text-ink-muted">
        You got {s.correct} of {s.answered} right.
      </p>
      <div className="mt-6 rounded-2xl border border-line bg-surface-2 p-4 text-left">
        <p className="font-medium">{s.next.label}</p>
        <p className="mt-1 text-sm text-ink-muted">{s.next.why}</p>
      </div>
      <div className="mt-6 flex flex-wrap justify-center gap-3">
        {next && (
          <Button size="lg" onClick={() => void launch(next)} loading={busy} icon={<ArrowRight className="size-4" />}>
            {s.next.label}
          </Button>
        )}
        <Button size="lg" variant="secondary" to="/home">
          Back to Home
        </Button>
      </div>
      {error && (
        <p className="mt-3 text-sm text-developing" role="alert">
          {error}
        </p>
      )}
      {kind === "skill" && skillId !== null && (
        <Disclosure variant="plain" title="Details" className="mt-6 text-left">
          <p className="text-sm text-ink-muted">
            All your answers in this skill: {pct(s.skill_accuracy)} over {s.skill_attempts}.
          </p>
        </Disclosure>
      )}
    </Card>
  );
}

export function PracticePage() {
  const { id = "" } = useParams();
  const navigate = useNavigate();
  const location = useLocation();
  const { profile } = useProfile();
  const aiEnabled = useAiEnabled();
  const [q, setQ] = useState<Question | null>(null);
  const [fb, setFb] = useState<PracticeAnswer | null>(null);
  const [hint, setHint] = useState<Hint | null>(null);
  const [hintLoading, setHintLoading] = useState(false);
  const [aiHint, setAiHint] = useState<Hint | null>(null);
  const [aiLoading, setAiLoading] = useState(false);
  const [aiError, setAiError] = useState<AiError>();
  const [summary, setSummary] = useState<PracticeSummary | null>(null);
  const [results, setResults] = useState<(boolean | null)[]>([]);
  const [loading, setLoading] = useState(true);
  const [submitting, setSubmitting] = useState(false);
  const [err, setErr] = useState<string>();
  const [fatal, setFatal] = useState<Error | null>(null);

  const stateKind = (location.state as { kind?: PracticeKind } | null)?.kind;
  const kind: PracticeKind = q?.mixed ? "mixed" : stateKind ?? "skill";

  async function load() {
    setLoading(true);
    setFb(null);
    setHint(null);
    setAiHint(null);
    setAiError(undefined);
    setErr(undefined);
    try {
      const next = await tutor.practiceNext(id);
      setQ(next);
      // answers given before a page reload are shown as grey dots
      setResults((r) => (r.length < (next.position ?? 1) - 1 ? [...r, ...Array<null>((next.position ?? 1) - 1 - r.length).fill(null)] : r));
    } catch (e) {
      if (e instanceof ApiError && e.code === "practice_closed") {
        navigate("/home", { replace: true });
        return;
      }
      setFatal(e as Error);
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => {
    setSummary(null);
    setResults([]);
    setQ(null);
    void load();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [id]);

  async function submit(body: AnswerBody, reveal = false) {
    setSubmitting(true);
    setErr(undefined);
    try {
      const r = await tutor.practiceAnswer(id, { ...body, reveal });
      setFb(r);
      setResults((rs) => [...rs, r.revealed ? false : r.correct]);
    } catch (e) {
      setErr(e instanceof ApiError ? e.message : "Couldn't submit. Please try again.");
    } finally {
      setSubmitting(false);
    }
  }

  async function getHint() {
    setHintLoading(true);
    setErr(undefined);
    try {
      setHint(await tutor.practiceHint(id, false));
    } catch (e) {
      setErr(e instanceof ApiError ? e.message : "Couldn't load a hint.");
    } finally {
      setHintLoading(false);
    }
  }

  async function getAiHint() {
    setAiLoading(true);
    setAiError(undefined);
    try {
      setAiHint(await tutor.practiceHint(id, true));
    } catch (e) {
      setAiError(toAiError(e));
    } finally {
      setAiLoading(false);
    }
  }

  async function finishEarly() {
    try {
      const r = await tutor.practiceEnd(id);
      if (r.summary) setSummary(r.summary);
      else navigate(q && kind === "skill" ? `/skills/${q.skill.id}` : "/home");
    } catch (e) {
      setErr(e instanceof ApiError ? e.message : "Couldn't finish the session.");
    }
  }

  if (fatal) return <ErrorState error={fatal} onRetry={() => { setFatal(null); void load(); }} />;
  if (summary) return <Summary s={summary} kind={summary.mixed ? "mixed" : summary.review ? "review" : kind} skillId={kind === "skill" && q ? q.skill.id : null} />;
  if (!q) return <PageLoader label="Choosing a question for you…" />;

  const total = q.total ?? 8;
  const current = fb ? fb.answered : (q.position ?? 1) - 1;
  const canHint = profile.hints_enabled && !fb;
  const backLabel = kind === "mixed" ? "Mixed practice" : kind === "review" ? "Review" : q.skill.name;
  const backTo = kind === "skill" ? `/skills/${q.skill.id}` : "/home";
  const sel = q.selection;

  return (
    <div>
      <div className="mb-5 flex items-center justify-between gap-3">
        <Link to={backTo} className="min-w-0 truncate text-sm text-ink-muted hover:text-ink">
          ← {backLabel}
        </Link>
        <Button variant="ghost" size="sm" onClick={finishEarly} icon={<Flag className="size-4" />}>
          Finish
        </Button>
      </div>
      <div className="mb-5">
        <ProgressDots total={total} results={results} current={current} />
      </div>

      <Card className="p-5 sm:p-8">
        <div className="mb-4 flex flex-wrap items-start justify-between gap-2">
          <div className="flex flex-wrap items-center gap-2 pt-2 text-xs">
            <DifficultyTag level={sel?.served === "review" ? "review" : q.difficulty} />
            {kind !== "skill" && <span className="text-ink-muted">{q.mixed ? (q.skills ?? []).map((sk) => sk.name).join(" + ") : q.skill.name}</span>}
          </div>
          {sel?.how && (
            <WhyButton label="Why this question?" align="end" className="max-w-full sm:max-w-sm">
              <p>{sel.how}</p>
              {sel.fallback_note && <p className="mt-1.5 text-developing">{sel.fallback_note}</p>}
              {sel.technical && (
                <Disclosure variant="plain" title="Details" className="mt-1">
                  <p className="text-xs text-ink-faint">{sel.technical}</p>
                </Disclosure>
              )}
            </WhyButton>
          )}
        </div>

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

        {hint && !fb && (
          <div className="mt-5 space-y-3">
            <HintBox text={hint.text} source={hint.source} label={hint.label} note={hint.note} />
            {aiEnabled && !aiHint && !aiError && (
              <Button variant="ghost" size="sm" onClick={getAiHint} loading={aiLoading} icon={<Bot className="size-4" />}>
                {aiLoading ? AI_THINKING : "Ask the AI tutor for a more specific hint"}
              </Button>
            )}
            {aiError && <AiErrorNote error={aiError} onRetry={getAiHint} />}
            {aiHint &&
              (aiHint.ai_failed ? (
                <div className="flex flex-wrap items-center gap-2" role="status">
                  <p className="text-sm text-developing">{aiHint.note ?? "The AI tutor couldn't give a specific hint this time."}</p>
                  <Button variant="secondary" size="sm" onClick={() => { setAiHint(null); void getAiHint(); }} loading={aiLoading} icon={<Bot className="size-4" />}>
                    {aiLoading ? AI_THINKING : "Try the AI hint again"}
                  </Button>
                </div>
              ) : (
                <div className="rounded-2xl border border-accent/30 bg-accent/8 p-4 text-sm animate-rise" aria-live="polite">
                  <p className="mb-1 flex items-center gap-2 text-xs font-semibold uppercase tracking-wider text-accent">
                    <Sparkles className="size-3.5" aria-hidden /> AI tutor
                  </p>
                  <p className="whitespace-pre-line leading-6 text-ink/90">{plainHint(aiHint.text)}</p>
                  {aiHint.label && <AiLabel text={aiHint.label} />}
                </div>
              ))}
          </div>
        )}

        {!fb && (
          <div className="mt-5 flex flex-wrap gap-2 border-t border-line pt-4">
            {canHint && !hint && (
              <Button variant="soft" size="sm" onClick={getHint} loading={hintLoading} icon={<Lightbulb className="size-4" />}>
                Hint
              </Button>
            )}
            <Button variant="ghost" size="sm" onClick={() => submit({ item_id: q.item_id }, true)} icon={<Eye className="size-4" />} disabled={submitting}>
              Show me the answer
            </Button>
          </div>
        )}

        {fb && (
          <div className="mt-6 space-y-4">
            {fb.early_stop && (
              <p className="rounded-2xl border border-brand/30 bg-brand-soft p-4 text-[15px]" role="status">
                {fb.early_stop.message}
              </p>
            )}
            {!fb.early_stop && fb.difficulty_change && (
              <p className="text-sm text-ink-muted">{fb.difficulty_change === "up" ? "Nice. The next one is a little harder." : "The next one is a little easier."}</p>
            )}
            {fb.hint_used && fb.correct && <p className="text-xs text-ink-faint">Correct with a hint. Next time, try it without one.</p>}
            <AiExplain interactionId={fb.interaction_id} label={fb.correct ? "Explain with AI" : "Explain my mistake with AI"} />
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
