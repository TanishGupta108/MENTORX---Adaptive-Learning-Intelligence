import { useState } from "react";
import type { ReactNode } from "react";
import { Link } from "react-router";
import { CalendarClock, Flame, Gauge, PlayCircle, Sparkles } from "lucide-react";
import { ApiError } from "../api/client";
import { tutor } from "../api/tutor";
import type { Home, NextAction, Streak } from "../api/tutor";
import { useApi } from "../hooks/useApi";
import { useProfile } from "../components/AppShell";
import { StartButton } from "../components/StartAction";
import { WhyButton } from "../components/WhyButton";
import { Button, EmptyState, ErrorState, PageLoader, Ring } from "../components/ui";

function greeting() {
  const h = new Date().getHours();
  return h < 12 ? "Good morning" : h < 17 ? "Good afternoon" : "Good evening";
}

function plural(n: number, one: string, many: string) {
  return `${n} ${n === 1 ? one : many}`;
}

function Banner({ icon, children, actions }: { icon: ReactNode; children: ReactNode; actions?: ReactNode }) {
  return (
    <div className="flex flex-col gap-3 rounded-[var(--radius-card)] border border-line-strong p-4 sm:flex-row sm:items-center sm:justify-between" role="status">
      <p className="flex items-start gap-3">
        <span className="mt-0.5 text-ink-muted">{icon}</span>
        <span>{children}</span>
      </p>
      {actions && <div className="flex shrink-0 flex-wrap gap-2">{actions}</div>}
    </div>
  );
}

function PaceBanner({ s, onDone }: { s: NonNullable<Home["pace_suggestion"]>; onDone: () => void }) {
  const { reload } = useProfile();
  const [busy, setBusy] = useState<"yes" | "no" | null>(null);
  const [err, setErr] = useState<string>();
  async function answer(accept: boolean) {
    setBusy(accept ? "yes" : "no");
    setErr(undefined);
    try {
      await tutor.paceSuggestion(accept);
      if (accept) await reload();
      onDone();
    } catch (e) {
      setErr(e instanceof ApiError ? e.message : "Couldn't save that. Please try again.");
      setBusy(null);
    }
  }
  return (
    <Banner
      icon={<Gauge className="size-5" aria-hidden />}
      actions={
        <>
          <Button variant="secondary" size="sm" onClick={() => answer(true)} loading={busy === "yes"}>
            Accept
          </Button>
          <Button variant="ghost" size="sm" onClick={() => answer(false)} loading={busy === "no"}>
            Not now
          </Button>
        </>
      }
    >
      {s.message}
      {err && <span className="mt-1 block text-sm text-developing">{err}</span>}
    </Banner>
  );
}

/** At most one banner, in priority order. */
function TopBanner({ home, onChange }: { home: Home; onChange: () => void }) {
  const nextKind = home.next?.kind;
  if (home.resume && nextKind !== "resume") {
    return (
      <Banner icon={<PlayCircle className="size-5" aria-hidden />} actions={<StartButton action={home.resume} variant="secondary" size="sm">Resume</StartButton>}>
        You have an unfinished session: <span className="font-medium">{home.resume.title}</span>
      </Banner>
    );
  }
  if (home.reviews_due.count > 0 && nextKind !== "review") {
    return (
      <Banner icon={<CalendarClock className="size-5" aria-hidden />} actions={<StartButton action={{ endpoint: "review" }} variant="secondary" size="sm">Start review</StartButton>}>
        {plural(home.reviews_due.count, "skill is", "skills are")} due for a quick review.
      </Banner>
    );
  }
  if (home.pace_suggestion) return <PaceBanner s={home.pace_suggestion} onDone={onChange} />;
  const d = home.diagnosis_summary;
  if (d.show) {
    return (
      <Banner icon={<Sparkles className="size-5" aria-hidden />} actions={<Button variant="secondary" size="sm" to="/diagnosis">See full report</Button>}>
        Your check is done: {d.strong} strong, {d.getting_there} getting there, {d.needs_practice} need practice.
      </Banner>
    );
  }
  return null;
}

