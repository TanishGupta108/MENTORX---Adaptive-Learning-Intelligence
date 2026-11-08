import { ButtonLink } from "../components/ui";

const steps = [
  {
    title: "A 19-question diagnostic",
    text: "One question per concept, from probability to neural networks, so MENTORX can see where you start.",
  },
  {
    title: "Questions picked for you",
    text: "A model trained on real learners predicts your chance of answering each question, and serves ones that stretch you without overwhelming you.",
  },
  {
    title: "A path and revision schedule",
    text: "Weak spots, missing prerequisites and concepts you're starting to forget, each with a reason you can read.",
  },
];

export function LandingPage() {
  return (
    <main className="mx-auto flex min-h-screen max-w-5xl flex-col px-4 py-10 sm:py-16">
      <p className="text-lg font-semibold tracking-tight">
        MENTOR<span className="text-brand">X</span>
      </p>
      <section className="mt-12 max-w-2xl sm:mt-20">
        <h1 className="text-4xl font-semibold tracking-tight sm:text-5xl">
          Learn Machine Learning at the level you're actually at.
        </h1>
        <p className="mt-4 text-lg text-ink-muted">
          MENTORX estimates what you know from how you answer, then chooses your next question,
          your study path and your revision schedule.
        </p>
        <div className="mt-8 flex flex-wrap gap-3">
          <ButtonLink to="/register">Create a free account</ButtonLink>
          <ButtonLink to="/login" variant="secondary">
            Log in
          </ButtonLink>
        </div>
      </section>
      <ol className="mt-16 grid gap-4 sm:grid-cols-3">
        {steps.map((s, i) => (
          <li key={s.title} className="rounded-xl border border-line bg-surface p-5">
            <p className="text-sm font-medium text-brand">Step {i + 1}</p>
            <h2 className="mt-1 font-semibold">{s.title}</h2>
            <p className="mt-2 text-sm text-ink-muted">{s.text}</p>
          </li>
        ))}
      </ol>
    </main>
  );
}
