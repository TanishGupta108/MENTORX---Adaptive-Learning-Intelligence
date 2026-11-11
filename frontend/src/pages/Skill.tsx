import { useState } from "react";
import type { ReactNode } from "react";
import { useNavigate, useParams } from "react-router";
import { AlertCircle, ArrowRight, BookOpenText, ClipboardCheck, GitBranch, History, Layers, LifeBuoy, PenLine, PlayCircle, Sparkles, Target, Video } from "lucide-react";
import { ApiError } from "../api/client";
import { tutor } from "../api/tutor";
import type { Mode, SkillDetail } from "../api/tutor";
import { useApi } from "../hooks/useApi";
import { useProfile } from "../components/AppShell";
import { Html } from "../components/QuestionView";
import { Markdown } from "../components/Markdown";
import { ResourceCard } from "../components/ResourceCard";
import { SkillCard } from "../components/SkillCard";
import { Button, Card, CardTitle, cx, ErrorState, EvidenceMeter, ModeBadge, ModelEstimate, PageLoader, pct, StatusBadge } from "../components/ui";

const MODES: { id: Mode; label: string; text: string }[] = [
  { id: "foundation", label: "Foundation", text: "More explanation, basic examples, easy questions, hints offered" },
  { id: "guided", label: "Guided", text: "Explanations and worked examples, easy to medium questions" },
  { id: "independent", label: "Independent", text: "Medium to hard questions, less assistance" },
  { id: "advanced", label: "Advanced", text: "Challenging, application-based questions" },
];

function Step({ n, icon, title, children, done }: { n: number; icon: ReactNode; title: string; children: ReactNode; done?: boolean }) {
  return (
    <li className="relative pl-12">
      <span className={cx("absolute left-0 top-0 grid size-9 place-items-center rounded-xl border text-sm font-semibold", done ? "border-strength/40 bg-strength/10 text-strength" : "border-line bg-surface-2 text-brand")}>
        {icon}
      </span>
      <p className="text-[11px] font-semibold uppercase tracking-wider text-ink-faint">Step {n}</p>
      <h3 className="font-semibold">{title}</h3>
      <div className="mt-3">{children}</div>
    </li>
  );
}

