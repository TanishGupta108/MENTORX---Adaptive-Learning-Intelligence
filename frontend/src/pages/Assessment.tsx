import { useEffect, useState } from "react";
import { Link, useNavigate, useParams, useSearchParams } from "react-router";
import { ArrowRight, CalendarClock, ClipboardCheck, Clock, Flag, Info, RefreshCw, Sparkles, TrendingUp } from "lucide-react";
import { ApiError } from "../api/client";
import { tutor } from "../api/tutor";
import type { Assessment, AssessmentAnswer, Question, ReassessmentResult } from "../api/tutor";
import { useApi } from "../hooks/useApi";
import { DifficultyTag, QuestionView } from "../components/QuestionView";
import { Button, Card, ErrorState, PageLoader, pct, ProgressBar, Spinner } from "../components/ui";

const TITLES: Record<Assessment["kind"], string> = {
  diagnostic: "Diagnostic assessment",
  skill_check: "Skill check",
  reassessment: "Reassessment",
};

export function AssessmentStartPage() {
  const [params] = useSearchParams();
  const navigate = useNavigate();
  const kind = (params.get("kind") ?? "diagnostic") as Assessment["kind"];
  const skillId = params.get("skill") ? Number(params.get("skill")) : undefined;
  const skill = useApi(() => (skillId ? tutor.skill(skillId) : Promise.resolve(null)), [skillId]);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string>();

  async function start() {
    setBusy(true);
    setError(undefined);
    try {
      const a = await tutor.startAssessment(kind, skillId);
      navigate(`/assess/${a.id}`, { replace: true });
    } catch (e) {
      setError(e instanceof ApiError ? e.message : "Couldn't start. Please try again.");
      setBusy(false);
    }
  }

  const copy = {
    diagnostic: {
      lead: "Before creating your personalized learning plan, MENTORX needs to understand what you already know.",
      points: ["About 10 questions from different areas of grade 6–8 mathematics", "One question at a time, with feedback after each answer", "No time limit. A wrong answer is useful information, not a failure"],
    },
    skill_check: {
      lead: "A few questions in this skill, from easier to harder, show where to start.",
      points: ["Questions are new to you", "Feedback after each answer", "Your learning mode for this skill is set from the result"],
    },
    reassessment: {
      lead: "Fresh questions you haven't seen before measure whether your practice has paid off.",
      points: ["Only questions you've never answered", "Compared with your first answers in this skill", "Model estimates are shown separately from your results"],
    },
  }[kind];

  return (
    <div className="mx-auto max-w-2xl py-6">
      <Card className="p-8">
        <span className="grid size-12 place-items-center rounded-2xl bg-brand-soft text-brand">
          <ClipboardCheck className="size-6" />
        </span>
        <h1 className="mt-5 text-2xl font-semibold tracking-tight">
          {TITLES[kind]}
          {skill.data && <span className="text-ink-muted">: {skill.data.name}</span>}
        </h1>
        <p className="mt-3 text-ink-muted">{copy.lead}</p>
        <ul className="mt-6 space-y-2.5">
          {copy.points.map((p) => (
            <li key={p} className="flex items-start gap-3 text-sm">
              <Sparkles className="mt-0.5 size-4 shrink-0 text-accent" />
              {p}
            </li>
          ))}
        </ul>
        {error && <p className="mt-5 rounded-xl bg-danger/10 px-3 py-2 text-sm text-danger" role="alert">{error}</p>}
        <div className="mt-8 flex flex-wrap gap-3">
          <Button size="lg" onClick={start} loading={busy} icon={<ArrowRight className="size-4" />}>
            Begin
          </Button>
          <Button size="lg" variant="ghost" to="/dashboard">
            Not now
          </Button>
        </div>
      </Card>
    </div>
  );
}

