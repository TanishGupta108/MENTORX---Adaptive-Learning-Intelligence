/**
 * Renders one dataset question and its answer controls.
 * The question HTML is sanitised on the server (allowlist rebuild) and contains MathML,
 * which browsers render natively. Correct answers are only shown after the server has
 * accepted an answer.
 */
import { useEffect, useRef, useState } from "react";
import type { FormEvent } from "react";
import { ArrowDown, ArrowUp, Check, CheckCircle2, Lightbulb, X, XCircle } from "lucide-react";
import { isTyped } from "../api/tutor";
import type { AnswerBody, CorrectAnswer, Question } from "../api/tutor";
import { MapQuestion } from "./MapQuestion";
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

/** Items shown in a given order, numbered (ordering answers). */
export function OrderedItems({ items, className }: { items: string[]; className?: string }) {
  return (
    <ol className={cx("inline-flex flex-wrap items-center gap-x-1.5 gap-y-1 align-middle", className)}>
      {items.map((h, i) => (
        <li key={i} className="inline-flex items-center gap-1">
          <span className="text-xs text-ink-faint">{i + 1}.</span>
          <Html html={h} className="option-html inline rounded bg-surface-3 px-2 py-0.5 text-ink" />
        </li>
      ))}
    </ol>
  );
}

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
  const [order, setOrder] = useState<string[]>(() => question.options.map((o) => o.id));
  const inputRef = useRef<HTMLInputElement>(null);

  const typed = isTyped(question.answer_type);
  const ordering = question.answer_type === "ordering";

  useEffect(() => {
    setValue("");
    setChoice(null);
    setChoices([]);
    setOrder(question.options.map((o) => o.id));
    if (typed) inputRef.current?.focus();
    // only a new question resets the answer (not a re-render of the same one)
  }, [question.item_id, typed]);

  const ready = typed
    ? value.trim().length > 0
    : ordering
      ? order.length > 1
      : question.answer_type === "multiple_choice"
        ? choice !== null
        : choices.length > 0;

  function move(index: number, by: -1 | 1) {
    setOrder((o) => {
      const j = index + by;
      if (j < 0 || j >= o.length) return o;
      const next = o.filter((_, k) => k !== index);
      next.splice(j, 0, o[index]!);
      return next;
    });
  }

  function submit(e: FormEvent) {
    e.preventDefault();
    if (!ready || locked || submitting) return;
    const body: AnswerBody = { item_id: question.item_id };
    if (typed) body.value = value.trim();
    else if (ordering) body.choices = order;
    else if (question.answer_type === "multiple_choice") body.choice = choice!;
    else body.choices = choices;
    onSubmit(body);
  }

  const ca = feedback?.correct_answer;
  const correctIds = ca && ca.type !== "numeric" && ca.type !== "text" ? ca.option_ids : [];
  const map = question.media?.kind === "map" ? question.media : null;
  // "Where is X?" map questions: the options are just the letters drawn on the map.
  const letterOptions = Boolean(map?.regions.some((r) => r.label)) && question.answer_type === "multiple_choice";

  return (
    <form onSubmit={submit} className="space-y-5">
      <Html html={question.body_html} className="question-html" />

      {map && (
        <MapQuestion
          media={map}
          selected={choice}
          onSelect={letterOptions ? (label) => setChoice(label) : undefined}
          disabled={locked}
          answered={Boolean(feedback)}
          correctIds={correctIds}
        />
      )}

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
              "h-12 w-full rounded-[var(--radius-control)] border bg-surface-2 px-4 text-lg disabled:cursor-not-allowed",
              feedback ? (feedback.correct ? "border-strength" : "border-weakness") : "border-line-strong",
            )}
          />
          {question.input_hint && question.answer_type !== "algebraic" && (
            // the placeholder is cut off on narrow fields and disappears while typing
            <p className="mt-1.5 text-xs text-ink-faint">{question.input_hint}</p>
          )}
          {question.answer_type === "algebraic" && (
            <p className="mt-1.5 text-xs text-ink-faint">Type powers as x^2, roots as sqrt(5), π as pi. Any equivalent answer counts unless the question asks for a particular form.</p>
          )}
        </div>
      )}

      {ordering && (
        <fieldset>
          <legend className="mb-2 text-sm font-medium text-ink-muted">Put the items in order with the arrows (top = first)</legend>
          <ol className="space-y-2.5">
            {order.map((id, i) => {
              const o = question.options.find((x) => x.id === id);
              const right = feedback ? correctIds[i] === id : null;
              return (
                <li
                  key={id}
                  className={cx(
                    "flex min-h-12 items-center gap-3 rounded-xl border px-3 py-2",
                    right === true && "border-strength bg-strength/8",
                    right === false && "border-weakness bg-weakness/8",
                    right === null && "border-line",
                  )}
                >
                  <span className="grid size-7 shrink-0 place-items-center rounded-full border border-line-strong text-xs font-semibold text-ink-muted" aria-hidden>
                    {i + 1}
                  </span>
                  <Html html={o?.html ?? ""} className="option-html flex-1" />
                  {!locked && (
                    <span className="flex shrink-0 gap-1">
                      <button type="button" className="grid size-9 place-items-center rounded-lg border border-line hover:bg-surface-2 disabled:opacity-40" onClick={() => move(i, -1)} disabled={i === 0} aria-label={`Move item ${i + 1} up`}>
                        <ArrowUp className="size-4" />
                      </button>
                      <button type="button" className="grid size-9 place-items-center rounded-lg border border-line hover:bg-surface-2 disabled:opacity-40" onClick={() => move(i, 1)} disabled={i === order.length - 1} aria-label={`Move item ${i + 1} down`}>
                        <ArrowDown className="size-4" />
                      </button>
                    </span>
                  )}
                </li>
              );
            })}
          </ol>
        </fieldset>
      )}

      {!typed && !ordering && (
        <fieldset className={cx(letterOptions ? "grid grid-cols-2 gap-2.5 sm:grid-cols-4" : "space-y-2.5")}>
          <legend className="mb-2 text-sm font-medium text-ink-muted">
            {question.answer_type === "check_all" ? "Select all that apply" : letterOptions ? "Choose the letter on the map" : "Choose one answer"}
          </legend>
          {question.options.map((o, i) => {
            const selected = question.answer_type === "multiple_choice" ? choice === o.id : choices.includes(o.id);
            const isCorrect = correctIds.includes(o.id);
            return (
              <label
                key={o.id}
                className={cx(
                  "flex min-h-12 cursor-pointer items-center gap-3 rounded-xl border px-4 py-3 transition-colors has-[:focus-visible]:outline-2 has-[:focus-visible]:outline-offset-2 has-[:focus-visible]:outline-brand has-[:focus-visible]:outline-solid",
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
                    letterOptions && "sr-only",
                  )}
                  aria-hidden
                >
                  {question.answer_type === "check_all" && selected ? <Check className="size-4" /> : String.fromCharCode(65 + i)}
                </span>
                <Html html={o.html} className={cx("option-html flex-1", letterOptions && "text-center text-lg font-semibold")} />
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
      className={cx("flex gap-3 rounded-xl p-4 animate-rise", feedback.correct ? "bg-strength/10" : "bg-weakness/10")}
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
            ) : ca.type === "ordering" ? (
              <OrderedItems items={ca.options_html} />
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

/** Hint text from Markdown notes: no bold markers, list dashes as bullets (line breaks kept). */
export function plainHint(text: string) {
  return text.replace(/\*\*/g, "").replace(/^\s*[-*]\s+/gm, "• ");
}

export function HintBox({ text, source, label, note }: { text: string; source: string; label?: string; note?: string }) {
  return (
    <div className="flex gap-3 rounded-xl bg-surface-2 p-4 text-sm animate-rise">
      <Lightbulb className="mt-0.5 size-5 shrink-0 text-ink-muted" aria-hidden />
      <div>
        <p className="mb-1 text-sm font-medium text-ink-muted">Hint: {source}</p>
        {note && <p className="mb-1.5 text-xs text-developing">{note}</p>}
        <p className="whitespace-pre-line leading-6 text-ink">{plainHint(text)}</p>
        {label && <p className="mt-2 text-[11px] text-ink-faint">{label}</p>}
      </div>
    </div>
  );
}

export function ResultIcon({ ok }: { ok: boolean }) {
  return ok ? <Check className="size-4 text-strength" /> : <X className="size-4 text-weakness" />;
}
