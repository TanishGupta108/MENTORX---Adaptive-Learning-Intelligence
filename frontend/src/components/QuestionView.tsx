/**
 * Renders one dataset question and its answer controls.
 * The question HTML is sanitised on the server (allowlist rebuild) and contains MathML,
 * which browsers render natively. Correct answers are only shown after the server has
 * accepted an answer.
 */
import { useEffect, useRef, useState } from "react";
import type { FormEvent } from "react";
import { Check, CheckCircle2, Lightbulb, X, XCircle } from "lucide-react";
import { CHOICE_TYPES } from "../api/tutor";
import type { AnswerBody, CorrectAnswer, Question } from "../api/tutor";
import { Button, cx } from "./ui";

export function Html({ html, className }: { html: string; className?: string }) {
  // Safe: produced by the server-side allowlist sanitiser (backend/app/tutor/html.py).
  return <div className={className} dangerouslySetInnerHTML={{ __html: html }} />;
}

const DIFF_STYLE: Record<string, string> = {
  easy: "text-strength bg-strength/10",
  medium: "text-developing bg-developing/10",
  hard: "text-weakness bg-weakness/10",
  unrated: "text-ink-muted bg-surface-3",
  review: "text-accent bg-accent/10",
};

export function DifficultyTag({ level }: { level: string }) {
  return <span className={cx("rounded-md px-2 py-0.5 text-xs font-medium capitalize", DIFF_STYLE[level] ?? DIFF_STYLE.unrated)}>{level}</span>;
}

type Props = {
  question: Question;
  onSubmit: (body: AnswerBody) => void;
  submitting: boolean;
  locked: boolean; // after an answer has been accepted
  feedback?: { correct: boolean; correct_answer: CorrectAnswer; message: string } | null;
  error?: string;
};

export function QuestionView({ question, onSubmit, submitting, locked, feedback, error }: Props) {
  const [value, setValue] = useState("");
  const [choice, setChoice] = useState<string | null>(null);
  const [choices, setChoices] = useState<string[]>([]);
  const inputRef = useRef<HTMLInputElement>(null);

  const typed = !CHOICE_TYPES.includes(question.answer_type);

  useEffect(() => {
    setValue("");
    setChoice(null);
    setChoices([]);
    if (typed) inputRef.current?.focus();
  }, [question.item_id, typed]);

  const ready = typed ? value.trim().length > 0 : question.answer_type === "multiple_choice" ? choice !== null : choices.length > 0;

  function submit(e: FormEvent) {
    e.preventDefault();
    if (!ready || locked || submitting) return;
    const body: AnswerBody = { item_id: question.item_id };
    if (typed) body.value = value.trim();
    else if (question.answer_type === "multiple_choice") body.choice = choice!;
    else body.choices = choices;
    onSubmit(body);
  }

  const ca = feedback?.correct_answer;
  const correctIds = ca && ca.type !== "numeric" && ca.type !== "text" ? ca.option_ids : [];

  return (
    <form onSubmit={submit} className="space-y-5">
      <Html html={question.body_html} className="question-html" />

      {typed && (
        <div className="max-w-md">
          <label className="mb-1.5 block text-sm font-medium text-ink-muted" htmlFor="answer">
            Your answer
          </label>
          <input
            id="answer"
            ref={inputRef}
            value={value}
            onChange={(e) => setValue(e.target.value)}
            disabled={locked}
            inputMode={question.answer_type === "numeric" ? "decimal" : "text"}
            autoComplete="off"
            autoCapitalize="off"
            autoCorrect="off"
            spellCheck={false}
            placeholder={question.input_hint ?? "e.g. 12, 0.5, 3/4 or 1 1/2"}
            className={cx(
              "h-12 w-full rounded-xl border bg-surface-2 px-4 text-lg tracking-wide focus:outline-none",
              feedback ? (feedback.correct ? "border-strength" : "border-weakness") : "border-line-strong focus:border-brand",
            )}
          />
          {question.answer_type === "algebraic" && (
            <p className="mt-1.5 text-xs text-ink-faint">Type powers as x^2, roots as sqrt(5), π as pi. Any equivalent answer counts unless the question asks for a particular form.</p>
          )}
        </div>
      )}

      {!typed && (
        <fieldset className="space-y-2.5">
          <legend className="mb-2 text-sm font-medium text-ink-muted">
            {question.answer_type === "check_all" ? "Select all that apply" : "Choose one answer"}
          </legend>
          {question.options.map((o, i) => {
            const selected = question.answer_type === "multiple_choice" ? choice === o.id : choices.includes(o.id);
            const isCorrect = correctIds.includes(o.id);
            return (
              <label
                key={o.id}
                className={cx(
                  "flex cursor-pointer items-center gap-3 rounded-xl border px-4 py-3 transition-colors",
                  locked && "cursor-default",
                  feedback && isCorrect && "border-strength bg-strength/8",
                  feedback && selected && !isCorrect && "border-weakness bg-weakness/8",
                  !feedback && selected && "border-brand bg-brand-soft",
                  !feedback && !selected && "border-line hover:border-line-strong hover:bg-surface-2",
                  feedback && !selected && !isCorrect && "border-line opacity-70",
                )}
              >
                <input
                  type={question.answer_type === "check_all" ? "checkbox" : "radio"}
                  name="option"
                  className="sr-only"
                  checked={selected}
                  disabled={locked}
                  onChange={() =>
                    question.answer_type === "multiple_choice"
                      ? setChoice(o.id)
                      : setChoices((cs) => (cs.includes(o.id) ? cs.filter((c) => c !== o.id) : [...cs, o.id]))
                  }
                />
                <span
                  className={cx(
                    "grid size-7 shrink-0 place-items-center border text-xs font-semibold",
                    question.answer_type === "check_all" ? "rounded-md" : "rounded-full",
                    selected ? "border-brand bg-brand text-brand-ink" : "border-line-strong text-ink-muted",
                  )}
                  aria-hidden
                >
                  {question.answer_type === "check_all" && selected ? <Check className="size-4" /> : String.fromCharCode(65 + i)}
                </span>
                <Html html={o.html} className="option-html flex-1" />
                {feedback && isCorrect && <CheckCircle2 className="size-5 text-strength" aria-label="correct option" />}
              </label>
            );
          })}
        </fieldset>
      )}

      {error && (
        <p className="text-sm text-danger" role="alert">
          {error}
        </p>
      )}

      {feedback && <FeedbackPanel feedback={feedback} />}

      {!locked && (
        <Button type="submit" size="lg" loading={submitting} disabled={!ready}>
          Submit answer
        </Button>
      )}
    </form>
  );
}

