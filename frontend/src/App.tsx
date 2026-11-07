import { ApiStatus } from "./components/ApiStatus";

export default function App() {
  return (
    <main className="mx-auto flex min-h-screen max-w-3xl flex-col justify-center gap-6 px-4 py-16">
      <ApiStatus />
      <h1 className="text-4xl font-semibold tracking-tight sm:text-5xl">MENTORX</h1>
      <p className="max-w-xl text-lg text-ink-muted">
        Adaptive learning for Machine Learning. MENTORX estimates what you know from how you answer,
        then picks your next question, your study path and your revision schedule.
      </p>
      <p className="text-sm text-ink-muted">Under construction: milestone M0.</p>
    </main>
  );
}
