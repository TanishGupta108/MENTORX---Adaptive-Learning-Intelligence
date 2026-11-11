import { ArrowRight, BarChart3, BrainCircuit, Compass, Gauge, Layers, LineChart, ListChecks, Route, ShieldCheck, Sparkles, Target } from "lucide-react";
import { Link } from "react-router";
import { Button, Logo, StatusBadge } from "../components/ui";

const STEPS = [
  { icon: ListChecks, title: "Take a short diagnostic", text: "About ten real maths questions across the curriculum, one at a time, with instant feedback." },
  { icon: BrainCircuit, title: "Get your skill diagnosis", text: "MENTORX combines your answers with a trained knowledge-tracing model to map strengths and gaps." },
  { icon: Route, title: "Follow a personal path", text: "Every recommendation comes with a reason: what to learn next and why it matters for you." },
  { icon: LineChart, title: "Practise and see progress", text: "Adaptive practice adjusts difficulty as you go, and fresh reassessments show real improvement." },
];

const FEATURES = [
  { icon: Target, title: "Evidence-based diagnosis", text: "Skills are labelled from your own answers. A model prediction never turns into a 'weakness' on its own." },
  { icon: Gauge, title: "Adaptive difficulty", text: "Two right in a row and it gets harder; two wrong and it eases off, always with unseen questions." },
  { icon: Layers, title: "Your pace, per skill", text: "Foundation, Guided, Independent or Advanced: a different mode for each topic, adjusted as you improve." },
  { icon: Compass, title: "Learning modules", text: "Concept notes, worked examples and the official standard for each skill, before you practise." },
  { icon: Sparkles, title: "Support when stuck", text: "No progress? MENTORX reviews your mistakes, checks building blocks and simplifies before you retry." },
  { icon: BarChart3, title: "Honest analytics", text: "What you actually got right and what the model predicts are always shown side by side, never mixed." },
];

const QUESTIONS = [
  "What do I already understand?",
  "What am I struggling with?",
  "What should I learn next?",
  "How should I practise?",
  "Am I actually improving?",
];

function Preview() {
  const rows = [
    { name: "Unit rates", code: "6.RP.A.3b", status: "likely_strength" as const, w: 86 },
    { name: "Two-step equations", code: "7.EE.B.4a", status: "developing" as const, w: 58 },
    { name: "Circles: area & circumference", code: "7.G.B.4", status: "potential_weakness" as const, w: 32 },
    { name: "Scale drawings", code: "7.G.A.1", status: "needs_assessment" as const, w: 0 },
  ];
  return (
    <div className="relative rounded-3xl border border-line bg-surface/80 p-5 shadow-[0_30px_80px_-30px_#6d6ef755] backdrop-blur">
      <div className="mb-4 flex items-center justify-between">
        <div>
          <p className="text-xs uppercase tracking-wider text-ink-faint">Example learning profile</p>
          <p className="font-semibold">Mathematics · skill map</p>
        </div>
        <span className="rounded-full bg-surface-3 px-2.5 py-1 text-xs text-ink-muted">illustration</span>
      </div>
      <div className="space-y-3">
        {rows.map((r) => (
          <div key={r.code} className="rounded-2xl border border-line bg-surface-2 p-3.5">
            <div className="flex items-center justify-between gap-3">
              <div className="min-w-0">
                <p className="truncate text-sm font-medium">{r.name}</p>
                <p className="text-xs text-ink-faint">{r.code}</p>
              </div>
              <StatusBadge status={r.status} />
            </div>
            <div className="mt-2.5 h-1.5 overflow-hidden rounded-full bg-surface-3">
              <div className="h-full rounded-full bg-gradient-to-r from-brand to-accent" style={{ width: `${r.w}%` }} />
            </div>
          </div>
        ))}
      </div>
      <div className="mt-4 rounded-2xl border border-brand/30 bg-brand-soft p-3.5 text-sm">
        <p className="font-medium">Recommended next: Circles</p>
        <p className="mt-0.5 text-ink-muted">Your answers suggest extra practice would help. Start with the worked example.</p>
      </div>
    </div>
  );
}

