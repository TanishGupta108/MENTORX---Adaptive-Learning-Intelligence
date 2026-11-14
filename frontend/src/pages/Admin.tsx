import { useState } from "react";
import { Navigate } from "react-router";
import { Bot, Plus, Trash2 } from "lucide-react";
import { ApiError } from "../api/client";
import { adminApi } from "../api/tutor";
import type { AdminSkill, AiTest } from "../api/tutor";
import { useApi } from "../hooks/useApi";
import { useProfile, useSubjects } from "../components/AppShell";
import { AiTexts, ModelMonitor } from "../components/AdminMonitor";
import { Button, Card, CardTitle, cx, ErrorState, Field, inputClass, PageHeader, Spinner, Stat } from "../components/ui";

const TABS = ["Overview", "Model monitor", "AI tutor", "Skills & questions", "Resources", "Prerequisites"] as const;

function TestAi() {
  const [busy, setBusy] = useState(false);
  const [res, setRes] = useState<AiTest | null>(null);
  const [err, setErr] = useState<string>();
  async function run() {
    setBusy(true);
    setErr(undefined);
    setRes(null);
    try {
      setRes(await adminApi.testAi());
    } catch (e) {
      setErr(e instanceof ApiError ? e.message : "The test request failed.");
    } finally {
      setBusy(false);
    }
  }
  return (
    <Card>
      <CardTitle title="Test the AI tutor" subtitle="Sends a tiny prompt through the same model chain the students use. The key is never shown." />
      <Button onClick={run} loading={busy} icon={<Bot className="size-4" />}>
        {busy ? "Testing… up to a minute" : "Test AI"}
      </Button>
      {res && (
        <div className={cx("mt-4 rounded-xl p-3 text-sm", res.ok ? "bg-strength/10" : "bg-weakness/10")} role="status">
          <p className="font-medium">{res.ok ? "OK: the AI tutor answered." : "Not working."}</p>
          <p className="mt-1 text-ink-muted">{res.message}</p>
          <p className="mt-1 text-xs text-ink-faint">
            Model: {res.model ?? "none"}. Time: {res.latency_ms === null ? "none" : `${(res.latency_ms / 1000).toFixed(1)} s`}
            {res.error_code ? `. Error: ${res.error_code}` : ""}
          </p>
        </div>
      )}
      {err && (
        <p className="mt-3 text-sm text-danger" role="alert">
          {err}
        </p>
      )}
    </Card>
  );
}

function Overview({ subject }: { subject: string }) {
  const o = useApi(() => adminApi.overview(subject), [subject]);
  if (o.loading) return <Spinner />;
  if (o.error) return <ErrorState error={o.error} onRetry={o.reload} />;
  const d = o.data!;
  return (
    <div className="space-y-6">
      <div className="grid grid-cols-2 gap-3 lg:grid-cols-4">
        <Stat label="Skills available" value={`${d.available_skills}/${d.skills}`} />
        <Stat label="Usable questions" value={`${d.usable_items}/${d.items}`} hint={`${d.usable_mixed_items} of them multi-skill (Mixed practice)`} />
        <Stat label="Resources" value={d.resources} />
        <Stat label="Prerequisite links" value={d.prerequisites} />
      </div>
      <Card>
        <CardTitle title="Why questions are excluded" subtitle="Stored but never served. Admin-disabled questions are counted separately." />
        <ul className="space-y-1.5 text-sm">
          {d.exclusions.map((e) => (
            <li key={e.reason} className="flex justify-between rounded-lg bg-surface-2/60 px-3 py-2">
              <span>{e.reason.replaceAll("_", " ")}</span>
              <span className="font-semibold">{e.count}</span>
            </li>
          ))}
        </ul>
        <p className="mt-3 text-xs text-ink-faint">Disabled by an admin: {d.disabled_by_admin}</p>
      </Card>
    </div>
  );
}

