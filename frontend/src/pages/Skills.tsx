import { useMemo, useState } from "react";
import { Search, Sigma } from "lucide-react";
import { tutor } from "../api/tutor";
import type { Status } from "../api/tutor";
import { useApi } from "../hooks/useApi";
import { SkillCard } from "../components/SkillCard";
import { cx, ErrorState, inputClass, PageHeader, PageLoader, STATUS_META } from "../components/ui";

const FILTERS: ("all" | Status)[] = ["all", "potential_weakness", "developing", "likely_strength", "needs_assessment"];

export function SkillsPage() {
  const c = useApi(() => tutor.catalog(), []);
  const [q, setQ] = useState("");
  const [filter, setFilter] = useState<(typeof FILTERS)[number]>("all");
  const domains = useMemo(() => {
    if (!c.data) return [];
    const needle = q.toLowerCase();
    return c.data.domains
      .map((d) => ({ ...d, skills: d.skills.filter((s) => (filter === "all" || s.status === filter) && `${s.name} ${s.code}`.toLowerCase().includes(needle)) }))
      .filter((d) => d.skills.length);
  }, [c.data, q, filter]);

  if (c.loading) return <PageLoader />;
  if (c.error) return <ErrorState error={c.error} onRetry={c.reload} />;
  const data = c.data!;

  return (
    <div>
      <PageHeader
        eyebrow="Subject"
        title={data.subject.name}
        subtitle={
          <span className="flex items-start gap-2">
            <Sigma className="mt-1 size-4 shrink-0 text-accent" />
            {data.subject.description}
          </span>
        }
      />
      <div className="mb-6 flex flex-col gap-3 lg:flex-row lg:items-center lg:justify-between">
        <div className="relative max-w-md flex-1">
          <Search className="pointer-events-none absolute left-3 top-3.5 size-4 text-ink-faint" />
          <input className={cx(inputClass, "pl-9")} placeholder={`Search ${data.n_skills} skills`} value={q} onChange={(e) => setQ(e.target.value)} />
        </div>
        <div className="flex flex-wrap gap-2">
          {FILTERS.map((f) => (
            <button key={f} type="button" onClick={() => setFilter(f)} className={cx("rounded-full border px-3 py-1.5 text-xs font-medium", filter === f ? "border-brand bg-brand-soft text-ink" : "border-line text-ink-muted hover:text-ink")}>
              {f === "all" ? "All skills" : STATUS_META[f].label}
            </button>
          ))}
        </div>
      </div>
      <div className="space-y-8">
        {domains.map((d) => (
          <section key={d.code}>
            <h2 className="mb-3 flex items-baseline gap-2 font-semibold">
              {d.name} <span className="text-sm font-normal text-ink-faint">{d.skills.length}</span>
            </h2>
            <div className="grid gap-3 md:grid-cols-2 xl:grid-cols-3">
              {d.skills.map((s) => (
                <SkillCard key={s.id} skill={s} />
              ))}
            </div>
          </section>
        ))}
        {!domains.length && <p className="text-ink-muted">No skills match.</p>}
      </div>
    </div>
  );
}
