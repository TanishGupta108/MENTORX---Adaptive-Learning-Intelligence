import { ArrowRight, Gauge, LineChart, ListChecks, MessageCircleQuestion, ShieldCheck, Target } from "lucide-react";
import { Link } from "react-router";
import { Credits } from "../components/Credits";
import { Disclosure } from "../components/Disclosure";
import { Button, Logo, StatusBadge } from "../components/ui";

const STEPS = [
  { icon: ListChecks, title: "Take a short check", text: "About ten questions show what you already know." },
  { icon: Target, title: "Get one clear next step", text: "Every day, one thing to do, and why it helps you." },
  { icon: LineChart, title: "Practise and improve", text: "Questions adapt to you, and fresh checks show real progress." },
];

const FEATURES = [
  { icon: Gauge, title: "Adapts to you", text: "Two right in a row and it gets harder; two wrong and it eases off." },
  { icon: ShieldCheck, title: "Honest progress", text: "Your status comes from your own answers, never from a guess." },
  { icon: MessageCircleQuestion, title: "Help when stuck", text: "Hints, worked examples and an AI tutor that explains mistakes." },
];

function Preview() {
  const rows = [
    { name: "Unit rates", status: "likely_strength" as const, w: 86 },
    { name: "Two-step equations", status: "developing" as const, w: 58 },
    { name: "Circles: area", status: "potential_weakness" as const, w: 32 },
    { name: "Scale drawings", status: "needs_assessment" as const, w: 0 },
  ];
  return (
    <div className="relative rounded-3xl border border-line bg-surface/80 p-5 shadow-[0_30px_80px_-30px_#6d6ef755]" aria-label="Example skill list (illustration)">
      <p className="mb-4 text-xs uppercase tracking-wider text-ink-faint">Example</p>
      <div className="space-y-3">
        {rows.map((r) => (
          <div key={r.name} className="rounded-2xl border border-line bg-surface-2 p-3.5">
            <div className="flex items-center justify-between gap-3">
              <p className="truncate text-sm font-medium">{r.name}</p>
              <StatusBadge status={r.status} />
            </div>
            <div className="mt-2.5 h-1.5 overflow-hidden rounded-full bg-surface-3">
              <div className="h-full rounded-full bg-gradient-to-r from-brand to-accent" style={{ width: `${r.w}%` }} />
            </div>
          </div>
        ))}
      </div>
    </div>
  );
}

export function LandingPage() {
  return (
    <div className="relative overflow-hidden">
      <div className="pointer-events-none absolute inset-x-0 top-0 h-[560px] bg-[radial-gradient(60%_60%_at_50%_0%,#6d6ef733,transparent)]" aria-hidden />
      <header className="relative mx-auto flex max-w-5xl items-center justify-between gap-3 px-5 py-5">
        <Logo />
        <nav className="flex items-center gap-2" aria-label="Account">
          <a href="#how" className="hidden min-h-11 items-center px-3 text-sm text-ink-muted hover:text-ink sm:inline-flex">
            How it works
          </a>
          <Button variant="ghost" to="/login">
            Sign in
          </Button>
          <Button to="/register">Get started</Button>
        </nav>
      </header>

      <section className="relative mx-auto grid max-w-5xl items-center gap-12 px-5 pb-16 pt-8 md:grid-cols-[1.15fr_1fr] md:pt-14">
        <div>
          <h1 className="text-4xl font-semibold leading-[1.1] tracking-tight sm:text-5xl">
            Your Learning Journey. <span className="bg-gradient-to-r from-brand to-accent bg-clip-text text-transparent">Your Pace.</span> Your Mentor.
          </h1>
          <p className="mt-5 max-w-xl text-lg text-ink-muted">A calm, adaptive tutor that finds what you know and shows you the next step.</p>
          <p className="mt-3 text-sm text-ink-faint">Maths for grades 4–8 · Geography map skills</p>
          <div className="mt-8 flex flex-wrap gap-3">
            <Button size="lg" to="/register" icon={<ArrowRight className="size-4" />}>
              Get started free
            </Button>
            <Button size="lg" variant="secondary" to="/login">
              Sign in
            </Button>
          </div>
        </div>
        <Preview />
      </section>

      <section id="how" className="relative mx-auto max-w-5xl px-5 py-14">
        <h2 className="text-2xl font-semibold tracking-tight sm:text-3xl">How it works</h2>
        <ol className="mt-8 grid gap-4 md:grid-cols-3">
          {STEPS.map((s, i) => (
            <li key={s.title} className="rounded-2xl border border-line bg-surface p-5">
              <div className="mb-4 flex items-center justify-between">
                <span className="grid size-10 place-items-center rounded-xl bg-brand-soft text-brand">
                  <s.icon className="size-5" aria-hidden />
                </span>
                <span className="text-sm font-semibold text-ink-faint">{i + 1}</span>
              </div>
              <h3 className="font-semibold">{s.title}</h3>
              <p className="mt-1.5 text-sm text-ink-muted">{s.text}</p>
            </li>
          ))}
        </ol>
      </section>

      <section className="relative mx-auto max-w-5xl px-5 py-10">
        <div className="grid gap-4 sm:grid-cols-3">
          {FEATURES.map((f) => (
            <div key={f.title} className="rounded-2xl border border-line bg-surface p-5">
              <f.icon className="size-5 text-accent" aria-hidden />
              <h3 className="mt-3 font-semibold">{f.title}</h3>
              <p className="mt-1.5 text-sm text-ink-muted">{f.text}</p>
            </div>
          ))}
        </div>
      </section>

      <section className="relative mx-auto max-w-5xl px-5 pb-16 pt-8 text-center">
        <h2 className="text-2xl font-semibold tracking-tight sm:text-3xl">Start with ten questions.</h2>
        <div className="mt-6">
          <Button size="lg" to="/register" icon={<ArrowRight className="size-4" />}>
            Create your account
          </Button>
        </div>
      </section>

      <footer className="border-t border-line">
        <div className="mx-auto max-w-5xl space-y-4 px-5 py-6 text-sm text-ink-faint">
          <div className="flex flex-col items-center justify-between gap-3 sm:flex-row">
            <Logo className="text-ink-muted" />
            <Link to="/login" className="hover:text-ink">
              Sign in
            </Link>
          </div>
          <Disclosure variant="plain" title="Data & credits">
            <Credits showStatic />
          </Disclosure>
        </div>
      </footer>
    </div>
  );
}
