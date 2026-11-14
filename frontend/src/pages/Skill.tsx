import { useState } from "react";
import type { KeyboardEvent, ReactNode } from "react";
import { Link, useParams, useSearchParams } from "react-router";
import { ArrowLeft, ArrowRight, ExternalLink } from "lucide-react";
import { tutor } from "../api/tutor";
import type { Mistake, Mode, SkillDetail } from "../api/tutor";
import { useApi } from "../hooks/useApi";
import { useProfile } from "../components/AppShell";
import { Html, OrderedItems } from "../components/QuestionView";
import { AiExplain } from "../components/AiTutor";
import { MAP_NOTICE, STATIC_CREDITS } from "../components/Credits";
import { Disclosure } from "../components/Disclosure";
import { MapQuestion } from "../components/MapQuestion";
import { ResourceCard } from "../components/ResourceCard";
import { SkillRow } from "../components/SkillRow";
import { launchFor, StartButton, useLauncher } from "../components/StartAction";
import { Button, cx, EmptyState, ErrorState, EvidenceMeter, MODE_LABEL, ModelEstimate, PageLoader, pct, StatusBadge } from "../components/ui";

const MODES: { id: Mode; text: string }[] = [
  { id: "foundation", text: "Easier questions, more explanation, hints offered" },
  { id: "guided", text: "Easy to medium questions with worked examples" },
  { id: "independent", text: "Medium to hard questions, less help" },
  { id: "advanced", text: "Challenging, application-style questions" },
];

const TABS = [
  { id: "learn", label: "Learn" },
  { id: "practice", label: "Practice" },
  { id: "mistakes", label: "My mistakes" },
] as const;
type Tab = (typeof TABS)[number]["id"];

function DetailBlock({ title, children }: { title: string; children: ReactNode }) {
  return (
    <div>
      <h3 className="mb-1.5 text-xs font-semibold uppercase tracking-wider text-ink-faint">{title}</h3>
      <div className="text-sm">{children}</div>
    </div>
  );
}

function optionHtml(m: Mistake, id: string | undefined) {
  if (id === undefined) return null;
  return m.options.find((o) => o.id === id)?.html ?? null;
}

function MistakeItem({ m }: { m: Mistake }) {
  const ca = m.correct_answer;
  const yourChoices = m.your_response.choice !== undefined ? [m.your_response.choice] : (m.your_response.choices ?? []);
  const correctIds = ca.type === "numeric" || ca.type === "text" ? [] : ca.option_ids;
  return (
    <li className="rounded-2xl border border-line bg-surface p-4">
      <Html html={m.body_html} className="question-html line-clamp-6 text-[15px]" />
      {m.media?.kind === "map" && (
        <MapQuestion media={m.media} selected={m.your_response.choice ?? null} answered correctIds={correctIds} className="mt-3 max-w-md" />
      )}
      <dl className="mt-3 grid gap-1 text-sm">
        <div className="flex flex-wrap gap-x-2">
          <dt className="text-ink-muted">Your answer:</dt>
          <dd className="text-weakness">
            {m.revealed
              ? "You asked to see the answer."
              : m.your_response.value ??
                (m.answer_type === "ordering" ? (
                  <OrderedItems items={yourChoices.map((c) => optionHtml(m, c) ?? c)} />
                ) : (
                  yourChoices.map((c) => {
                    const h = optionHtml(m, c);
                    return h ? <Html key={c} html={h} className="option-html inline" /> : <span key={c}>{c}</span>;
                  })
                ))}
          </dd>
        </div>
        <div className="flex flex-wrap gap-x-2">
          <dt className="text-ink-muted">Correct answer:</dt>
          <dd className="text-strength">
            {ca.type === "numeric" || ca.type === "text"
              ? ca.values.join(" or ")
              : ca.type === "ordering"
                ? <OrderedItems items={ca.options_html} />
                : ca.options_html.map((h, i) => <Html key={i} html={h} className="option-html mr-2 inline" />)}
          </dd>
        </div>
      </dl>
      <AiExplain interactionId={m.interaction_id} label="Explain my mistake" className="mt-3" />
    </li>
  );
}

