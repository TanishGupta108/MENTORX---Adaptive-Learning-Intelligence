/**
 * Admin views for the machine-learning and AI parts:
 * - Model monitor: how well the served knowledge-tracing model predicts REAL answers in this
 *   app (predictions are stored before each answer), next to its offline test results.
 * - AI tutor texts: every cached AI explanation/hint, which an admin can hide.
 */
import { CartesianGrid, ComposedChart, Legend, Line, ResponsiveContainer, Scatter, Tooltip, XAxis, YAxis } from "recharts";
import { Eye, EyeOff, Info } from "lucide-react";
import { adminApi } from "../api/tutor";
import type { Metrics } from "../api/tutor";
import { useApi } from "../hooks/useApi";
import { Markdown } from "./Markdown";
import { Button, Card, CardTitle, cx, ErrorState, pct, Spinner, Stat, timeAgo, token } from "./ui";

const AXIS = { stroke: token("ink-faint"), fontSize: 12, tickLine: false, axisLine: false } as const;

function num(x: number | null | undefined, d = 3) {
  return x === null || x === undefined ? "—" : x.toFixed(d);
}

function MetricsRow({ name, m }: { name: string; m: Metrics }) {
  return (
    <tr className="border-t border-line">
      <td className="py-2 pr-3 font-medium">{name}</td>
      <td className="py-2 pr-3 text-right">{m.n}</td>
      <td className="py-2 pr-3 text-right">{num(m.auc)}</td>
      <td className="py-2 pr-3 text-right">{num(m.log_loss)}</td>
      <td className="py-2 pr-3 text-right">{num(m.brier)}</td>
      <td className="py-2 pr-3 text-right">{pct(m.accuracy)}</td>
      <td className="py-2 pr-3 text-right">{pct(m.mean_predicted)}</td>
      <td className="py-2 text-right">{pct(m.observed_rate)}</td>
    </tr>
  );
}

