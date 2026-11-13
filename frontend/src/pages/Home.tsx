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
import { Button, Card, EmptyState, ErrorState, PageLoader, Ring } from "../components/ui";

function greeting() {
  const h = new Date().getHours();
  return h < 12 ? "Good morning" : h < 17 ? "Good afternoon" : "Good evening";
}

function plural(n: number, one: string, many: string) {
  return `${n} ${n === 1 ? one : many}`;
}

function Banner({ icon, children, actions }: { icon: ReactNode; children: ReactNode; actions?: ReactNode }) {
  return (
    <div className="flex flex-col gap-3 rounded-2xl border border-line-strong bg-surface-2/70 p-4 sm:flex-row sm:items-center sm:justify-between animate-rise" role="status">
      <p className="flex items-start gap-3 text-[15px]">
        <span className="mt-0.5 text-accent">{icon}</span>
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
    <Card className="relative overflow-hidden border-brand/35 p-6 sm:p-7">
      <div className="pointer-events-none absolute -right-24 -top-24 size-72 rounded-full bg-brand/12 blur-3xl" aria-hidden />
      <div className="relative">
        <p className="text-xs font-semibold uppercase tracking-[0.14em] text-brand">Today</p>
        <h2 className="mt-2 text-xl font-semibold tracking-tight sm:text-2xl">{next.title}</h2>
        {next.progress_hint && <p className="mt-1.5 text-[15px] text-ink-muted">{next.progress_hint}</p>}
        <div className="mt-6 flex flex-wrap items-start justify-between gap-3">
          <StartButton action={next} size="lg">
            Start
          </StartButton>
          <WhyButton align="end" className="max-w-sm">
            {next.reason}
          </WhyButton>
        </div>
      </div>
    </Card>
  );
}

function StreakStrip({ s }: { s: Streak }) {
  const goal = Math.max(1, s.daily_goal);
  return (
    <div className="flex items-center justify-between gap-4 rounded-2xl border border-line bg-surface px-4 py-3">
      <p className="flex items-center gap-2 text-[15px]">
        <Flame className={s.current > 0 ? "size-5 text-weakness" : "size-5 text-ink-faint"} aria-hidden />
        <span className="font-medium">{s.current === 1 ? "1-day streak" : `${s.current}-day streak`}</span>
      </p>
      <div className="flex items-center gap-3">
        <span className="text-sm text-ink-muted">{s.goal_met ? "Daily goal reached" : "Today"}</span>
        <Ring value={Math.min(s.today, goal) / goal} size={44} stroke={5} color={s.goal_met ? "#34d399" : "#8b8cff"} label={<span className="text-[11px]">{`${s.today}/${s.daily_goal}`}</span>} />
      </div>
    </div>
  );
}

function UpNextRow({ a }: { a: NextAction }) {
  return (
    <li className="rounded-xl border border-line bg-surface px-4 py-3">
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
    <div className="space-y-6">
      <header>
        <h1 className="text-2xl font-semibold tracking-tight sm:text-[28px]">
          {greeting()}, {home.name}
        </h1>
        <p className="mt-1 text-ink-muted">{home.subject.name}</p>
      </header>

      <TopBanner home={home} onChange={h.reload} />

      {home.next ? (
        <TodayCard next={home.next} />
      ) : (
        <EmptyState title="Nothing to practise here yet">This subject has no questions available right now. Try another subject or come back later.</EmptyState>
      )}

      <StreakStrip s={home.streak} />

      {home.up_next.length > 0 && (
        <section aria-labelledby="up-next">
          <h2 id="up-next" className="mb-3 text-sm font-semibold uppercase tracking-wider text-ink-faint">
            Up next
          </h2>
          <ul className="space-y-2">
            {home.up_next.slice(0, 2).map((a, i) => (
              <UpNextRow key={`${a.kind}-${a.skill?.id ?? i}`} a={a} />
            ))}
          </ul>
        </section>
      )}

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
          Want a full picture? <Link to="/assess/start?kind=diagnostic" className="text-brand hover:underline">Take the placement check</Link>
        </p>
      )}
    </div>
  );
}