function ModePicker({ k, onChange }: { k: SkillDetail; onChange: () => void }) {
  const [busy, setBusy] = useState(false);
  async function setMode(mode: Mode | null) {
    setBusy(true);
    try {
      await tutor.setMode(k.id, mode);
      onChange();
    } finally {
      setBusy(false);
    }
  }
  return (
    <div>
      <p className="text-ink-muted">
        Now: <span className="font-medium text-ink">{MODE_LABEL[k.mode]}</span> · {k.mode_is_override ? "chosen by you" : "set automatically from your answers"}
      </p>
      <div className="mt-2 grid gap-2 sm:grid-cols-2">
        {MODES.map((m) => (
          <button
            key={m.id}
            type="button"
            disabled={busy}
            aria-pressed={k.mode === m.id}
            onClick={() => setMode(m.id)}
            className={cx("min-h-11 rounded-xl border p-3 text-left text-sm", k.mode === m.id ? "border-brand bg-brand-soft" : "border-line hover:bg-surface-2")}
          >
            <span className="font-medium">{MODE_LABEL[m.id]}</span>
            <span className="mt-0.5 block text-xs text-ink-muted">{m.text}</span>
          </button>
        ))}
      </div>
      {k.mode_is_override && (
        <Button variant="ghost" size="sm" className="mt-2" onClick={() => setMode(null)} disabled={busy}>
          Go back to automatic
        </Button>
      )}
    </div>
  );
}

function Details({ k, onChange }: { k: SkillDetail; onChange: () => void }) {
  return (
    <Disclosure title="Details">
      <div className="grid gap-6">
        <div className="grid gap-6 sm:grid-cols-2">
          <DetailBlock title="Your answers">
            {k.attempts ? (
              <>
                <p>
                  {k.correct} of {k.attempts} correct ({pct(k.observed_accuracy)}) · recent {pct(k.recent_accuracy)}
                </p>
                <EvidenceMeter evidence={k.evidence} />
              </>
            ) : (
              <p className="text-ink-muted">No answers in this skill yet.</p>
            )}
          </DetailBlock>
          <DetailBlock title="Prediction">
            <ModelEstimate p={k.predicted_p} />
            <p className="mt-1 text-xs text-ink-faint">A model's guess from all your answers. It never changes your status; only your answers in this skill do.</p>
          </DetailBlock>
        </div>
        <DetailBlock title="How you practise this skill">
          <ModePicker k={k} onChange={onChange} />
        </DetailBlock>
        {k.support_plan && (
          <DetailBlock title="Support plan">
            <p className="font-medium">{k.support_plan.message}</p>
            <ol className="ml-5 mt-1.5 list-decimal space-y-1 text-ink-muted">
              {k.support_plan.steps.map((s) => (
                <li key={s}>{s}</li>
              ))}
            </ol>
            {k.support_plan.no_prerequisite_note && <p className="mt-1.5 text-ink-muted">{k.support_plan.no_prerequisite_note}</p>}
          </DetailBlock>
        )}
        {(k.prerequisites.length > 0 || k.leads_to.length > 0) && (
          <div className="grid gap-6 sm:grid-cols-2">
            {k.prerequisites.length > 0 && (
              <DetailBlock title="Builds on">
                <div className="-mx-3">
                  {k.prerequisites.map((p) => (
                    <SkillRow key={p.id} skill={p} />
                  ))}
                </div>
              </DetailBlock>
            )}
            {k.leads_to.length > 0 && (
              <DetailBlock title="Leads to">
                <div className="-mx-3">
                  {k.leads_to.map((p) => (
                    <SkillRow key={p.id} skill={p} />
                  ))}
                </div>
              </DetailBlock>
            )}
          </div>
        )}
        <div className="grid gap-6 sm:grid-cols-2">
          <DetailBlock title="Question bank">
            <p>
              {k.n_items} questions · {k.fresh_questions} you haven't seen
            </p>
            <p className="mt-1 text-xs text-ink-muted">
              {(["easy", "medium", "hard", "unrated"] as const)
                .filter((d) => k.difficulty_counts[d])
                .map((d) => `${d} ${k.difficulty_counts[d]}`)
                .join(" · ")}
            </p>
          </DetailBlock>
          <DetailBlock title="Last check">
            {k.last_reassessment ? (
              <p>
                {pct(k.last_reassessment.result.reassessment_accuracy ?? k.last_reassessment.result.accuracy)} on {new Date(k.last_reassessment.completed_at).toLocaleDateString()}
              </p>
            ) : (
              <p className="text-ink-muted">No check taken yet.</p>
            )}
          </DetailBlock>
        </div>
        {k.standard_url && (
          <a href={k.standard_url} target="_blank" rel="noopener noreferrer" className="inline-flex items-center gap-1.5 text-sm text-brand hover:underline">
            Official standard {k.code} <ExternalLink className="size-3.5" aria-hidden />
          </a>
        )}
      </div>
    </Disclosure>
  );
}