export function AssessmentRunPage() {
  const { id = "" } = useParams();
  const navigate = useNavigate();
  const meta = useApi(() => tutor.assessment(id), [id]);
  const [question, setQuestion] = useState<Question | null>(null);
  const [feedback, setFeedback] = useState<AssessmentAnswer | null>(null);
  const [loadingQ, setLoadingQ] = useState(true);
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState<string>();
  const [fatal, setFatal] = useState<Error | null>(null);

  async function loadNext() {
    setLoadingQ(true);
    setFeedback(null);
    setError(undefined);
    try {
      setQuestion(await tutor.assessmentNext(id));
    } catch (e) {
      if (e instanceof ApiError && (e.code === "assessment_closed" || e.code === "assessment_complete")) {
        navigate(meta.data?.kind === "reassessment" ? `/assess/${id}/result` : "/diagnosis", { replace: true });
        return;
      }
      setFatal(e as Error);
    } finally {
      setLoadingQ(false);
    }
  }

  useEffect(() => {
    void loadNext();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [id]);

  async function submit(body: Parameters<typeof tutor.assessmentAnswer>[1]) {
    setSubmitting(true);
    setError(undefined);
    try {
      setFeedback(await tutor.assessmentAnswer(id, body));
    } catch (e) {
      setError(e instanceof ApiError ? e.message : "Couldn't submit. Please try again.");
    } finally {
      setSubmitting(false);
    }
  }

  function next() {
    if (feedback?.complete) {
      navigate(meta.data?.kind === "reassessment" ? `/assess/${id}/result` : "/diagnosis", { replace: true });
    } else {
      void loadNext();
    }
  }

  if (fatal) return <ErrorState error={fatal} onRetry={() => { setFatal(null); void loadNext(); }} />;
  if (!question || !meta.data) return <PageLoader label="Preparing your question…" />;

  const answered = feedback ? feedback.answered : (question.position ?? 1) - 1;
  const total = question.total ?? meta.data.total;

  return (
    <div className="mx-auto max-w-3xl">
      <div className="mb-6">
        <div className="mb-2 flex items-center justify-between text-sm">
          <span className="font-medium">
            {TITLES[meta.data.kind]}
            {meta.data.skill && <span className="text-ink-muted"> · {meta.data.skill.name}</span>}
          </span>
          <span className="text-ink-muted">
            Question {question.position} of {total}
          </span>
        </div>
        <ProgressBar value={answered} max={total} />
      </div>

      <Card className="p-6 sm:p-8">
        <div className="mb-5 flex flex-wrap items-center gap-2 text-xs">
          <span className="rounded-md bg-surface-3 px-2 py-0.5 font-medium text-ink-muted">{question.skill.code}</span>
          <span className="text-ink-muted">{question.skill.name}</span>
          <DifficultyTag level={question.difficulty} />
        </div>
        {question.selection?.how && (
          <p className="-mt-2 mb-5 flex items-start gap-1.5 text-xs text-ink-faint">
            <Info className="mt-px size-3.5 shrink-0" /> {question.selection.how}
          </p>
        )}
        {loadingQ ? (
          <Spinner />
        ) : (
          <QuestionView question={question} onSubmit={submit} submitting={submitting} locked={Boolean(feedback)} feedback={feedback} error={error} />
        )}
        {feedback && (
          <div className="mt-6 flex justify-end">
            <Button size="lg" onClick={next} icon={feedback.complete ? <Flag className="size-4" /> : <ArrowRight className="size-4" />}>
              {feedback.complete ? "See my results" : "Next question"}
            </Button>
          </div>
        )}
      </Card>
      <p className="mt-4 flex items-center gap-2 text-xs text-ink-faint">
        <Info className="size-3.5" /> Your progress is saved after every answer, so you can leave and come back.
      </p>
    </div>
  );
}

function Compare({ label, before, after, note }: { label: string; before: number | null | undefined; after: number | null | undefined; note: string }) {
  return (
    <div className="rounded-2xl border border-line bg-surface-2 p-4">
      <p className="text-xs font-semibold uppercase tracking-wider text-ink-faint">{label}</p>
      <div className="mt-2 flex items-baseline gap-3">
        <span className="text-2xl font-semibold text-ink-muted">{pct(before)}</span>
        <ArrowRight className="size-4 text-ink-faint" />
        <span className="text-3xl font-semibold">{pct(after)}</span>
      </div>
      <p className="mt-1 text-xs text-ink-faint">{note}</p>
    </div>
  );
}

export function ReassessmentResultPage() {
  const { id = "" } = useParams();
  const a = useApi(() => tutor.assessment(id), [id]);
  if (a.loading) return <PageLoader />;
  if (a.error) return <ErrorState error={a.error} onRetry={a.reload} />;
  const r = a.data!.result as ReassessmentResult;
  const skill = a.data!.skill!;
  const outcome = r.outcome ?? "not_improved";
  const headline = {
    improved: "Great progress! Your recent practice performance has improved.",
    progressing: "You're improving. Keep going!",
    not_improved: "Learning takes time. Let's strengthen the basics before moving ahead.",
  }[outcome];
  return (
    <div className="mx-auto max-w-3xl space-y-6">
      <Card className="p-8">
        <span className={`grid size-12 place-items-center rounded-2xl ${outcome === "not_improved" ? "bg-developing/15 text-developing" : "bg-strength/15 text-strength"}`}>
          {outcome === "not_improved" ? <RefreshCw className="size-6" /> : <TrendingUp className="size-6" />}
        </span>
        <p className="mt-5 text-sm text-ink-muted">Reassessment · {skill.name}</p>
        <h1 className="mt-1 text-2xl font-semibold tracking-tight">{headline}</h1>
        <p className="mt-2 text-ink-muted">
          You answered {r.correct} of {r.answered} fresh questions correctly.
        </p>
        <div className="mt-6 grid gap-3 sm:grid-cols-2">
          <Compare
            label="Your observed performance"
            before={r.initial_accuracy}
            after={r.reassessment_accuracy}
            note={r.initial_attempts ? `First ${r.initial_attempts} answers in this skill → this reassessment` : "No earlier answers to compare with"}
          />
          <Compare label="Model estimate (prediction)" before={r.predicted_before} after={r.predicted_after} note="DKT-Q predicted success on a typical question. A prediction, not a score." />
        </div>
      </Card>

      <Card>
        <h2 className="mb-3 font-semibold">What happens next</h2>
        {outcome === "improved" ? (
          <ul className="space-y-3 text-sm">
            <li className="flex gap-3"><TrendingUp className="size-4 text-strength" /> Your learning profile is updated, and practice in this skill now uses harder questions.</li>
            {r.completed && r.revision_due_at && (
              <li className="flex gap-3"><CalendarClock className="size-4 text-accent" /> A short revision is scheduled for {new Date(r.revision_due_at).toLocaleDateString()} to keep it fresh.</li>
            )}
            <li className="flex gap-3"><Sparkles className="size-4 text-brand" /> Your dashboard now recommends your next learning objective.</li>
          </ul>
        ) : outcome === "progressing" ? (
          <p className="text-sm text-ink-muted">You've made real gains. A little more practice at your current level should get you over the line. Then try another reassessment.</p>
        ) : (
          <ul className="space-y-3 text-sm">
            <li className="flex gap-3"><Clock className="size-4 text-developing" /> We'll review your recent mistakes and check the building blocks this skill depends on.</li>
            <li className="flex gap-3"><RefreshCw className="size-4 text-accent" /> Practice switches to Foundation mode: easier questions, worked examples and hints.</li>
            <li className="flex gap-3"><Sparkles className="size-4 text-brand" /> When you're ready, a new reassessment will use questions you haven't seen.</li>
          </ul>
        )}
        <div className="mt-6 flex flex-wrap gap-3">
          <Button to={`/skills/${skill.id}`}>{outcome === "not_improved" ? "Open the support plan" : "Back to the skill"}</Button>
          <Button variant="secondary" to="/dashboard">Go to dashboard</Button>
        </div>
      </Card>
      <p className="text-center text-xs text-ink-faint">
        <Link to="/analytics" className="hover:text-ink">See all your results in Analytics →</Link>
      </p>
    </div>
  );
}