function SkillsTab({ subject }: { subject: string }) {
  const [q, setQ] = useState("");
  const [query, setQuery] = useState("");
  const skills = useApi(() => adminApi.skills(query, subject), [query, subject]);
  const [sel, setSel] = useState<AdminSkill | null>(null);
  const [desc, setDesc] = useState("");
  const items = useApi(() => (sel ? adminApi.items(sel.id) : Promise.resolve([])), [sel?.id]);
  const [msg, setMsg] = useState<string>();
  return (
    <div className="grid gap-6 lg:grid-cols-[340px_1fr]">
      <Card>
        <form onSubmit={(e) => { e.preventDefault(); setQuery(q); }}>
          <input className={inputClass} placeholder="Search skills" value={q} onChange={(e) => setQ(e.target.value)} />
        </form>
        <div className="mt-3 max-h-[560px] space-y-1 overflow-y-auto">
          {skills.data?.map((s) => (
            <button key={s.id} type="button" onClick={() => { setSel(s); setDesc(s.description); setMsg(undefined); }} className={cx("block w-full rounded-lg px-3 py-2 text-left text-sm", sel?.id === s.id ? "bg-brand-soft" : "hover:bg-surface-2")}>
              <span className="font-medium">{s.code}</span> <span className="text-ink-muted">{s.name}</span>
              <span className="block text-xs text-ink-faint">{s.n_items} usable, {s.is_available ? "available" : "hidden (fewer than 5 usable)"}</span>
            </button>
          ))}
        </div>
      </Card>
      {sel ? (
        <div className="space-y-6">
          <Card>
            <CardTitle title={`${sel.code} ${sel.name}`} subtitle={sel.domain_name} />
            <Field label="Description shown to students">
              <textarea className={cx(inputClass, "h-28 py-2")} value={desc} onChange={(e) => setDesc(e.target.value)} />
            </Field>
            <Button className="mt-3" size="sm" onClick={async () => { await adminApi.updateSkill(sel.id, desc); setMsg("Saved"); }}>Save description</Button>
            {msg && <span className="ml-3 text-sm text-strength">{msg}</span>}
          </Card>
          <Card>
            <CardTitle title="Questions" subtitle="Turn off any question that renders badly or has a doubtful answer key." />
            {items.loading ? <Spinner /> : (
              <div className="max-h-[520px] space-y-1.5 overflow-y-auto">
                {items.data?.map((i) => (
                  <div key={i.id} className="flex items-start gap-3 rounded-lg bg-surface-2/60 px-3 py-2 text-sm">
                    <span className="min-w-0 flex-1">
                      <span className="block truncate">{i.preview}</span>
                      <span className="block text-xs text-ink-faint">#{i.id}, {i.answer_type}, {i.difficulty}{i.exclusion_reason ? `, excluded: ${i.exclusion_reason}` : ""}</span>
                    </span>
                    {!i.exclusion_reason && (
                      <Button size="sm" variant={i.is_active ? "secondary" : "soft"} onClick={async () => { await adminApi.setItem(i.id, !i.is_active); items.reload(); }}>
                        {i.is_active ? "Disable" : "Enable"}
                      </Button>
                    )}
                  </div>
                ))}
              </div>
            )}
          </Card>
        </div>
      ) : (
        <p className="text-ink-muted">Choose a skill.</p>
      )}
    </div>
  );
}

function ResourcesTab() {
  const res = useApi(() => adminApi.resources(), []);
  const [form, setForm] = useState({ skill_id: "", kind: "notes", title: "", url: "", content_md: "", minutes: "5", source_label: "Added by an administrator" });
  const [err, setErr] = useState<string>();
  async function create() {
    setErr(undefined);
    try {
      await adminApi.createResource({
        skill_id: form.skill_id ? Number(form.skill_id) : null,
        kind: form.kind,
        title: form.title,
        url: form.url || null,
        content_md: form.content_md || null,
        minutes: Number(form.minutes) || 5,
        source_label: form.source_label,
      });
      setForm({ ...form, title: "", url: "", content_md: "" });
      res.reload();
    } catch (e) {
      setErr(e instanceof ApiError ? Object.values(e.fields)[0] ?? e.message : "Couldn't save.");
    }
  }
  return (
    <div className="grid gap-6 lg:grid-cols-[380px_1fr]">
      <Card>
        <CardTitle title="Add a resource" subtitle="Only add genuine links you have checked. Written notes use the simple Markdown format." />
        <div className="space-y-3">
          <Field label="Skill ID"><input className={inputClass} value={form.skill_id} onChange={(e) => setForm({ ...form, skill_id: e.target.value })} placeholder="e.g. 198" /></Field>
          <Field label="Kind">
            <select className={inputClass} value={form.kind} onChange={(e) => setForm({ ...form, kind: e.target.value })}>
              {["notes", "worked_example", "video", "article", "practice_tip", "standard"].map((k) => <option key={k}>{k}</option>)}
            </select>
          </Field>
          <Field label="Title"><input className={inputClass} value={form.title} onChange={(e) => setForm({ ...form, title: e.target.value })} /></Field>
          <Field label="URL (https)" hint="Leave empty for written content"><input className={inputClass} value={form.url} onChange={(e) => setForm({ ...form, url: e.target.value })} /></Field>
          <Field label="Content (Markdown)"><textarea className={cx(inputClass, "h-32 py-2")} value={form.content_md} onChange={(e) => setForm({ ...form, content_md: e.target.value })} /></Field>
          <Field label="Source"><input className={inputClass} value={form.source_label} onChange={(e) => setForm({ ...form, source_label: e.target.value })} /></Field>
          {err && <p className="text-sm text-danger">{err}</p>}
          <Button onClick={create} icon={<Plus className="size-4" />}>Add resource</Button>
        </div>
      </Card>
      <Card>
        <CardTitle title="All resources" subtitle={res.data ? `${res.data.length} resources` : undefined} />
        {res.loading ? <Spinner /> : (
          <div className="max-h-[640px] space-y-1.5 overflow-y-auto">
            {res.data?.filter((r) => r.kind !== "standard").map((r) => (
              <div key={r.id} className="flex items-center gap-3 rounded-lg bg-surface-2/60 px-3 py-2 text-sm">
                <span className="min-w-0 flex-1">
                  <span className="block truncate font-medium">{r.title}</span>
                  <span className="block text-xs text-ink-faint">skill {r.skill_id}, {r.kind}, {r.source_label}</span>
                </span>
                <button type="button" className="rounded-lg p-2 text-ink-muted hover:bg-danger/15 hover:text-danger" aria-label="Delete resource" onClick={async () => { if (confirm(`Delete "${r.title}"?`)) { await adminApi.deleteResource(r.id); res.reload(); } }}>
                  <Trash2 className="size-4" />
                </button>
              </div>
            ))}
          </div>
        )}
      </Card>
    </div>
  );
}

