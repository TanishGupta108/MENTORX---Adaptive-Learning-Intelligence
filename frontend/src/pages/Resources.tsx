import { useState } from "react";
import { BookOpen, Search } from "lucide-react";
import { tutor } from "../api/tutor";
import { useApi } from "../hooks/useApi";
import { ResourceCard } from "../components/ResourceCard";
import { cx, EmptyState, ErrorState, inputClass, PageHeader, PageLoader } from "../components/ui";

const KINDS = [
  { id: "", label: "Notes & examples" },
  { id: "notes", label: "Concept notes" },
  { id: "worked_example", label: "Worked examples" },
  { id: "standard", label: "Official standards" },
];

export function ResourcesPage() {
  const [kind, setKind] = useState("");
  const [q, setQ] = useState("");
  const [query, setQuery] = useState("");
  const r = useApi(() => tutor.resources({ kind, q: query }), [kind, query]);
  return (
    <div>
      <PageHeader
        eyebrow="Resource library"
        title="Learn the ideas behind the questions"
        subtitle="Concept notes and worked examples written for MENTORX, plus the official Common Core standard for every skill. Completing a resource doesn't change your skill estimates. Your answers do."
      />
      <div className="mb-6 flex flex-col gap-3 lg:flex-row lg:items-center lg:justify-between">
        <form className="relative max-w-md flex-1" onSubmit={(e) => { e.preventDefault(); setQuery(q); }}>
          <Search className="pointer-events-none absolute left-3 top-3.5 size-4 text-ink-faint" />
          <input className={cx(inputClass, "pl-9")} placeholder="Search by topic or skill code, then press Enter" value={q} onChange={(e) => setQ(e.target.value)} />
        </form>
        <div className="flex flex-wrap gap-2">
          {KINDS.map((k) => (
            <button key={k.id} type="button" onClick={() => setKind(k.id)} className={cx("rounded-full border px-3 py-1.5 text-xs font-medium", kind === k.id ? "border-brand bg-brand-soft text-ink" : "border-line text-ink-muted hover:text-ink")}>
              {k.label}
            </button>
          ))}
        </div>
      </div>
      {r.loading && <PageLoader />}
      {r.error && <ErrorState error={r.error} onRetry={r.reload} />}
      {r.data && r.data.length === 0 && (
        <EmptyState icon={<BookOpen className="size-8" />} title="Nothing found">
          Try another search. Skills without written notes can still be practised from their skill page.
        </EmptyState>
      )}
      {r.data && r.data.length > 0 && (
        <div className="grid gap-3 lg:grid-cols-2">
          {r.data.map((res) => (
            <ResourceCard key={res.id} resource={res} showSkill />
          ))}
        </div>
      )}
    </div>
  );
}