export function FeedbackPanel({ feedback }: { feedback: { correct: boolean; correct_answer: CorrectAnswer; message: string } }) {
  const ca = feedback.correct_answer;
  return (
    <div
      className={cx("flex gap-3 rounded-2xl border p-4 animate-rise", feedback.correct ? "border-strength/40 bg-strength/8" : "border-weakness/40 bg-weakness/8")}
      role="status"
      aria-live="polite"
    >
      {feedback.correct ? <CheckCircle2 className="mt-0.5 size-5 shrink-0 text-strength" /> : <XCircle className="mt-0.5 size-5 shrink-0 text-weakness" />}
      <div className="space-y-1.5">
        <p className="font-medium">{feedback.message}</p>
        {!feedback.correct && (
          <div className="text-sm text-ink-muted">
            Correct answer:{" "}
            {ca.type === "numeric" || ca.type === "text" ? (
              <span className="font-mono text-ink">{ca.values.join(" or ")}</span>
            ) : (
              <span className="inline-flex flex-wrap gap-2 align-middle">
                {ca.options_html.map((h, i) => (
                  <Html key={i} html={h} className="option-html inline rounded bg-surface-3 px-2 py-0.5 text-ink" />
                ))}
              </span>
            )}
          </div>
        )}
      </div>
    </div>
  );
}

export function HintBox({ text, source, label, note }: { text: string; source: string; label?: string; note?: string }) {
  return (
    <div className="flex gap-3 rounded-2xl border border-accent/30 bg-accent/8 p-4 text-sm animate-rise">
      <Lightbulb className="mt-0.5 size-5 shrink-0 text-accent" />
      <div>
        <p className="mb-1 text-xs font-semibold uppercase tracking-wider text-accent">Hint · {source}</p>
        {note && <p className="mb-1.5 text-xs text-developing">{note}</p>}
        <p className="leading-6 text-ink/90">{text.replace(/\*\*/g, "")}</p>
        {label && <p className="mt-2 text-[11px] text-ink-faint">{label}</p>}
      </div>
    </div>
  );
}

export function ResultIcon({ ok }: { ok: boolean }) {
  return ok ? <Check className="size-4 text-strength" /> : <X className="size-4 text-weakness" />;
}
