import { useCallback, useEffect, useRef, useState } from "react";
import type { FormEvent } from "react";
import { Link, useParams } from "react-router";
import { ApiError } from "../api/client";
import { sessions } from "../api/endpoints";
import type { AnswerResult, MasteryChange, OptionKey, Question, Session } from "../api/types";
import { isFixedSession } from "../api/types";
import { Button, ButtonLink, Card, cx, ErrorState, pct, Spinner } from "../components/ui";
import { useConceptNames } from "../hooks/useConcepts";

const TITLES = {
  diagnostic: "Diagnostic",
  practice: "Practice",
  revision: "Revision",
  pretest: "Pre-test",
  posttest: "Post-test",
} as const;

type Phase =
  | { kind: "loading" }
  | { kind: "question"; q: Question }
  | { kind: "feedback"; q: Question; picked: OptionKey | null; result: AnswerResult }
  | { kind: "done"; result?: AnswerResult }
  | { kind: "error"; error: Error };

export function SessionPage() {
  const { id = "" } = useParams();
  const [session, setSession] = useState<Session>();
  const [phase, setPhase] = useState<Phase>({ kind: "loading" });

  const finish = useCallback(
    async (result?: AnswerResult) => {
      const s = await sessions.get(id);
      setSession(s);
      setPhase({ kind: "done", result });
    },
    [id],
  );

  const loadNext = useCallback(async () => {
    setPhase({ kind: "loading" });
    try {
      setPhase({ kind: "question", q: await sessions.next(id) });
    } catch (err) {
      if (err instanceof ApiError && ["session_closed", "session_complete"].includes(err.code)) {
        await finish();
      } else setPhase({ kind: "error", error: err as Error });
    }
  }, [id, finish]);

  useEffect(() => {
    let cancelled = false;
    sessions
      .get(id)
      .then((s) => {
        if (cancelled) return;
        setSession(s);
        if (s.status === "active") void loadNext();
        else setPhase({ kind: "done" });
      })
      .catch((err: Error) => !cancelled && setPhase({ kind: "error", error: err }));
    return () => {
      cancelled = true;
    };
  }, [id, loadNext]);

  async function submit(q: Question, picked: OptionKey | null) {
    const result = await sessions.answer(id, q.question_id, picked);
    setSession((s) => (s ? { ...s, answered: result.answered } : s));
    if (result.session_complete) {
      if (session && isFixedSession(session.type)) return finish(result);
      setPhase({ kind: "feedback", q, picked, result });
      return;
    }
    if (session && isFixedSession(session.type)) return loadNext(); // no feedback in tests
    setPhase({ kind: "feedback", q, picked, result });
  }

  async function endEarly() {
    const msg =
      session?.type === "diagnostic"
        ? "End the diagnostic now? Concepts you haven't reached will be estimated from your answers so far."
        : session?.type === "pretest" || session?.type === "posttest"
          ? "End the test now? Questions you haven't answered count as not known."
          : "End this session now? Your answers so far are saved.";
    if (!window.confirm(msg)) return;
    await sessions.end(id);
    await finish();
  }

  if (phase.kind === "error") return <ErrorState error={phase.error} onRetry={() => void loadNext()} />;
  if (!session) return <Spinner label="Loading session…" />;

  const progress = session.target ? session.answered / session.target : 0;

  return (
    <div className="mx-auto max-w-2xl">
      <div className="mb-4 flex items-center justify-between gap-3">
        <div>
          <h1 className="text-xl font-semibold">{TITLES[session.type]}</h1>
          <p className="text-sm text-ink-muted">
            {Math.min(session.answered, session.target)} of {session.target} answered
          </p>
        </div>
        {session.status === "active" && phase.kind !== "done" && (
          <Button variant="ghost" onClick={() => void endEarly()}>
            End session
          </Button>
        )}
      </div>
      <div
        className="mb-6 h-1.5 overflow-hidden rounded-full bg-line"
        role="progressbar"
        aria-label="Session progress"
        aria-valuenow={Math.round(progress * 100)}
        aria-valuemin={0}
        aria-valuemax={100}
      >
        <div className="h-full bg-brand transition-all" style={{ width: `${progress * 100}%` }} />
      </div>

      {phase.kind === "loading" && <Spinner label="Choosing your next question…" />}
      {phase.kind === "question" && (
        <QuestionCard
          key={phase.q.question_id}
          q={phase.q}
          diagnostic={isFixedSession(session.type)}
          onSubmit={(picked) => submit(phase.q, picked)}
        />
      )}
      {phase.kind === "feedback" && (
        <FeedbackCard
          q={phase.q}
          picked={phase.picked}
          result={phase.result}
          onNext={() => (phase.result.session_complete ? void finish(phase.result) : void loadNext())}
        />
      )}
      {phase.kind === "done" && <Summary session={session} result={phase.result} />}
    </div>
  );
}

