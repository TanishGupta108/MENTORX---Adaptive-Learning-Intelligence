import { useEffect, useState } from "react";
import { useLocation, useNavigate } from "react-router";
import { LogOut, Save } from "lucide-react";
import { ApiError } from "../api/client";
import { tutor } from "../api/tutor";
import type { GoalKind, GoalType, Pace } from "../api/tutor";
import { useAuth } from "../auth/AuthContext";
import { useProfile, useSubjects } from "../components/AppShell";
import { Credits } from "../components/Credits";
import { Button, Card, CardTitle, cx, Field, inputClass, PageHeader } from "../components/ui";

const GOAL_TYPES: { id: GoalType; label: string }[] = [
  { id: "assess_overall", label: "Check what I know" },
  { id: "improve_weak", label: "Improve my weak areas" },
  { id: "learn_topic", label: "Learn one topic" },
];
const PACES: { id: Pace; label: string; text: string }[] = [
  { id: "more_support", label: "More support", text: "Easier questions first, more help." },
  { id: "balanced", label: "Balanced", text: "Follow my answers." },
  { id: "challenge", label: "Challenge me", text: "Harder questions sooner, less help." },
];
const GOAL_KINDS: { id: GoalKind; label: string; unit: string }[] = [
  { id: "weekly_practice", label: "Practise regularly", unit: "questions every 7 days" },
  { id: "strengthen_skills", label: "Build strong skills", unit: "skills" },
  { id: "master_skill", label: "Complete my focus topic", unit: "topic" },
];

function Subjects() {
  const { profile, reload } = useProfile();
  const { subjects, reload: reloadSubjects } = useSubjects();
  const navigate = useNavigate();
  const [busy, setBusy] = useState<string | null>(null);
  const [err, setErr] = useState<string>();
  if (!subjects || subjects.length < 2) return null;
  async function choose(code: string) {
    setBusy(code);
    setErr(undefined);
    try {
      await tutor.setSubject(code);
      await reload();
      reloadSubjects();
      navigate("/home");
    } catch (e) {
      setErr(e instanceof ApiError ? e.message : "Couldn't switch subject.");
      setBusy(null);
    }
  }
  return (
    <Card>
      <CardTitle title="Subjects" />
      <ul className="space-y-2">
        {subjects.map((s) => {
          const current = s.code === profile.subject_code || (profile.subject_code == null && s.current);
          return (
            <li key={s.code} className="flex flex-wrap items-center justify-between gap-3 rounded-xl border border-line px-4 py-3">
              <span className="min-w-0">
                <span className="block font-medium">{s.name}</span>
                <span className="block text-sm text-ink-muted">{s.enrolled ? (s.diagnostic_completed ? "Placement check done" : "Started") : `${s.n_skills} skills`}</span>
                {s.code === "GEO" && <span className="mt-1 block text-xs text-ink-faint">{s.attribution}</span>}
              </span>
              {current ? (
                <span className="rounded-full bg-brand-soft px-2.5 py-1 text-xs font-medium text-brand">Current</span>
              ) : (
                <Button variant="secondary" size="sm" loading={busy === s.code} onClick={() => choose(s.code)}>
                  {s.enrolled ? "Switch" : "Start"}
                </Button>
              )}
            </li>
          );
        })}
      </ul>
      {err && (
        <p className="mt-2 text-sm text-developing" role="alert">
          {err}
        </p>
      )}
    </Card>
  );
}