export function LandingPage() {
  return (
    <div className="relative overflow-hidden">
      <div className="pointer-events-none absolute inset-x-0 top-0 h-[560px] bg-[radial-gradient(60%_60%_at_50%_0%,#6d6ef733,transparent)]" />
      <header className="relative mx-auto flex max-w-6xl items-center justify-between px-5 py-5">
        <Logo />
        <nav className="hidden items-center gap-7 text-sm text-ink-muted md:flex">
          <a href="#how" className="hover:text-ink">How it works</a>
          <a href="#features" className="hover:text-ink">Features</a>
          <a href="#why" className="hover:text-ink">Why MENTORX</a>
        </nav>
        <div className="flex items-center gap-2">
          <Button variant="ghost" to="/login">Sign in</Button>
          <Button to="/register">Get started</Button>
        </div>
      </header>

      <section className="relative mx-auto grid max-w-6xl items-center gap-12 px-5 pb-20 pt-10 md:grid-cols-[1.1fr_1fr] md:pt-16">
        <div>
          <p className="mb-5 inline-flex items-center gap-2 rounded-full border border-line bg-surface/70 px-3 py-1 text-xs text-ink-muted">
            <Sparkles className="size-3.5 text-brand" /> Learn Smarter. Improve Faster.
          </p>
          <h1 className="text-4xl font-semibold leading-[1.1] tracking-tight sm:text-5xl">
            Your Learning Journey. <span className="bg-gradient-to-r from-brand to-accent bg-clip-text text-transparent">Your Pace.</span> Your Mentor.
          </h1>
          <p className="mt-5 max-w-xl text-lg text-ink-muted">
            Discover your strengths, improve your weak areas, and learn through a personalized AI-powered experience.
          </p>
          <div className="mt-8 flex flex-wrap gap-3">
            <Button size="lg" to="/register" icon={<ArrowRight className="size-4" />}>
              Get started free
            </Button>
            <Button size="lg" variant="secondary" to="/login">
              Sign in
            </Button>
          </div>
          <p className="mt-6 flex items-center gap-2 text-sm text-ink-faint">
            <ShieldCheck className="size-4" /> Grade 6–8 mathematics · Common Core aligned · real student data
          </p>
        </div>
        <Preview />
      </section>

      <section id="how" className="relative mx-auto max-w-6xl px-5 py-16">
        <p className="text-xs font-semibold uppercase tracking-[0.14em] text-brand">How it works</p>
        <h2 className="mt-2 text-3xl font-semibold tracking-tight">From first question to steady progress</h2>
        <div className="mt-10 grid gap-4 md:grid-cols-4">
          {STEPS.map((s, i) => (
            <div key={s.title} className="rounded-2xl border border-line bg-surface p-5">
              <div className="mb-4 flex items-center justify-between">
                <span className="grid size-10 place-items-center rounded-xl bg-brand-soft text-brand">
                  <s.icon className="size-5" />
                </span>
                <span className="text-sm font-semibold text-ink-faint">0{i + 1}</span>
              </div>
              <h3 className="font-semibold">{s.title}</h3>
              <p className="mt-1.5 text-sm text-ink-muted">{s.text}</p>
            </div>
          ))}
        </div>
      </section>

      <section id="features" className="relative mx-auto max-w-6xl px-5 py-16">
        <p className="text-xs font-semibold uppercase tracking-[0.14em] text-brand">Features</p>
        <h2 className="mt-2 text-3xl font-semibold tracking-tight">A mentor, not a quiz website</h2>
        <div className="mt-10 grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
          {FEATURES.map((f) => (
            <div key={f.title} className="rounded-2xl border border-line bg-surface p-5">
              <f.icon className="size-5 text-accent" />
              <h3 className="mt-3 font-semibold">{f.title}</h3>
              <p className="mt-1.5 text-sm text-ink-muted">{f.text}</p>
            </div>
          ))}
        </div>
      </section>

      <section id="why" className="relative mx-auto max-w-6xl px-5 py-16">
        <div className="grid gap-10 rounded-3xl border border-line bg-surface p-8 md:grid-cols-2 md:p-12">
          <div>
            <p className="text-xs font-semibold uppercase tracking-[0.14em] text-brand">Why MENTORX</p>
            <h2 className="mt-2 text-3xl font-semibold tracking-tight">Every student learns differently</h2>
            <p className="mt-4 text-ink-muted">
              Students have different knowledge, speeds, strengths and weaknesses. Traditional platforms give everyone the
              same experience. MENTORX keeps analysing what you do and adapts what comes next. Every decision is explained
              in plain language.
            </p>
            <p className="mt-4 text-sm text-ink-faint">
              Built on the FoundationalASSIST dataset (ASSISTments, CC BY-NC 4.0) and a deep knowledge-tracing model trained
              on it.
            </p>
          </div>
          <ul className="space-y-3">
            {QUESTIONS.map((q, i) => (
              <li key={q} className="flex items-center gap-3 rounded-2xl border border-line bg-surface-2 p-4">
                <span className="grid size-8 shrink-0 place-items-center rounded-lg bg-brand-soft text-sm font-semibold text-brand">{i + 1}</span>
                <span className="font-medium">{q}</span>
              </li>
            ))}
          </ul>
        </div>
      </section>

      <section className="relative mx-auto max-w-6xl px-5 pb-20 pt-6 text-center">
        <h2 className="text-3xl font-semibold tracking-tight">Start with ten questions.</h2>
        <p className="mt-3 text-ink-muted">Your personal learning plan is ready in about ten minutes.</p>
        <div className="mt-7">
          <Button size="lg" to="/register" icon={<ArrowRight className="size-4" />}>
            Create your account
          </Button>
        </div>
      </section>

      <footer className="border-t border-line">
        <div className="mx-auto flex max-w-6xl flex-col items-center justify-between gap-3 px-5 py-6 text-sm text-ink-faint sm:flex-row">
          <Logo className="text-ink-muted" />
          <span>Learn Smarter. Improve Faster.</span>
          <Link to="/login" className="hover:text-ink">Sign in</Link>
        </div>
      </footer>
    </div>
  );
}
