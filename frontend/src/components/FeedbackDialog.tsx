import { useEffect, useRef, useState } from "react";
import { useLocation } from "react-router";
import { engagement } from "../api/endpoints";
import type { FeedbackCategory } from "../api/types";
import { Button, cx, Field, inputClass } from "./ui";

const CATEGORIES: { value: FeedbackCategory; label: string }[] = [
  { value: "bug", label: "Something isn't working" },
  { value: "content", label: "A question or explanation" },
  { value: "idea", label: "An idea" },
  { value: "other", label: "Something else" },
];

/** FR-PILOT-03: a 1–5 rating, a category and a message, from any page. */
export function FeedbackDialog({ onClose }: { onClose: () => void }) {
  const { pathname } = useLocation();
  const [rating, setRating] = useState<number | null>(null);
  const [category, setCategory] = useState<FeedbackCategory>("idea");
  const [message, setMessage] = useState("");
  const [state, setState] = useState<"idle" | "sending" | "sent" | "error">("idle");
  const [error, setError] = useState("");
  const first = useRef<HTMLButtonElement>(null);

  useEffect(() => {
    first.current?.focus();
    const onKey = (e: KeyboardEvent) => e.key === "Escape" && onClose();
    document.addEventListener("keydown", onKey);
    return () => document.removeEventListener("keydown", onKey);
  }, [onClose]);

  async function send(e: React.FormEvent) {
    e.preventDefault();
    if (rating == null) {
      setError("Pick a rating from 1 to 5.");
      return;
    }
    setState("sending");
    try {
      await engagement.feedback({ rating, category, message: message.trim(), page: pathname });
      setState("sent");
    } catch (err) {
      setError(err instanceof Error ? err.message : "Couldn't send. Try again.");
      setState("error");
    }
  }

  return (
    <div
      className="fixed inset-0 z-50 flex items-end justify-center bg-black/40 p-4 sm:items-center"
      onMouseDown={(e) => e.target === e.currentTarget && onClose()}
    >
      <div
        role="dialog"
        aria-modal="true"
        aria-labelledby="feedback-title"
        className="w-full max-w-md rounded-xl border border-line bg-surface p-5 shadow-lg"
      >
        <h2 id="feedback-title" className="text-lg font-semibold">
          Send feedback
        </h2>
        {state === "sent" ? (
          <div role="status">
            <p className="mt-3">Thank you! The team reads every message.</p>
            <Button className="mt-5" onClick={onClose}>
              Close
            </Button>
          </div>
        ) : (
          <form onSubmit={send} className="mt-4 space-y-4" noValidate>
            <fieldset>
              <legend className="text-sm font-medium">How is MENTORX working for you?</legend>
              <div className="mt-2 flex gap-2" role="radiogroup" aria-label="Rating from 1 to 5">
                {[1, 2, 3, 4, 5].map((n) => (
                  <button
                    key={n}
                    ref={n === 1 ? first : undefined}
                    type="button"
                    role="radio"
                    aria-checked={rating === n}
                    aria-label={`${n} out of 5`}
                    onClick={() => {
                      setRating(n);
                      setError("");
                    }}
                    className={cx(
                      "min-h-11 min-w-11 rounded-lg border text-sm font-medium",
                      rating === n
                        ? "border-brand bg-brand text-brand-ink"
                        : "border-line hover:bg-canvas",
                    )}
                  >
                    {n}
                  </button>
                ))}
              </div>
              <p className="mt-1 text-xs text-ink-muted">1 = poor, 5 = excellent</p>
            </fieldset>
            <Field label="What is it about?">
              <select
                className={inputClass}
                value={category}
                onChange={(e) => setCategory(e.target.value as FeedbackCategory)}
              >
                {CATEGORIES.map((c) => (
                  <option key={c.value} value={c.value}>
                    {c.label}
                  </option>
                ))}
              </select>
            </Field>
            <Field label="Message (optional)" hint={`${message.length} / 2000`}>
              <textarea
                className={cx(inputClass, "min-h-24 py-2")}
                maxLength={2000}
                value={message}
                onChange={(e) => setMessage(e.target.value)}
              />
            </Field>
            {error && (
              <p role="alert" className="text-sm text-danger">
                {error}
              </p>
            )}
            <div className="flex justify-end gap-2">
              <Button variant="ghost" onClick={onClose}>
                Cancel
              </Button>
              <Button type="submit" disabled={state === "sending"}>
                {state === "sending" ? "Sending…" : "Send"}
              </Button>
            </div>
          </form>
        )}
      </div>
    </div>
  );
}