export function ModelMonitor({ subject }: { subject?: string }) {
  const r = useApi(() => adminApi.model(subject), [subject]);
  if (r.loading) return <Spinner />;
  if (r.error) return <ErrorState error={r.error} onRetry={r.reload} />;
  const d = r.data!;
  const o = d.overall;
  const cal = d.calibration.map((b) => ({ x: Math.round(100 * b.mean_predicted), observed: Math.round(100 * b.observed_rate), n: b.n }));
  return (
    <div className="space-y-6">
      <div className="grid grid-cols-2 gap-3 lg:grid-cols-4">
        <Stat label="Live predictions" value={o.n} hint="answers with a stored prediction" />
        <Stat label="Live AUC" value={num(o.auc)} hint={`offline test: ${num(d.model.test_auc)}`} />
        <Stat label="Live accuracy" value={pct(o.accuracy)} hint={`offline test: ${pct(d.model.test_accuracy)}`} />
        <Stat label="Brier score" value={num(o.brier)} hint="lower is better" />
      </div>
      {o.n < d.min_for_metrics && (
        <p className="flex items-center gap-2 rounded-xl bg-developing/10 px-3 py-2 text-sm text-developing">
          <Info className="size-4" /> Metrics appear after {d.min_for_metrics} answers with a prediction ({o.n} so far).
        </p>
      )}
      <Card>
        <CardTitle title="By context" subtitle="Label = the model's own target: correct first time, no hint, answer not shown." />
        <div className="overflow-x-auto">
          <table className="w-full min-w-[640px] text-sm">
            <thead className="text-sm text-ink-muted">
              <tr>
                <th className="py-2 pr-3 text-left">Where</th>
                <th className="py-2 pr-3 text-right">n</th>
                <th className="py-2 pr-3 text-right">AUC</th>
                <th className="py-2 pr-3 text-right">Log loss</th>
                <th className="py-2 pr-3 text-right">Brier</th>
                <th className="py-2 pr-3 text-right">Acc.</th>
                <th className="py-2 pr-3 text-right">Mean pred.</th>
                <th className="py-2 text-right">Observed</th>
              </tr>
            </thead>
            <tbody>
              <MetricsRow name="All answers" m={o} />
              {Object.entries(d.by_context).map(([k, m]) => (
                <MetricsRow key={k} name={k.replace("_", " ")} m={m} />
              ))}
            </tbody>
          </table>
        </div>
        <p className="mt-3 text-xs text-ink-faint">
          Practice deliberately serves questions near a target success rate, which narrows the range of predictions and usually lowers live AUC compared with the offline test set. Compare calibration too, not AUC alone.
        </p>
      </Card>
      <Card>
        <CardTitle title="Calibration" subtitle="Each point: answers grouped by predicted success. On the diagonal = predictions match reality." />
        {cal.length ? (
          <ResponsiveContainer width="100%" height={280}>
            <ComposedChart data={cal} margin={{ top: 8, right: 16, bottom: 8, left: -12 }}>
              <CartesianGrid stroke={token("line")} strokeDasharray="3 4" />
              <XAxis type="number" dataKey="x" domain={[0, 100]} unit="%" {...AXIS} name="Predicted" />
              <YAxis type="number" domain={[0, 100]} unit="%" {...AXIS} />
              <Tooltip
                contentStyle={{ background: "var(--color-surface-2)", border: "1px solid var(--color-line-strong)", borderRadius: 12, color: "var(--color-ink)", fontSize: 13 }}
                formatter={(v, name) => [name === "n" ? v : `${v}%`, name]}
              />
              <Legend wrapperStyle={{ fontSize: 12, color: "var(--color-ink-muted)" }} />
              <Line data={[{ x: 0, ideal: 0 }, { x: 100, ideal: 100 }]} dataKey="ideal" name="Perfect calibration" stroke={token("ink-faint")} strokeDasharray="5 5" dot={false} />
              <Scatter dataKey="observed" name="Observed success" fill={token("strength")} />
            </ComposedChart>
          </ResponsiveContainer>
        ) : (
          <p className="text-sm text-ink-muted">No predictions recorded yet.</p>
        )}
      </Card>
    </div>
  );
}

export function AiTexts() {
  const r = useApi(() => adminApi.aiTexts(), []);
  if (r.loading) return <Spinner />;
  if (r.error) return <ErrorState error={r.error} onRetry={r.reload} />;
  const rows = r.data!;
  return (
    <Card>
      <CardTitle title="AI tutor texts" subtitle="Cached explanations and hints. Hide any that are wrong; students then see the skill hint or no explanation." />
      {rows.length === 0 ? (
        <p className="text-sm text-ink-muted">No AI texts yet.</p>
      ) : (
        <ul>
          {rows.map((t) => (
            <li key={t.id} className={cx("border-b border-line py-3 last:border-b-0", t.status === "hidden" && "opacity-60")}>
              <div className="flex flex-wrap items-center justify-between gap-2 text-xs text-ink-faint">
                <span>
                  <span className="font-semibold text-ink">{t.kind}</span>, question {t.item_id}, {t.answer_sig}, {t.model}, {timeAgo(t.created_at)}
                </span>
                <Button
                  size="sm"
                  variant="ghost"
                  icon={t.status === "ok" ? <EyeOff className="size-4" /> : <Eye className="size-4" />}
                  onClick={async () => {
                    await adminApi.setAiText(t.id, t.status === "ok" ? "hidden" : "ok");
                    r.reload();
                  }}
                >
                  {t.status === "ok" ? "Hide" : "Show again"}
                </Button>
              </div>
              <p className="mt-1 text-xs text-ink-muted">{t.question}</p>
              <div className="mt-2 rounded-lg bg-surface-2/60 p-3">
                <Markdown source={t.content} />
              </div>
            </li>
          ))}
        </ul>
      )}
    </Card>
  );
}