function keyIdea(md: string | null | undefined) {
  if (!md) return null;
  const m = md.match(/###\s*Key idea\s*\n([\s\S]+?)(\n###|$)/);
  return m?.[1]?.trim() ?? null;
}

export function SkillPage() {
  const { id = "" } = useParams();
  const skillId = Number(id);
  const navigate = useNavigate();
  const { profile } = useProfile();
  const s = useApi(() => tutor.skill(skillId), [skillId]);
  const [busy, setBusy] = useState<string | null>(null);
  const [error, setError] = useState<string>();
  const [modeOpen, setModeOpen] = useState(false);

  if (s.loading && !s.data) return <PageLoader label="Opening the learning module…" />;
  if (s.error) return <ErrorState error={s.error} onRetry={s.reload} />;
  const k: SkillDetail = s.data!;
  const notes = k.resources.filter((r) => r.kind === "notes");
  const examples = k.resources.filter((r) => r.kind === "worked_example");
  const videos = k.resources.filter((r) => r.kind === "video");
  const others = k.resources.filter((r) => !["notes", "worked_example", "video"].includes(r.kind));
  const idea = keyIdea(notes[0]?.content_md);

  async function practise(guided: boolean) {
    setBusy(guided ? "guided" : "practice");
    setError(undefined);
    try {
      const p = await tutor.startPractice(skillId, guided);
      navigate(`/practice/${p.id}`);
    } catch (e) {
      setError(e instanceof ApiError ? e.message : "Couldn't start practice.");
      setBusy(null);
    }
  }

  async function setMode(mode: Mode | null) {
    setBusy("mode");
    try {
      await tutor.setMode(skillId, mode);
      s.reload();
      setModeOpen(false);
    } finally {
      setBusy(null);
    }
  }

  const assessKind = k.attempts === 0 ? "skill_check" : "reassessment";
  const canReassess = k.fresh_questions >= 3;

  return (
    <div className="space-y-6">
      <header>
        <p className="text-xs font-semibold uppercase tracking-[0.14em] text-brand">
          {k.domain_name} · Grade {k.grade} · {k.code}
        </p>
        <h1 className="mt-1 text-2xl font-semibold tracking-tight sm:text-[28px]">{k.name}</h1>
        <div className="mt-3 flex flex-wrap items-center gap-2">
          <StatusBadge status={k.status} />
          <ModeBadge mode={k.mode} />
          {k.completed && <span className="rounded-full bg-strength/12 px-2.5 py-1 text-xs font-medium text-strength">Completed</span>}
          <EvidenceMeter evidence={k.evidence} attempts={k.attempts} />
        </div>
      </header>

      <div className="grid gap-4 md:grid-cols-3">
        <Card>
          <p className="text-xs font-semibold uppercase tracking-wider text-ink-faint">Your observed performance</p>
          <p className="mt-2 text-3xl font-semibold">{k.attempts ? pct(k.observed_accuracy) : "—"}</p>
          <p className="mt-1 text-sm text-ink-muted">{k.attempts ? `${k.correct} of ${k.attempts} correct · recent ${pct(k.recent_accuracy)}` : "No answers in this skill yet"}</p>
        </Card>
        <Card>
          <p className="text-xs font-semibold uppercase tracking-wider text-ink-faint">Model estimate</p>
          <p className="mt-2 text-3xl font-semibold text-accent">{k.predicted_p === null ? "—" : pct(k.predicted_p)}</p>
          <ModelEstimate p={k.predicted_p} className="mt-1" />
        </Card>
        <Card>
          <div className="flex items-center justify-between">
            <p className="text-xs font-semibold uppercase tracking-wider text-ink-faint">Learning mode</p>
            <button type="button" className="text-xs text-brand hover:underline" onClick={() => setModeOpen((o) => !o)}>
              {modeOpen ? "Close" : "Adjust"}
            </button>
          </div>
          <p className="mt-2 text-xl font-semibold">{k.mode_label}</p>
          <p className="mt-1 text-sm text-ink-muted">{MODES.find((m) => m.id === k.mode)?.text}</p>
          <p className="mt-1 text-xs text-ink-faint">{k.mode_is_override ? "Chosen by you" : "Set automatically from your evidence"}</p>
        </Card>
      </div>

      {modeOpen && (
        <Card>
          <CardTitle title="Choose how you want to learn this skill" subtitle="Modes are per skill and never a permanent label. Automatic mode follows your accuracy and hint use (never your speed)." />
          <div className="grid gap-2 sm:grid-cols-2 lg:grid-cols-4">
            {MODES.map((m) => (
              <button key={m.id} type="button" disabled={busy === "mode"} onClick={() => setMode(m.id)} className={cx("rounded-xl border p-3 text-left text-sm", k.mode === m.id ? "border-brand bg-brand-soft" : "border-line hover:bg-surface-2")}>
                <span className="font-semibold">{m.label}</span>
                <span className="mt-1 block text-xs text-ink-muted">{m.text}</span>
              </button>
            ))}
          </div>
          {k.mode_is_override && (
            <Button variant="ghost" size="sm" className="mt-3" onClick={() => setMode(null)}>
              Use the automatic mode again
            </Button>
          )}
        </Card>
      )}

      {k.support_plan && (
        <Card className="border-developing/40 bg-developing/5">
          <CardTitle icon={<LifeBuoy className="size-4 text-developing" />} title={k.support_plan.message} subtitle="Here's a different approach before you try again." />
          <ol className="ml-5 list-decimal space-y-1.5 text-sm text-ink/90">
            {k.support_plan.steps.map((st) => (
              <li key={st}>{st}</li>
            ))}
          </ol>
          {k.support_plan.prerequisites_to_check.length > 0 && (
            <div className="mt-4">
              <p className="mb-2 text-sm font-medium">Building blocks worth checking first (curated prerequisites):</p>
              <div className="grid gap-2 md:grid-cols-2">
                {k.support_plan.prerequisites_to_check.map((p) => (
                  <SkillCard key={p.id} skill={p} compact />
                ))}
              </div>
            </div>
          )}
          {k.support_plan.no_prerequisite_note && <p className="mt-3 text-sm text-ink-muted">{k.support_plan.no_prerequisite_note}</p>}
          <Button className="mt-4" onClick={() => practise(true)} loading={busy === "guided"} icon={<PlayCircle className="size-4" />}>
            Start foundation practice
          </Button>
        </Card>
      )}

      <div className="grid gap-6 lg:grid-cols-[1.55fr_1fr]">
        <Card>
          <CardTitle icon={<Layers className="size-4" />} title="Learning module" subtitle={`${k.resources_done} of ${k.resources.length} resources completed. Studying never changes your skill estimate; only your answers do.`} />
          <ol className="space-y-8">
            <Step n={1} icon={<Sparkles className="size-4" />} title="Understand the concept">
              {idea ? (
                <div className="rounded-xl border border-line bg-surface-2/60 p-4">
                  <Markdown source={idea} />
                </div>
              ) : (
                <p className="text-sm text-ink-muted">{k.description || "Read the official standard below to see exactly what this skill covers."}</p>
              )}
            </Step>
            <Step n={2} icon={<Video className="size-4" />} title="Watch a relevant educational video">
              {videos.length ? (
                <div className="space-y-3">
                  {videos.map((r) => (
                    <ResourceCard key={r.id} resource={r} />
                  ))}
                </div>
              ) : (
                <p className="rounded-xl border border-dashed border-line-strong p-4 text-sm text-ink-muted">No verified video has been added for this skill yet. Use the notes and worked example instead, then practise.</p>
              )}
            </Step>
            <Step n={3} icon={<BookOpenText className="size-4" />} title="Read concept notes" done={notes.length > 0 && notes.every((r) => r.completed)}>
              <div className="space-y-3">
                {notes.map((r) => (
                  <ResourceCard key={r.id} resource={r} onChange={() => s.reload()} />
                ))}
                {others.map((r) => (
                  <ResourceCard key={r.id} resource={r} onChange={() => s.reload()} />
                ))}
                {!notes.length && <p className="text-sm text-ink-muted">No written notes for this skill yet. The official standard below describes it, and practice will help.</p>}
              </div>
            </Step>
            <Step n={4} icon={<PenLine className="size-4" />} title="Study worked examples" done={examples.length > 0 && examples.every((r) => r.completed)}>
              {examples.length ? (
                <div className="space-y-3">
                  {examples.map((r) => (
                    <ResourceCard key={r.id} resource={r} onChange={() => s.reload()} />
                  ))}
                </div>
              ) : (
                <p className="text-sm text-ink-muted">No worked example for this skill yet. Guided practice shows the correct answer after every question, so you can learn from each one.</p>
              )}
            </Step>
            <Step n={5} icon={<PlayCircle className="size-4" />} title="Attempt guided practice">
              <p className="mb-3 text-sm text-ink-muted">Starts easy with hints available. Two right in a row makes it harder; two wrong makes it easier.</p>
              <div className="flex flex-wrap gap-2">
                <Button onClick={() => practise(true)} loading={busy === "guided"} icon={<PlayCircle className="size-4" />}>
                  Guided practice
                </Button>
                {!["foundation"].includes(k.mode) && (
                  <Button variant="secondary" onClick={() => practise(false)} loading={busy === "practice"}>
                    {k.mode_label} practice
                  </Button>
                )}
              </div>
            </Step>
            <Step n={6} icon={<ClipboardCheck className="size-4" />} title="Take a short assessment">
              <p className="mb-3 text-sm text-ink-muted">
                {assessKind === "skill_check"
                  ? "A few questions to see where you stand in this skill."
                  : `A ${k.reassessment_length}-question reassessment with questions you have never seen, compared with your first answers.`}
              </p>
              {assessKind === "reassessment" && !canReassess ? (
                <p className="text-sm text-ink-muted">You've seen almost every question in this skill, so a fair reassessment isn't possible.</p>
              ) : (
                <Button variant="secondary" to={`/assess/start?kind=${assessKind}&skill=${k.id}`} icon={<ArrowRight className="size-4" />}>
                  {assessKind === "skill_check" ? "Take the skill check" : "Take a reassessment"}
                </Button>
              )}
            </Step>
          </ol>
          {error && <p className="mt-4 text-sm text-danger" role="alert">{error}</p>}
        </Card>

        <div className="space-y-6">
          <Card className="border-brand/30">
            <CardTitle icon={<Target className="size-4" />} title="Next recommended activity" />
            <p className="font-medium">{k.next_activity.label}</p>
            <div className="mt-3">
              {k.next_activity.action === "skill_check" && <Button to={`/assess/start?kind=skill_check&skill=${k.id}`}>Start</Button>}
              {k.next_activity.action === "reassess" && <Button to={`/assess/start?kind=reassessment&skill=${k.id}`}>Start reassessment</Button>}
              {(k.next_activity.action === "practice" || k.next_activity.action === "foundation") && (
                <Button onClick={() => practise(k.next_activity.action === "foundation")} loading={busy !== null}>
                  Start practice
                </Button>
              )}
            </div>
            {k.last_reassessment && (
              <p className="mt-3 text-xs text-ink-faint">
                Last reassessment: {pct(k.last_reassessment.result.reassessment_accuracy)} ({k.last_reassessment.result.outcome?.replace("_", " ")})
              </p>
            )}
          </Card>

          <Card>
            <CardTitle icon={<History className="size-4" />} title="Recent mistakes" subtitle="Compare your answer with the correct one" />
            {k.recent_mistakes.length ? (
              <ul className="space-y-3">
                {k.recent_mistakes.map((m) => (
                  <li key={`${m.item_id}-${m.at}`} className="rounded-xl border border-line bg-surface-2/50 p-3 text-sm">
                    <Html html={m.body_html} className="question-html line-clamp-4 text-sm" />
                    <p className="mt-2 text-xs text-ink-muted">
                      {m.revealed ? "You asked to see the answer." : (
                        <>
                          You answered: <span className="text-weakness">{m.your_response.value ?? (m.your_response.choice !== undefined ? `option ${String.fromCharCode(65 + Number(m.your_response.choice))}` : (m.your_response.choices ?? []).map((c) => String.fromCharCode(65 + Number(c))).join(", "))}</span>
                        </>
                      )}
                    </p>
                    <p className="text-xs text-ink-muted">
                      Correct:{" "}
                      <span className="text-strength">
                        {m.correct_answer.type === "numeric" ? m.correct_answer.values.join(" or ") : m.correct_answer.option_ids.map((c) => String.fromCharCode(65 + Number(c))).join(", ")}
                      </span>
                    </p>
                  </li>
                ))}
              </ul>
            ) : (
              <p className="text-sm text-ink-muted">No mistakes recorded in this skill.</p>
            )}
          </Card>

          <Card>
            <CardTitle icon={<GitBranch className="size-4" />} title="How this skill connects" />
            {k.prerequisites.length > 0 ? (
              <>
                <p className="mb-2 text-xs font-semibold uppercase tracking-wider text-ink-faint">Builds on</p>
                <div className="space-y-2">
                  {k.prerequisites.map((p) => (
                    <SkillCard key={p.id} skill={p} compact />
                  ))}
                </div>
                <p className="mt-2 text-xs text-ink-faint">{k.prerequisites[0]?.source}</p>
              </>
            ) : (
              <p className="text-sm text-ink-muted">No curated prerequisite is mapped for this skill.</p>
            )}
            {k.leads_to.length > 0 && (
              <>
                <p className="mb-2 mt-4 text-xs font-semibold uppercase tracking-wider text-ink-faint">Leads to</p>
                <div className="space-y-2">
                  {k.leads_to.map((p) => (
                    <SkillCard key={p.id} skill={p} compact />
                  ))}
                </div>
              </>
            )}
          </Card>

          <Card>
            <CardTitle icon={<AlertCircle className="size-4" />} title="Question bank" />
            <p className="text-sm text-ink-muted">
              {k.n_items} questions · {k.fresh_questions} you haven't seen yet
            </p>
            <div className="mt-2 flex flex-wrap gap-2 text-xs">
              {(["easy", "medium", "hard", "unrated"] as const).map((d) =>
                k.difficulty_counts[d] ? (
                  <span key={d} className="rounded-md bg-surface-3 px-2 py-0.5 capitalize text-ink-muted">
                    {d}: {k.difficulty_counts[d]}
                  </span>
                ) : null,
              )}
            </div>
            <p className="mt-2 text-xs text-ink-faint">Difficulty comes from how often students in the training data got each question right on their first try.</p>
          </Card>
          {profile.focus_skill?.id === k.id && <p className="text-center text-xs text-brand">This is your chosen focus topic.</p>}
        </div>
      </div>
    </div>
  );
}