function QuestionCard({
  q,
  diagnostic,
  onSubmit,
}: {
  q: Question;
  diagnostic: boolean;
  onSubmit: (picked: OptionKey | null) => Promise<void>;
}) {
  const [picked, setPicked] = useState<OptionKey | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string>();
  const heading = useRef<HTMLHeadingElement>(null);

  useEffect(() => heading.current?.focus(), []);

  async function send(choice: OptionKey | null) {
    if (busy) return;
    setBusy(true);
    setError(undefined);
    try {
      await onSubmit(choice);
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Couldn't send your answer. Try again.");
      setBusy(false);
    }
  }

  // Keyboard: A–D or 1–4 to pick an option.
  useEffect(() => {
    function onKey(e: KeyboardEvent) {
      if (e.target instanceof HTMLTextAreaElement || e.target instanceof HTMLInputElement) return;
      if (e.metaKey || e.ctrlKey || e.altKey) return;
      const k = e.key.toUpperCase();
      const idx = "1234".indexOf(k);
      const key = (idx >= 0 ? "ABCD"[idx] : k) as OptionKey;
      if (q.options.some((o) => o.key === key)) setPicked(key);
    }
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [q]);

  return (
    <Card>
      <p className="text-sm text-ink-muted">
        Question {q.position} of {q.total} · {q.concept_name}
      </p>
      <form
        onSubmit={(e: FormEvent) => {
          e.preventDefault();
          if (picked) void send(picked);
        }}
      >
        <fieldset className="mt-2">
          <legend>
            <h2
              ref={heading}
              tabIndex={-1}
              className="whitespace-pre-line text-lg font-medium leading-relaxed outline-none"
            >
              {q.stem}
            </h2>
          </legend>
          <div className="mt-4 space-y-2">
            {q.options.map((o) => (
              <label
                key={o.key}
                className={cx(
                  "flex min-h-12 cursor-pointer items-start gap-3 rounded-lg border p-3 transition",
                  picked === o.key ? "border-brand bg-brand/5" : "border-line hover:bg-canvas",
                )}
              >
                <input
                  type="radio"
                  name="answer"
                  value={o.key}
                  checked={picked === o.key}
                  onChange={() => setPicked(o.key)}
                  className="mt-1 size-4 shrink-0 accent-brand"
                />
                <span>
                  <span className="mr-2 font-semibold">{o.key}.</span>
                  <span className="whitespace-pre-line">{o.text}</span>
                </span>
              </label>
            ))}
          </div>
        </fieldset>
        {error && (
          <p role="alert" className="mt-3 text-sm text-danger">
            {error}
          </p>
        )}
        <div className="mt-5 flex flex-wrap items-center gap-3">
          <Button type="submit" disabled={!picked || busy}>
            {busy ? "Sending…" : diagnostic ? "Next" : "Check answer"}
          </Button>
          {q.allow_dont_know && (
            <Button variant="secondary" disabled={busy} onClick={() => void send(null)}>
              I don't know yet
            </Button>
          )}
          <FlagQuestion questionId={q.question_id} />
        </div>
      </form>
    </Card>
  );
}

function FlagQuestion({ questionId }: { questionId: number }) {
  const [open, setOpen] = useState(false);
  const [comment, setComment] = useState("");
  const [state, setState] = useState<"idle" | "sending" | "sent" | "error">("idle");
  if (state === "sent") return <span className="text-sm text-ink-muted">Thanks, reported.</span>;
  if (!open)
    return (
      <button
        type="button"
        className="ml-auto min-h-11 text-sm text-ink-muted underline-offset-2 hover:underline"
        onClick={() => setOpen(true)}
      >
        Report a problem
      </button>
    );
  return (
    <div className="w-full rounded-lg border border-line p-3">
      <label className="text-sm font-medium" htmlFor={`flag-${questionId}`}>
        What's wrong with this question?
      </label>
      <textarea
        id={`flag-${questionId}`}
        className="mt-1 block w-full rounded-lg border border-line bg-surface p-2 text-sm"
        rows={2}
        maxLength={1000}
        value={comment}
        onChange={(e) => setComment(e.target.value)}
      />
      <div className="mt-2 flex gap-2">
        <Button
          variant="secondary"
          disabled={state === "sending"}
          onClick={async () => {
            setState("sending");
            try {
              await sessions.flag(questionId, comment);
              setState("sent");
            } catch {
              setState("error");
            }
          }}
        >
          Send report
        </Button>
        <Button variant="ghost" onClick={() => setOpen(false)}>
          Cancel
        </Button>
      </div>
      {state === "error" && <p className="mt-2 text-xs text-danger">Couldn't send. Try again.</p>}
    </div>
  );
}

function FeedbackCard({
  q,
  picked,
  result,
  onNext,
}: {
  q: Question;
  picked: OptionKey | null;
  result: AnswerResult;
  onNext: () => void;
}) {
  const fb = result.feedback;
  const next = useRef<HTMLButtonElement>(null);
  useEffect(() => next.current?.focus(), []);
  if (!fb) return null;
  const correctText = q.options.find((o) => o.key === fb.correct_key)?.text;
  return (
    <Card>
      <div role="status" aria-live="polite">
        <p className={cx("text-lg font-semibold", fb.correct ? "text-success" : "text-danger")}>
          {fb.correct ? "Correct" : picked ? "Not quite" : "Here's the answer"}
        </p>
        <p className="mt-1 text-sm text-ink-muted">
          {picked && !fb.correct ? `You chose ${picked}. ` : ""}
          The answer is <strong className="text-ink">{fb.correct_key}</strong>
          {correctText ? `: ${correctText}` : ""}
        </p>
      </div>
      <p className="mt-4 whitespace-pre-line leading-relaxed">{fb.explanation}</p>
      {result.mastery && (
        <div className="mt-4 rounded-lg bg-canvas p-3 text-sm">
          <MasteryDelta change={result.mastery} name={q.concept_name} />
        </div>
      )}
      {result.goal?.just_met && <GoalBanner goal={result.goal} />}
      <Button ref={next} className="mt-5" onClick={onNext}>
        {result.session_complete ? "See results" : "Next question"}
      </Button>
    </Card>
  );
}

/** FR-ENG-03: shown when today's goal of valid answers is reached. */
function GoalBanner({ goal }: { goal: NonNullable<AnswerResult["goal"]> }) {
  return (
    <p role="status" className="mt-4 rounded-lg border border-success/40 bg-success/10 p-3 text-sm">
      <strong>Daily goal reached!</strong> {goal.today_valid} questions today · {goal.current_streak}
      -day streak
    </p>
  );
}

export function MasteryDelta({ change, name }: { change: MasteryChange; name?: string }) {
  const diff = change.before == null ? null : change.after - change.before;
  return (
    <span>
      {name ?? change.concept}:{" "}
      {change.before == null ? "" : <span className="tabular-nums">{pct(change.before)} → </span>}
      <strong className="tabular-nums">{pct(change.after)}</strong>
      {diff != null && Math.abs(diff) >= 0.005 && (
        <span className={cx("ml-2 tabular-nums", diff > 0 ? "text-success" : "text-danger")}>
          ({diff > 0 ? "+" : "−"}
          {Math.round(Math.abs(diff) * 100)} pts)
        </span>
      )}
    </span>
  );
}

function Summary({ session, result }: { session: Session; result?: AnswerResult }) {
  const names = useConceptNames();
  const accuracy = session.correct != null && session.answered ? session.correct / session.answered : null;
  return (
    <Card>
      <h2 className="text-lg font-semibold">
        {session.status === "abandoned" ? "This session was replaced" : "Session complete"}
      </h2>
      {result?.goal?.goal_met_today && <GoalBanner goal={result.goal} />}
      {isFixedSession(session.type) ? (
        <>
          {session.type !== "diagnostic" && (
            <p className="mt-1 text-ink-muted">
              Thank you! Your answers are saved for the study.
              {session.type === "posttest" && (
                <>
                  {" "}
                  One last step: a short{" "}
                  <Link to="/survey" className="font-medium text-brand">
                    usability questionnaire
                  </Link>
                  .
                </>
              )}
            </p>
          )}
          {(session.type === "diagnostic" || result?.summary) && (
            <p className="mt-1 text-ink-muted">
              Your starting profile is ready: MENTORX has estimated your mastery of every concept.
            </p>
          )}
          {result?.summary && (
            <div className="mt-4 grid gap-4 sm:grid-cols-2">
              <ConceptList title="Strongest" items={result.summary.strongest} />
              <ConceptList title="Most room to grow" items={result.summary.weakest} />
            </div>
          )}
        </>
      ) : (
        <>
          <p className="mt-1 text-ink-muted">
            {session.answered} question{session.answered === 1 ? "" : "s"} answered
            {accuracy != null ? `, ${pct(accuracy)} correct` : ""}.
          </p>
          {session.changes && session.changes.length > 0 && (
            <div className="mt-4">
              <h3 className="text-sm font-medium">Mastery before → after</h3>
              <ul className="mt-2 space-y-1 text-sm">
                {session.changes.map((c) => (
                  <li key={c.concept}>
                    <MasteryDelta change={c} name={names[c.concept]} />
                  </li>
                ))}
              </ul>
            </div>
          )}
        </>
      )}
      <div className="mt-6 flex flex-wrap gap-3">
        <ButtonLink to="/path">See your learning path</ButtonLink>
        <ButtonLink to="/dashboard" variant="secondary">
          Dashboard
        </ButtonLink>
      </div>
      <p className="mt-4 text-xs text-ink-muted">
        Mastery is the model's estimate of your chance of answering a typical new question on a
        concept correctly. <Link className="underline" to="/concepts">See all concepts</Link>.
      </p>
    </Card>
  );
}


function ConceptList({ title, items }: { title: string; items: { name: string; mastery: number }[] }) {
  return (
    <div>
      <h3 className="text-sm font-medium">{title}</h3>
      <ul className="mt-2 space-y-1 text-sm">
        {items.map((c) => (
          <li key={c.name} className="flex justify-between gap-3">
            <span>{c.name}</span>
            <span className="tabular-nums text-ink-muted">{pct(c.mastery)}</span>
          </li>
        ))}
      </ul>
    </div>
  );
}