function PrereqTab() {
  const p = useApi(() => adminApi.prerequisites(), []);
  const [skill, setSkill] = useState("");
  const [pre, setPre] = useState("");
  const [err, setErr] = useState<string>();
  return (
    <Card>
      <CardTitle title="Curated prerequisites" subtitle="Only add links that reflect the curriculum. Never infer them from a student's results." />
      <div className="mb-4 flex flex-wrap items-end gap-3">
        <Field label="Skill ID"><input className={cx(inputClass, "w-32")} value={skill} onChange={(e) => setSkill(e.target.value)} /></Field>
        <Field label="Requires skill ID"><input className={cx(inputClass, "w-32")} value={pre} onChange={(e) => setPre(e.target.value)} /></Field>
        <Button onClick={async () => { setErr(undefined); try { await adminApi.addPrerequisite(Number(skill), Number(pre)); p.reload(); } catch (e) { setErr((e as Error).message); } }} icon={<Plus className="size-4" />}>Add link</Button>
        {err && <p className="text-sm text-danger">{err}</p>}
      </div>
      {p.loading ? <Spinner /> : (
        <div className="max-h-[560px] space-y-1.5 overflow-y-auto">
          {p.data?.map((l) => (
            <div key={`${l.skill_id}-${l.prerequisite_id}`} className="flex items-center gap-3 rounded-lg bg-surface-2/60 px-3 py-2 text-sm">
              <span className="min-w-0 flex-1">
                <span className="block truncate">{l.skill}</span>
                <span className="block truncate text-xs text-ink-faint">requires {l.prerequisite} ({l.source})</span>
              </span>
              <button type="button" className="rounded-lg p-2 text-ink-muted hover:bg-danger/15 hover:text-danger" aria-label="Remove link" onClick={async () => { await adminApi.removePrerequisite(l.skill_id, l.prerequisite_id); p.reload(); }}>
                <Trash2 className="size-4" />
              </button>
            </div>
          ))}
        </div>
      )}
    </Card>
  );
}

export function AdminPage() {
  const { profile } = useProfile();
  const { subjects } = useSubjects();
  const [tab, setTab] = useState<(typeof TABS)[number]>("Overview");
  const [subject, setSubject] = useState("MATH");
  if (!profile.is_admin) return <Navigate to="/home" replace />;
  const subjectOptions = subjects?.length ? subjects.map((s) => ({ code: s.code, name: s.name })) : [{ code: "MATH", name: "Mathematics" }];
  const bySubject = tab === "Overview" || tab === "Model monitor" || tab === "Skills & questions";
  return (
    <div>
      <PageHeader
        title="Content admin"
        subtitle="Resources, skill descriptions, question availability, prerequisite links, the model and the AI tutor."
        actions={
          bySubject && subjectOptions.length > 1 ? (
            <label className="flex items-center gap-2 text-sm text-ink-muted">
              Subject
              <select className={cx(inputClass, "h-10 w-auto")} value={subject} onChange={(e) => setSubject(e.target.value)}>
                {subjectOptions.map((s) => (
                  <option key={s.code} value={s.code}>
                    {s.name}
                  </option>
                ))}
              </select>
            </label>
          ) : undefined
        }
      />
      <div className="mb-6 flex flex-wrap gap-2">
        {TABS.map((t) => (
          <button key={t} type="button" onClick={() => setTab(t)} className={cx("rounded-full border px-3.5 py-1.5 text-sm", tab === t ? "border-brand bg-brand-soft" : "border-line text-ink-muted hover:text-ink")}>
            {t}
          </button>
        ))}
      </div>
      {tab === "Overview" && <Overview subject={subject} />}
      {tab === "Model monitor" && <ModelMonitor subject={subject} />}
      {tab === "AI tutor" && (
        <div className="space-y-6">
          <TestAi />
          <AiTexts />
        </div>
      )}
      {tab === "Skills & questions" && <SkillsTab key={subject} subject={subject} />}
      {tab === "Resources" && <ResourcesTab />}
      {tab === "Prerequisites" && <PrereqTab />}
    </div>
  );
}

