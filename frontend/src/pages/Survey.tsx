import { useState } from "react";
import { ApiError } from "../api/client";
import { pilot } from "../api/endpoints";
import type { PilotStatus } from "../api/types";
import { Button, ButtonLink, Card, cx, EmptyState, ErrorState, Field, inputClass, PageHeader, Spinner } from "../components/ui";
import { useApi } from "../hooks/useApi";

/** The 10 standard System Usability Scale statements (Brooke, 1996), FR-PILOT-04. */
export const SUS_ITEMS = [
  "I think that I would like to use MENTORX frequently.",
  "I found MENTORX unnecessarily complex.",
  "I thought MENTORX was easy to use.",
  "I think that I would need the support of a technical person to be able to use MENTORX.",
  "I found the various functions in MENTORX were well integrated.",
  "I thought there was too much inconsistency in MENTORX.",
  "I would imagine that most people would learn to use MENTORX very quickly.",
  "I found MENTORX very cumbersome to use.",
  "I felt very confident using MENTORX.",
  "I needed to learn a lot of things before I could get going with MENTORX.",
];

const SCALE = [
  { value: 1, label: "Strongly disagree" },
  { value: 2, label: "Disagree" },
  { value: 3, label: "Neutral" },
  { value: 4, label: "Agree" },
  { value: 5, label: "Strongly agree" },
];

export function SurveyPage() {
  const status = useApi((s) => pilot.status(s));
  if (status.loading && !status.data) return <Spinner />;
  if (status.error) return <ErrorState error={status.error} onRetry={status.reload} />;
  return (
    <>
      <PageHeader title="Usability questionnaire">
        10 short statements about your experience. There are no right or wrong answers.
      </PageHeader>
      <SurveyBody s={status.data as PilotStatus} />
    </>
  );
}

function SurveyBody({ s }: { s: PilotStatus }) {
  const [answers, setAnswers] = useState<(number | null)[]>(Array(10).fill(null));
  const [comment, setComment] = useState("");
  const [state, setState] = useState<"idle" | "sending" | "done">(s.sus_done ? "done" : "idle");
  const [error, setError] = useState("");

  if (state === "done")
    return (
      <EmptyState title="Thank you!">
        Your answers are saved. You can keep using MENTORX as long as you like.
        <div className="mt-4">
          <ButtonLink to="/dashboard">Back to the dashboard</ButtonLink>
        </div>
      </EmptyState>
    );
  if (s.posttest.status !== "done")
    return (
      <EmptyState title="Not yet">The questionnaire opens after you've taken the post-test.</EmptyState>
    );

  async function send(e: React.FormEvent) {
    e.preventDefault();
    const missing = answers.findIndex((a) => a == null);
    if (missing >= 0) {
      setError(`Please answer statement ${missing + 1}.`);
      return;
    }
    setState("sending");
    setError("");
    try {
      await pilot.sus(answers as number[], comment.trim());
      setState("done");
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Couldn't send. Try again.");
      setState("idle");
    }
  }

  return (
    <form onSubmit={send} noValidate className="space-y-4">
      {SUS_ITEMS.map((text, i) => (
        <Card key={i}>
          <fieldset>
            <legend className="font-medium">
              {i + 1}. {text}
            </legend>
            <div className="mt-3 grid grid-cols-5 gap-2">
              {SCALE.map((o) => (
                <label
                  key={o.value}
                  className={cx(
                    "flex min-h-11 cursor-pointer flex-col items-center justify-center rounded-lg border p-2 text-center text-xs",
                    answers[i] === o.value ? "border-brand bg-brand/10 text-brand" : "border-line hover:bg-canvas",
                  )}
                >
                  <input
                    type="radio"
                    className="sr-only"
                    name={`sus-${i}`}
                    value={o.value}
                    checked={answers[i] === o.value}
                    onChange={() => setAnswers((a) => a.map((x, j) => (j === i ? o.value : x)))}
                  />
                  <span className="text-base font-semibold">{o.value}</span>
                  <span className="hidden sm:block">{o.label}</span>
                </label>
              ))}
            </div>
            <p className="mt-1 flex justify-between text-xs text-ink-muted sm:hidden">
              <span>Strongly disagree</span>
              <span>Strongly agree</span>
            </p>
          </fieldset>
        </Card>
      ))}
      <Card>
        <Field label="Anything else you'd like to tell us? (optional)">
          <textarea
            className={cx(inputClass, "min-h-24 py-2")}
            maxLength={2000}
            value={comment}
            onChange={(e) => setComment(e.target.value)}
          />
        </Field>
      </Card>
      {error && (
        <p role="alert" className="text-sm text-danger">
          {error}
        </p>
      )}
      <Button type="submit" disabled={state === "sending"}>
        {state === "sending" ? "Sending…" : "Submit questionnaire"}
      </Button>
    </form>
  );
}
