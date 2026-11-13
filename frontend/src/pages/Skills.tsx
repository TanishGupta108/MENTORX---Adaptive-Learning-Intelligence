import { useMemo, useState } from "react";
import { Search } from "lucide-react";
import { tutor } from "../api/tutor";
import type { Status } from "../api/tutor";
import { useApi } from "../hooks/useApi";
import { useProfile } from "../components/AppShell";
import { Disclosure } from "../components/Disclosure";
import { SkillRow } from "../components/SkillRow";
import { cx, EmptyState, ErrorState, inputClass, PageHeader, PageLoader, STATUS_META } from "../components/ui";

const FILTERS: ("all" | Status)[] = ["all", "potential_weakness", "developing", "likely_strength", "needs_assessment"];

export function SkillsPage() {
  const { profile } = useProfile();
  const c = useApi(() => tutor.catalog(), [profile.subject_code]);
  const [q, setQ] = useState("");
  const [filter, setFilter] = useState<(typeof FILTERS)[number]>("all");
  // "" = all grades; default to the student's grade when the subject has grades
  const [grade, setGrade] = useState<string | null>(null);
  const [toggled, setToggled] = useState<Record<string, boolean>>({});

  const grades = useMemo(() => {
    const set = new Set<number>();
    for (const d of c.data?.domains ?? []) for (const s of d.skills) if (s.grade !== null) set.add(s.grade);
    return [...set].sort((a, b) => a - b);
  }, [c.data]);
  const defaultGrade = profile.grade != null && grades.includes(profile.grade) ? String(profile.grade) : "";
  const gradeValue = grades.length ? (grade ?? defaultGrade) : "";

  const domains = useMemo(() => {
    if (!c.data) return [];
    const needle = q.trim().toLowerCase();
    return c.data.domains
      .map((d) => ({
        ...d,
        skills: d.skills.filter(
          (s) =>
            (filter === "all" || s.status === filter) &&
            (gradeValue === "" || String(s.grade) === gradeValue) &&
            `${s.name} ${s.code} ${d.name}`.toLowerCase().includes(needle),
        ),
      }))
      .filter((d) => d.skills.length);
  }, [c.data, q, filter, gradeValue]);

  if (c.loading && !c.data) return <PageLoader label="Loading skills…" />;
  if (c.error) return <ErrorState error={c.error} onRetry={c.reload} />;
  const data = c.data!;
  const searching = q.trim().length > 0;

  return (
    <div>
      <PageHeader title="Skills" subtitle={data.subject.name} />
      <div className="mb-6 space-y-3">
        <div className="flex flex-col gap-3 sm:flex-row">
          <div className="relative flex-1">
            <Search className="pointer-events-none absolute left-3 top-3.5 size-4 text-ink-faint" aria-hidden />
            <label htmlFor="skill-search" className="sr-only">
              Search skills
            </label>
            <input id="skill-search" type="search" className={cx(inputClass, "pl-9")} placeholder={`Search ${data.n_skills} skills`} value={q} onChange={(e) => setQ(e.target.value)} />
          </div>
          {grades.length > 0 && (
            <div className="sm:w-44">
              <label htmlFor="grade-filter" className="sr-only">
                Grade
              </label>
              <select id="grade-filter" className={inputClass} value={gradeValue} onChange={(e) => setGrade(e.target.value)}>
                <option value="">All grades</option>
                {grades.map((g) => (
                  <option key={g} value={String(g)}>
                    Grade {g}
                  </option>
                ))}
              </select>
            </div>
          )}
        </div>
        <div className="flex flex-wrap gap-2" role="group" aria-label="Filter by status">
          {FILTERS.map((f) => (
            <button
              key={f}
              type="button"
              aria-pressed={filter === f}
              onClick={() => setFilter(f)}
              className={cx("min-h-11 rounded-full border px-3.5 text-sm font-medium sm:min-h-9", filter === f ? "border-brand bg-brand-soft text-ink" : "border-line text-ink-muted hover:text-ink")}
            >
              {f === "all" ? "All" : STATUS_META[f].label}
            </button>
          ))}
        </div>
      </div>

      <div className="space-y-3">
        {domains.map((d) => {
          const auto = searching || filter !== "all" || d.skills.some((s) => s.status !== "needs_assessment") || (profile.grade != null && d.skills.some((s) => s.grade === profile.grade));
          const open = toggled[d.code] ?? auto;
          return (
            <Disclosure
              key={d.code}
              open={open}
              onToggle={(o) => setToggled((t) => ({ ...t, [d.code]: o }))}
              title={
                <span>
                  {d.name} <span className="ml-1 text-sm font-normal text-ink-faint">{d.skills.length}</span>
                </span>
              }
            >
              <div className="-mx-3 -my-1 divide-y divide-line/60">
                {d.skills.map((s) => (
                  <SkillRow key={s.id} skill={s} />
                ))}
              </div>
            </Disclosure>
          );
        })}
        {!domains.length && (
          <EmptyState title="No skills match">
            Try another search{grades.length > 0 && gradeValue !== "" ? " or choose All grades" : ""}.
          </EmptyState>
        )}
      </div>
    </div>
  );
}
