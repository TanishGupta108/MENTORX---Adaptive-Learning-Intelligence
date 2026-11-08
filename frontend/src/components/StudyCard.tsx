import { useState } from "react";
import { ApiError } from "../api/client";
import { me } from "../api/endpoints";
import type { PilotStatus } from "../api/types";
import { useAuth } from "../auth/AuthContext";
import { useStartSession } from "../hooks/useStartSession";
import { Button, ButtonLink, Card } from "./ui";

const DISMISS_KEY = "mentorx.study.dismissed";

function dismissed() {
  try {
    return localStorage.getItem(DISMISS_KEY) === "1";
  } catch {
    return false;
  }
}

/** The pilot study's next step for this student (FR-PILOT-02/04). Never shows the group. */
export function StudyCard({ s, onChange }: { s: PilotStatus; onChange: () => void }) {
  const { setUser } = useAuth();
  const starter = useStartSession();
  const [hidden, setHidden] = useState(dismissed);
  const [error, setError] = useState("");

  if (!s.in_study) return null;

  if (!s.consented) {
    if (hidden) return null;
    return (
      <Card className="mb-6 border-brand/40" title="You're invited to the MENTORX study">
        <p className="text-sm">
          We're testing whether MENTORX helps students learn. Taking part means:
        </p>
        <ul className="mt-2 list-disc space-y-1 pl-5 text-sm">
          <li>a 19-question pre-test now, which also sets up your starting profile;</li>
          <li>using MENTORX as you normally would;</li>
          <li>a 19-question post-test and a 10-statement questionnaire at the end.</li>
        </ul>
        <p className="mt-2 text-sm text-ink-muted">
          Your answers are used for research only in pseudonymised form: no name or email. Taking
          part is voluntary and you can withdraw at any time in Settings.
        </p>
        {error && (
          <p role="alert" className="mt-2 text-sm text-danger">
            {error}
          </p>
        )}
        <div className="mt-4 flex flex-wrap gap-2">
          <Button
            onClick={async () => {
              setError("");
              try {
                setUser(await me.update({ consent_research: true }));
                onChange();
              } catch (err) {
                setError(err instanceof ApiError ? err.message : "Couldn't save. Try again.");
              }
            }}
          >
            I agree to take part
          </Button>
          <Button
            variant="ghost"
            onClick={() => {
              try {
                localStorage.setItem(DISMISS_KEY, "1");
              } catch {
                /* private mode: hide for this visit only */
              }
              setHidden(true);
            }}
          >
            Not now
          </Button>
        </div>
      </Card>
    );
  }

  const test = (kind: "pretest" | "posttest", title: string, body: string) => {
    const st = kind === "pretest" ? s.pretest : s.posttest;
    return (
      <Card className="mb-6 border-brand/40" title={title}>
        <p className="text-sm">{body}</p>
        <p className="mt-1 text-sm text-ink-muted">
          {st.questions} questions, one per concept, about 15 minutes. No feedback until the end, so
          just answer as well as you can. "I don't know yet" is fine.
        </p>
        {starter.error && (
          <p role="alert" className="mt-2 text-sm text-danger">
            {starter.error}
          </p>
        )}
        <Button className="mt-4" disabled={starter.busy !== null} onClick={() => starter.start(kind)}>
          {st.status === "in_progress" ? "Resume the test" : "Start the test"}
        </Button>
      </Card>
    );
  };

  if (s.pretest.status === "todo" || s.pretest.status === "in_progress")
    return test(
      "pretest",
      "Study step 1: the pre-test",
      "Thanks for taking part! This short test measures where you're starting from.",
    );
  if (s.posttest.status === "todo" || s.posttest.status === "in_progress")
    return test(
      "posttest",
      "Study final step: the post-test",
      "The study is ending. This test measures how much you've learned.",
    );
  if (s.posttest.status === "done" && !s.sus_done)
    return (
      <Card className="mb-6 border-brand/40" title="One last thing: a 2-minute questionnaire">
        <p className="text-sm">10 statements about how easy MENTORX was to use.</p>
        <ButtonLink to="/survey" className="mt-4">
          Open the questionnaire
        </ButtonLink>
      </Card>
    );
  return null;
}

/** True when the pre-test replaces the diagnostic for this student. */
export function pretestPending(s: PilotStatus | undefined) {
  return !!s && s.in_study && s.consented && s.pretest.status !== "done" && s.pretest.status !== "unavailable";
}