export function SkillPage() {
  const { id = "" } = useParams();
  const skillId = Number(id);
  const { profile } = useProfile();
  const [params, setParams] = useSearchParams();
  const s = useApi(() => tutor.skill(skillId), [skillId]);
  const header = useLauncher();
  const tabParam = params.get("tab");
  const tab: Tab = TABS.some((t) => t.id === tabParam) ? (tabParam as Tab) : "learn";

  if (s.loading && !s.data) return <PageLoader label="Opening the skill…" />;
  if (s.error) return <ErrorState error={s.error} onRetry={s.reload} />;
  const k: SkillDetail = s.data!;

  const setTab = (t: Tab) => setParams((p) => {
    const n = new URLSearchParams(p);
    n.set("tab", t);
    return n;
  }, { replace: true });
  const onTabKey = (e: KeyboardEvent<HTMLButtonElement>) => {
    const i = TABS.findIndex((t) => t.id === tab);
    if (e.key === "ArrowRight" || e.key === "ArrowLeft") {
      e.preventDefault();
      const next = TABS[(i + (e.key === "ArrowRight" ? 1 : TABS.length - 1)) % TABS.length]!;
      setTab(next.id);
      document.getElementById(`tab-${next.id}`)?.focus();
    }
  };

  const na = k.next_activity;
  const primary = launchFor(na.action, k.id, na.skill_id);
  const learn = k.resources.filter((r) => r.kind !== "video" && r.kind !== "standard");
  const learnOrder = { notes: 0, worked_example: 1, practice_tip: 2, article: 3, standard: 4, video: 5 } as const;
  learn.sort((a, b) => learnOrder[a.kind] - learnOrder[b.kind]);
  const checkKind = k.attempts === 0 ? "skill_check" : "reassessment";
  const minFresh = k.check_min_fresh ?? 3;
  const canCheck = checkKind === "skill_check" || k.fresh_questions >= minFresh;
  const isGeo = (k.subject?.code ?? profile.subject_code) === "GEO";
  const geoNotice = k.notice ?? MAP_NOTICE;
  const geoCredit = k.attribution ?? STATIC_CREDITS.find((c) => c.code === "GEO")!.text;

  return (
    <div className="space-y-6">
      <Link to="/skills" className="inline-flex min-h-11 items-center gap-1.5 text-sm text-ink-muted hover:text-ink sm:min-h-0">
        <ArrowLeft className="size-4" aria-hidden /> Skills
      </Link>

      <header className="space-y-3">
        <p className="text-xs font-semibold uppercase tracking-[0.14em] text-brand">
          {k.domain_name}
          {k.grade !== null && ` · Grade ${k.grade}`}
        </p>
        <h1 className="text-2xl font-semibold tracking-tight sm:text-[28px]">{k.name}</h1>
        <div className="flex flex-wrap items-center gap-2">
          <StatusBadge status={k.status} />
          {k.completed && <span className="rounded-full bg-strength/12 px-2.5 py-1 text-xs font-medium text-strength">Completed</span>}
          {k.review_due && <span className="rounded-full bg-accent/12 px-2.5 py-1 text-xs font-medium text-accent">Due for review</span>}
        </div>
        {k.mastery?.progress_hint && <p className="text-[15px] text-ink-muted">{k.mastery.progress_hint}</p>}
        {primary && (
          <div className="pt-1">
            {na.action === "learn" ? (
              <Button size="lg" onClick={() => setTab("learn")} icon={<ArrowRight className="size-4" />}>
                {na.label}
              </Button>
            ) : (
              <Button size="lg" onClick={() => void header.launch(primary)} loading={header.busy} icon={<ArrowRight className="size-4" />}>
                {na.label}
              </Button>
            )}
            {header.error && (
              <p className="mt-2 text-sm text-developing" role="alert">
                {header.error}
              </p>
            )}
          </div>
        )}
      </header>

      <div>
        <div role="tablist" aria-label="Skill sections" className="flex gap-1 border-b border-line">
          {TABS.map((t) => (
            <button
              key={t.id}
              id={`tab-${t.id}`}
              role="tab"
              type="button"
              aria-selected={tab === t.id}
              aria-controls={`panel-${t.id}`}
              tabIndex={tab === t.id ? 0 : -1}
              onClick={() => setTab(t.id)}
              onKeyDown={onTabKey}
              className={cx("-mb-px min-h-11 border-b-2 px-3 text-sm font-medium", tab === t.id ? "border-brand text-ink" : "border-transparent text-ink-muted hover:text-ink")}
            >
              {t.label}
              {t.id === "mistakes" && k.recent_mistakes.length > 0 && <span className="ml-1.5 rounded-full bg-surface-3 px-1.5 text-xs text-ink-muted">{k.recent_mistakes.length}</span>}
            </button>
          ))}
        </div>

        <div role="tabpanel" id={`panel-${tab}`} aria-labelledby={`tab-${tab}`} className="pt-5">
          {tab === "learn" &&
            (learn.length ? (
              <div className="space-y-3">
                {learn.map((r, i) => (
                  <ResourceCard key={r.id} resource={r} defaultOpen={i === 0} onChange={() => s.reload()} />
                ))}
              </div>
            ) : (
              <EmptyState title="No notes for this skill yet">Practice shows the right answer after every question, so you can learn as you go.</EmptyState>
            ))}

          {tab === "practice" && (
            <div className="space-y-4">
              <p className="text-[15px] text-ink-muted">A short set of questions that adapts to you: two right in a row and they get harder, two wrong and they get easier.</p>
              <div className="flex flex-wrap gap-3">
                <StartButton action={{ endpoint: "practice", skill_id: k.id, guided: k.mode === "foundation" || k.mode === "guided" }} variant="secondary">
                  Start practice
                </StartButton>
                {!canCheck && !k.completed && (
                  <p className="w-full text-sm text-ink-muted">You've seen almost every question here, so there's no fresh check. Meeting the mastery goal in practice completes this skill.</p>
                )}
                {canCheck && (
                  <StartButton action={{ endpoint: "assessment", kind: checkKind, skill_id: k.id }} variant="soft">
                    {checkKind === "skill_check" ? "Quick skill check" : `Take the ${k.reassessment_length}-question check`}
                  </StartButton>
                )}
              </div>
            </div>
          )}

          {tab === "mistakes" &&
            (k.recent_mistakes.length ? (
              <ul className="space-y-3">
                {k.recent_mistakes.map((m) => (
                  <MistakeItem key={m.interaction_id} m={m} />
                ))}
              </ul>
            ) : (
              <EmptyState title="No mistakes here">Questions you get wrong in this skill will show up here, with the right answer.</EmptyState>
            ))}
        </div>
      </div>

      <Details k={k} onChange={s.reload} />

      {profile.focus_skill?.id === k.id && <p className="text-center text-xs text-brand">This is your chosen focus topic.</p>}

      {isGeo && (
        <footer className="space-y-1 border-t border-line pt-4 text-xs text-ink-faint">
          <p>{geoNotice}</p>
          <p>{geoCredit}</p>
        </footer>
      )}
    </div>
  );
}
