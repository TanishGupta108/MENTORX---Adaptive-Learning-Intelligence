import { useState } from "react";
import { useNavigate } from "react-router";
import { LogOut, Save } from "lucide-react";
import { tutor } from "../api/tutor";
import type { GoalKind, GoalType, Profile } from "../api/tutor";
import { useAuth } from "../auth/AuthContext";
import { useProfile } from "../components/AppShell";
import { Button, Card, CardTitle, cx, Field, inputClass, PageHeader } from "../components/ui";

const GOAL_TYPES: { id: GoalType; label: string }[] = [
  { id: "assess_overall", label: "Assess my overall knowledge" },
  { id: "improve_weak", label: "Improve my weak areas" },
  { id: "learn_topic", label: "Learn a specific topic" },
];
const PACES: { id: Profile["pace_preference"]; label: string; text: string }[] = [
  { id: "more_support", label: "More support", text: "Start one mode lower: more explanation, easier questions." },
  { id: "balanced", label: "Balanced", text: "Follow my evidence." },
  { id: "challenge", label: "Challenge me", text: "Start one mode higher: harder questions, less help." },
];
const GOAL_KINDS: { id: GoalKind; label: string; unit: string }[] = [
  { id: "strengthen_skills", label: "Build strong skills", unit: "skills" },
  { id: "weekly_practice", label: "Weekly practice", unit: "questions / 7 days" },
  { id: "master_skill", label: "Complete my focus topic", unit: "topic" },
];

export function ProfilePage() {
  const { profile, reload } = useProfile();
  const { logout } = useAuth();
  const navigate = useNavigate();
  const [pace, setPace] = useState(profile.pace_preference);
  const [hints, setHints] = useState(profile.hints_enabled);
  const [goalType, setGoalType] = useState<GoalType>(profile.goal_type ?? "assess_overall");
  const [goalKind, setGoalKind] = useState<GoalKind>(profile.goal?.kind ?? "strengthen_skills");
  const [target, setTarget] = useState(profile.goal?.target ?? 3);
  const [saved, setSaved] = useState<string>();
  const [busy, setBusy] = useState(false);

  async function save() {
    setBusy(true);
    setSaved(undefined);
    try {
      await tutor.updateProfile({ pace_preference: pace, hints_enabled: hints, goal_type: goalType === "learn_topic" && !profile.focus_skill ? profile.goal_type ?? "assess_overall" : goalType });
      if (goalKind !== profile.goal?.kind || target !== profile.goal?.target) {
        await tutor.setGoal({ kind: goalKind, target, skill_id: goalKind === "master_skill" ? profile.focus_skill?.id : null });
      }
      await reload();
      setSaved("Saved. Your recommendations have been updated.");
    } catch (e) {
      setSaved((e as Error).message);
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="mx-auto max-w-3xl">
      <PageHeader eyebrow="Profile & settings" title={profile.full_name} subtitle={profile.email} actions={<Button variant="secondary" onClick={async () => { await logout(); navigate("/"); }} icon={<LogOut className="size-4" />}>Log out</Button>} />
      <div className="space-y-6">
        <Card>
          <CardTitle title="Learning" />
          <dl className="grid gap-4 text-sm sm:grid-cols-2">
            <div>
              <dt className="text-ink-faint">Subject</dt>
              <dd className="mt-0.5 font-medium">{profile.subject ?? "Mathematics"}</dd>
            </div>
            <div>
              <dt className="text-ink-faint">Focus topic</dt>
              <dd className="mt-0.5 font-medium">{profile.focus_skill ? `${profile.focus_skill.name} (${profile.focus_skill.code})` : "None chosen"}</dd>
            </div>
          </dl>
          <div className="mt-5">
            <p className="mb-2 text-sm font-medium">What I want to achieve</p>
            <div className="flex flex-wrap gap-2">
              {GOAL_TYPES.map((g) => (
                <button key={g.id} type="button" disabled={g.id === "learn_topic" && !profile.focus_skill} onClick={() => setGoalType(g.id)} className={cx("rounded-xl border px-3 py-2 text-sm disabled:opacity-40", goalType === g.id ? "border-brand bg-brand-soft" : "border-line hover:bg-surface-2")}>
                  {g.label}
                </button>
              ))}
            </div>
          </div>
        </Card>

        <Card>
          <CardTitle title="Learning goal" />
          <div className="grid gap-4 sm:grid-cols-[1fr_160px]">
            <Field label="Goal">
              <select className={inputClass} value={goalKind} onChange={(e) => setGoalKind(e.target.value as GoalKind)}>
                {GOAL_KINDS.filter((g) => g.id !== "master_skill" || profile.focus_skill).map((g) => (
                  <option key={g.id} value={g.id}>{g.label}</option>
                ))}
              </select>
            </Field>
            <Field label={`Target (${GOAL_KINDS.find((g) => g.id === goalKind)?.unit})`}>
              <input className={inputClass} type="number" min={1} max={500} value={target} onChange={(e) => setTarget(Math.max(1, Math.min(500, Number(e.target.value) || 1)))} disabled={goalKind === "master_skill"} />
            </Field>
          </div>
          {profile.goal && <p className="mt-3 text-sm text-ink-muted">Current: {profile.goal.label}. Progress {profile.goal.value}/{profile.goal.target}.</p>}
        </Card>

        <Card>
          <CardTitle title="Learning preferences" subtitle="Your pace preference shifts every skill's learning mode. You can also set a mode for a single skill on its page." />
          <div className="grid gap-2 sm:grid-cols-3">
            {PACES.map((p) => (
              <button key={p.id} type="button" onClick={() => setPace(p.id)} className={cx("rounded-xl border p-3 text-left text-sm", pace === p.id ? "border-brand bg-brand-soft" : "border-line hover:bg-surface-2")}>
                <span className="font-semibold">{p.label}</span>
                <span className="mt-1 block text-xs text-ink-muted">{p.text}</span>
              </button>
            ))}
          </div>
          <label className="mt-5 flex items-center justify-between gap-4 rounded-xl border border-line p-3 text-sm">
            <span>
              <span className="font-medium">Offer hints during practice</span>
              <span className="block text-xs text-ink-muted">Hints remind you of the key idea. A correct answer after a hint counts as "with help".</span>
            </span>
            <input type="checkbox" className="size-5 accent-[#8b8cff]" checked={hints} onChange={(e) => setHints(e.target.checked)} />
          </label>
        </Card>

        <div className="flex items-center gap-4">
          <Button onClick={save} loading={busy} icon={<Save className="size-4" />}>
            Save changes
          </Button>
          {saved && <p className="text-sm text-ink-muted" role="status">{saved}</p>}
        </div>
      </div>
    </div>
  );
}