export function ProfilePage() {
  const { profile, reload } = useProfile();
  const { subjects } = useSubjects();
  const { logout } = useAuth();
  const navigate = useNavigate();
  const location = useLocation();
  const [pace, setPace] = useState<Pace>(profile.pace_preference);
  const [hints, setHints] = useState(profile.hints_enabled);
  const [daily, setDaily] = useState(profile.daily_goal ?? 10);
  const [grade, setGrade] = useState<string>(profile.grade == null ? "" : String(profile.grade));
  const [goalType, setGoalType] = useState<GoalType>(profile.goal_type ?? "assess_overall");
  const [goalKind, setGoalKind] = useState<GoalKind>(profile.goal?.kind ?? "weekly_practice");
  const [target, setTarget] = useState(profile.goal?.target ?? 30);
  const [saved, setSaved] = useState<string>();
  const [busy, setBusy] = useState(false);

  const current = subjects?.find((s) => s.code === profile.subject_code) ?? subjects?.find((s) => s.current);
  const hasGrades = current ? current.grades : (profile.subject_code ?? "MATH") === "MATH";

  useEffect(() => {
    if (location.hash === "#credits") document.getElementById("credits")?.scrollIntoView?.({ block: "start" });
  }, [location.hash]);

  async function save() {
    setBusy(true);
    setSaved(undefined);
    try {
      await tutor.updateProfile({
        pace_preference: pace,
        hints_enabled: hints,
        daily_goal: daily,
        goal_type: goalType === "learn_topic" && !profile.focus_skill ? (profile.goal_type ?? "assess_overall") : goalType,
        ...(hasGrades ? { grade: grade === "" ? null : Number(grade) } : {}),
      });
      if (goalKind !== profile.goal?.kind || target !== profile.goal?.target) {
        await tutor.setGoal({ kind: goalKind, target, skill_id: goalKind === "master_skill" ? profile.focus_skill?.id : null });
      }
      await reload();
      setSaved("Saved.");
    } catch (e) {
      setSaved((e as Error).message);
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="mx-auto max-w-2xl">
      <PageHeader title={profile.full_name} subtitle={profile.email} />
      <div className="space-y-6">
        <Card>
          <CardTitle title="How you learn" />
          <div className="space-y-5">
            {hasGrades && (
              <Field label="Grade">
                <select className={cx(inputClass, "max-w-xs")} value={grade} onChange={(e) => setGrade(e.target.value)}>
                  <option value="">Not sure</option>
                  {[3, 4, 5, 6, 7, 8].map((g) => (
                    <option key={g} value={String(g)}>
                      Grade {g}
                    </option>
                  ))}
                </select>
              </Field>
            )}
            <div>
              <p className="mb-2 text-sm font-medium">Pace</p>
              <div className="grid gap-2 sm:grid-cols-3">
                {PACES.map((p) => (
                  <button key={p.id} type="button" aria-pressed={pace === p.id} onClick={() => setPace(p.id)} className={cx("min-h-11 rounded-xl border p-3 text-left text-sm", pace === p.id ? "border-brand bg-brand-soft" : "border-line hover:bg-surface-2")}>
                    <span className="font-semibold">{p.label}</span>
                    <span className="mt-1 block text-xs text-ink-muted">{p.text}</span>
                  </button>
                ))}
              </div>
            </div>
            <label className="flex min-h-11 items-center justify-between gap-4 rounded-xl border border-line p-3 text-sm">
              <span>
                <span className="font-medium">Offer hints during practice</span>
                <span className="block text-xs text-ink-muted">A right answer after a hint counts as &quot;with help&quot;.</span>
              </span>
              <input type="checkbox" className="size-5 accent-[#8b8cff]" checked={hints} onChange={(e) => setHints(e.target.checked)} />
            </label>
          </div>
        </Card>

        <Card>
          <CardTitle title="Goals" />
          <div className="space-y-5">
            <div className="max-w-xs">
              <Field label="Daily goal (questions per day)">
                <input className={inputClass} type="number" min={1} max={200} value={daily} onChange={(e) => setDaily(Math.max(1, Math.min(200, Number(e.target.value) || 1)))} />
              </Field>
            </div>
            <div className="grid gap-4 sm:grid-cols-[1fr_160px]">
              <Field label="Learning goal">
                <select className={inputClass} value={goalKind} onChange={(e) => setGoalKind(e.target.value as GoalKind)}>
                  {GOAL_KINDS.filter((g) => g.id !== "master_skill" || profile.focus_skill).map((g) => (
                    <option key={g.id} value={g.id}>
                      {g.label}
                    </option>
                  ))}
                </select>
              </Field>
              <Field label={`Target (${GOAL_KINDS.find((g) => g.id === goalKind)?.unit})`}>
                <input className={inputClass} type="number" min={1} max={500} value={target} onChange={(e) => setTarget(Math.max(1, Math.min(500, Number(e.target.value) || 1)))} disabled={goalKind === "master_skill"} />
              </Field>
            </div>
            {profile.goal && (
              <p className="text-sm text-ink-muted">
                Now: {profile.goal.label} ({profile.goal.value}/{profile.goal.target})
              </p>
            )}
            <div>
              <p className="mb-2 text-sm font-medium">What I want to do</p>
              <div className="flex flex-wrap gap-2">
                {GOAL_TYPES.map((g) => (
                  <button
                    key={g.id}
                    type="button"
                    aria-pressed={goalType === g.id}
                    disabled={g.id === "learn_topic" && !profile.focus_skill}
                    onClick={() => setGoalType(g.id)}
                    className={cx("min-h-11 rounded-xl border px-3 text-sm disabled:opacity-40", goalType === g.id ? "border-brand bg-brand-soft" : "border-line hover:bg-surface-2")}
                  >
                    {g.label}
                  </button>
                ))}
              </div>
              {profile.focus_skill && <p className="mt-2 text-xs text-ink-muted">Focus topic: {profile.focus_skill.name}</p>}
            </div>
          </div>
        </Card>

        <div className="flex flex-wrap items-center gap-4">
          <Button onClick={save} loading={busy} icon={<Save className="size-4" />}>
            Save changes
          </Button>
          {saved && (
            <p className="text-sm text-ink-muted" role="status">
              {saved}
            </p>
          )}
        </div>

        <Subjects />

        <section id="credits" className="scroll-mt-24">
          <Card>
            <CardTitle title="Data & credits" />
            <Credits subjects={subjects} />
          </Card>
        </section>

        <Button
          variant="secondary"
          onClick={async () => {
            await logout();
            navigate("/");
          }}
          icon={<LogOut className="size-4" />}
        >
          Log out
        </Button>
      </div>
    </div>
  );
}