function TodayCard({ next }: { next: NextAction }) {
  return (
    <section aria-labelledby="today" className="rounded-[var(--radius-card)] bg-surface p-6 sm:p-8">
      <p className="text-sm text-ink-muted">For today</p>
      <h2 id="today" className="mt-1 max-w-[24ch] text-[28px] font-semibold leading-tight tracking-tight sm:text-[34px]">
        {next.title}
      </h2>
      {next.progress_hint && <p className="mt-2 text-ink-muted">{next.progress_hint}</p>}
      <div className="mt-8 flex flex-wrap items-start justify-between gap-3">
        <StartButton action={next} size="lg">
          Start
        </StartButton>
        <WhyButton align="end" className="max-w-sm">
          {next.reason}
        </WhyButton>
      </div>
    </section>
  );
}

/** The day at a glance, beside the lead: the daily goal as a ring, the streak under it. */
function StreakStrip({ s }: { s: Streak }) {
  const goal = Math.max(1, s.daily_goal);
  return (
    <aside aria-label="Your day" className="flex items-center gap-5 rounded-[var(--radius-card)] border border-line p-5 lg:flex-col lg:items-start lg:p-6">
      <Ring
        value={Math.min(s.today, goal) / goal}
        size={88}
        stroke={7}
        color={s.goal_met ? "var(--color-strength)" : "var(--color-brand)"}
        label={<span className="text-base tabular-nums">{`${s.today}/${s.daily_goal}`}</span>}
      />
      <div className="space-y-1">
        <p className="text-sm text-ink-muted">{s.goal_met ? "Daily goal reached" : "Questions today"}</p>
        <p className="flex items-center gap-2 font-medium">
          <Flame className={s.current > 0 ? "size-4 text-ink" : "size-4 text-ink-faint"} aria-hidden />
          {s.current === 1 ? "1-day streak" : `${s.current}-day streak`}
        </p>
      </div>
    </aside>
  );
}

function UpNextRow({ a }: { a: NextAction }) {
  return (
    <li className="border-t border-line py-4 last:border-b">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div className="min-w-0">
          <p className="font-medium">{a.title}</p>
          {a.progress_hint && <p className="text-sm text-ink-muted">{a.progress_hint}</p>}
        </div>
        <StartButton action={a} variant="secondary" size="sm" />
      </div>
      <WhyButton className="mt-1">{a.reason}</WhyButton>
    </li>
  );
}

export function HomePage() {
  const { profile } = useProfile();
  const h = useApi(() => tutor.home(), [profile.subject_code]);
  if (h.loading && !h.data) return <PageLoader label="Getting today ready…" />;
  if (h.error) return <ErrorState error={h.error} onRetry={h.reload} />;
  const home = h.data!;

  return (
    <div className="space-y-10">
      <header>
        <h1 className="text-[28px] font-semibold leading-tight tracking-tight sm:text-[32px]">
          {greeting()}, {home.name}
        </h1>
        <p className="mt-1 text-ink-muted">{home.subject.name}</p>
      </header>

      <TopBanner home={home} onChange={h.reload} />

      <div className="grid items-start gap-4 lg:grid-cols-[minmax(0,1fr)_240px]">
        {home.next ? (
          <TodayCard next={home.next} />
        ) : (
          <EmptyState title="Nothing to practise here yet">This subject has no questions available right now. Try another subject or come back later.</EmptyState>
        )}
        <StreakStrip s={home.streak} />
      </div>

      {home.up_next.length > 0 && (
        <section aria-labelledby="up-next">
          <h2 id="up-next" className="mb-2 text-[19px] font-semibold tracking-tight">
            Up next
          </h2>
          <ul>
            {home.up_next.slice(0, 2).map((a, i) => (
              <UpNextRow key={`${a.kind}-${a.skill?.id ?? i}`} a={a} />
            ))}
          </ul>
        </section>
      )}

      {(home.mixed.available || (!home.diagnostic_completed && home.next?.kind !== "diagnostic")) && (
        <div className="flex flex-wrap items-center justify-between gap-4">
          {home.mixed.available && (
            <div className="flex flex-wrap items-center gap-3">
              <StartButton action={{ endpoint: "mixed" }} variant="secondary">
                Mixed practice
              </StartButton>
              <span className="text-sm text-ink-muted">Problems that combine several skills.</span>
            </div>
          )}
          {!home.diagnostic_completed && home.next?.kind !== "diagnostic" && (
            <p className="text-sm text-ink-muted">
              Want a full picture?{" "}
              <Link to="/assess/start?kind=diagnostic" className="text-ink underline decoration-line-strong underline-offset-4 hover:decoration-brand">
                Take the placement check
              </Link>
            </p>
          )}
        </div>
      )}
    </div>
  );
}
