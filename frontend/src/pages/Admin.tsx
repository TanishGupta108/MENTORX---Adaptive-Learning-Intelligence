import { useState } from "react";
import { ApiError } from "../api/client";
import { admin } from "../api/endpoints";
import type { PilotMetrics } from "../api/types";
import { Button, Card, EmptyState, ErrorState, PageHeader, pct, Spinner, Stat } from "../components/ui";
import { useApi } from "../hooks/useApi";

const num = (x: number | null, digits = 2) => (x == null ? "—" : x.toFixed(digits));
const pts = (x: number | null) => (x == null ? "—" : `${x >= 0 ? "+" : "−"}${Math.round(Math.abs(x) * 100)} pts`);
const ci = (c: [number, number] | null) => (c == null ? "n too small" : `${pts(c[0])} to ${pts(c[1])}`);
const rate = (x: number | null) => (x == null ? "—" : pct(x));

/** FR-DASH-09 and FR-PILOT-05: the study team's view. */
export function AdminPage() {
  const m = useApi((s) => admin.metrics(s));
  if (m.loading && !m.data) return <Spinner />;
  if (m.error) return <ErrorState error={m.error} onRetry={m.reload} />;
  const d = m.data as PilotMetrics;

  return (
    <>
      <PageHeader title="Pilot study">
        Research outcomes include consenting participants only. Pilot sign-ups are{" "}
        <strong>{d.pilot_active ? "on" : "off"}</strong>; the post-test is{" "}
        <strong>{d.posttest_open ? "open" : "closed"}</strong>.
      </PageHeader>

      <Exports />

      <Card title="Learning gain by group (post − pre, fraction correct)" className="mt-6">
        <div className="overflow-x-auto">
          <table className="w-full min-w-[36rem] text-left text-sm">
            <thead className="text-ink-muted">
              <tr>
                <th className="py-2 pr-3 font-medium">Group</th>
                <th className="py-2 pr-3 font-medium">Participants</th>
                <th className="py-2 pr-3 font-medium">Pre / post done</th>
                <th className="py-2 pr-3 font-medium">Mean pre</th>
                <th className="py-2 pr-3 font-medium">Mean post</th>
                <th className="py-2 pr-3 font-medium">Mean gain (95% CI)</th>
                <th className="py-2 font-medium">SUS</th>
              </tr>
            </thead>
            <tbody className="tabular-nums">
              {d.groups.map((g) => (
                <tr key={g.group} className="border-t border-line">
                  <td className="py-2 pr-3 font-medium capitalize">{g.group}</td>
                  <td className="py-2 pr-3">{g.participants}</td>
                  <td className="py-2 pr-3">
                    {g.pretest_done} / {g.posttest_done}
                  </td>
                  <td className="py-2 pr-3">{rate(g.mean_pre)}</td>
                  <td className="py-2 pr-3">{rate(g.mean_post)}</td>
                  <td className="py-2 pr-3">
                    {pts(g.mean_gain)} <span className="text-ink-muted">({ci(g.gain_ci95)})</span>
                  </td>
                  <td className="py-2">
                    {num(g.sus_mean, 1)} <span className="text-ink-muted">(n={g.sus_n})</span>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
        <p className="mt-3 text-sm">
          Adaptive − control: <strong>{pts(d.gain_difference)}</strong>{" "}
          <span className="text-ink-muted">
            (Welch 95% CI {ci(d.gain_difference_ci95)}; Cohen's d {num(d.cohens_d)})
          </span>
        </p>
        <p className="mt-1 text-xs text-ink-muted">
          Small samples: report these as preliminary, with the confidence intervals.
        </p>
      </Card>

      <h2 className="mt-8 mb-3 text-lg font-semibold">Engagement</h2>
      <div className="grid grid-cols-2 gap-3 lg:grid-cols-3">
        <Stat label="Students" value={d.engagement.students} />
        <Stat label="Weekly active" value={d.engagement.wau} hint="answered in the last 7 days" />
        <Stat label="Session completion" value={rate(d.engagement.completion_rate)} hint={`${d.engagement.sessions_started} started`} />
        <Stat label="Day-1 retention" value={rate(d.engagement.d1_retention)} hint="active on the day after sign-up" />
        <Stat label="Day-7 retention" value={rate(d.engagement.d7_retention)} hint="active 7 days after sign-up" />
      </div>

      <Card title="Live model quality" className="mt-6">
        {d.model.n === 0 ? (
          <EmptyState title="No predictions yet">These appear once students answer questions.</EmptyState>
        ) : (
          <>
            <div className="grid grid-cols-2 gap-3 lg:grid-cols-4">
              <Stat label="Answers" value={d.model.n} />
              <Stat label="AUC" value={num(d.model.auc, 3)} />
              <Stat label="Brier score" value={num(d.model.brier, 3)} hint="lower is better" />
              <Stat label="Calibration error" value={num(d.model.ece, 3)} hint="ECE, lower is better" />
            </div>
            <div className="mt-4 overflow-x-auto">
              <table className="w-full text-left text-sm tabular-nums">
                <thead className="text-ink-muted">
                  <tr>
                    <th className="py-1 pr-3 font-medium">Predicted</th>
                    <th className="py-1 pr-3 font-medium">Answers</th>
                    <th className="py-1 pr-3 font-medium">Mean predicted</th>
                    <th className="py-1 font-medium">Actually correct</th>
                  </tr>
                </thead>
                <tbody>
                  {d.model.bins.map((b) => (
                    <tr key={b.lo} className="border-t border-line">
                      <td className="py-1 pr-3">
                        {pct(b.lo)}–{pct(b.hi)}
                      </td>
                      <td className="py-1 pr-3">{b.n}</td>
                      <td className="py-1 pr-3">{pct(b.mean_predicted)}</td>
                      <td className="py-1">{pct(b.observed)}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </>
        )}
      </Card>

      <Card title={`Feedback (${d.feedback.n}, mean rating ${num(d.feedback.mean_rating, 1)})`} className="mt-6">
        {d.feedback.recent.length === 0 ? (
          <EmptyState title="No feedback yet" />
        ) : (
          <ul className="space-y-3">
            {d.feedback.recent.map((f, i) => (
              <li key={i} className="border-t border-line pt-3 first:border-0 first:pt-0">
                <p className="text-sm">
                  <strong>{f.rating}/5</strong> · {f.category}
                  {f.page ? ` · ${f.page}` : ""}{" "}
                  <span className="text-ink-muted">· {new Date(f.at).toLocaleString()}</span>
                </p>
                {f.message && <p className="mt-1 whitespace-pre-line">{f.message}</p>}
              </li>
            ))}
          </ul>
        )}
      </Card>
    </>
  );
}

function Exports() {
  const [busy, setBusy] = useState<string | null>(null);
  const [error, setError] = useState("");
  async function run(name: string, fn: () => Promise<void>) {
    setBusy(name);
    setError("");
    try {
      await fn();
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Download failed.");
    } finally {
      setBusy(null);
    }
  }
  return (
    <Card title="Pseudonymised exports">
      <p className="text-sm text-ink-muted">
        Consenting students only. No names or emails: each student is a stable random code.
      </p>
      <div className="mt-3 flex flex-wrap gap-2">
        <Button variant="secondary" disabled={busy !== null} onClick={() => run("a", admin.exportAttempts)}>
          {busy === "a" ? "Preparing…" : "Answers (for retraining)"}
        </Button>
        <Button variant="secondary" disabled={busy !== null} onClick={() => run("o", admin.exportOutcomes)}>
          {busy === "o" ? "Preparing…" : "Outcomes per participant"}
        </Button>
      </div>
      {error && (
        <p role="alert" className="mt-2 text-sm text-danger">
          {error}
        </p>
      )}
    </Card>
  );
}
