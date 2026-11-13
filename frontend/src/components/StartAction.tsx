/**
 * Launches a "next thing to do" in one click: starts the practice session or assessment on the
 * server and opens it, resumes an active one, or opens a skill's Learn tab.
 */
import { useState } from "react";
import type { ReactNode } from "react";
import { useNavigate } from "react-router";
import { ArrowRight } from "lucide-react";
import { ApiError } from "../api/client";
import { tutor } from "../api/tutor";
import type { NextAction, PracticeKind, PracticeSummary, SkillDetail, StartSpec } from "../api/tutor";
import { Button } from "./ui";

/** Everything StartSpec can do, plus Mixed practice (not a recommendation, but started the same way). */
export type Launch = StartSpec | { endpoint: "mixed" };

export function useLauncher() {
  const navigate = useNavigate();
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string>();

  async function launch(spec: Launch) {
    setError(undefined);
    const openPractice = (id: string, kind: PracticeKind) => navigate(`/practice/${id}`, { state: { kind } });
    switch (spec.endpoint) {
      case "resume_practice":
        return navigate(`/practice/${spec.session_id}`);
      case "resume_assessment":
        return navigate(`/assess/${spec.assessment_id}`);
      case "learn":
        return navigate(`/skills/${spec.skill_id}?tab=learn`);
    }
    setBusy(true);
    try {
      if (spec.endpoint === "practice") {
        const p = await tutor.startPractice(spec.skill_id, spec.guided);
        openPractice(p.id, "skill");
      } else if (spec.endpoint === "review") {
        const p = await tutor.startReview();
        openPractice(p.id, "review");
      } else if (spec.endpoint === "mixed") {
        const p = await tutor.startMixed();
        openPractice(p.id, "mixed");
      } else {
        const a = await tutor.startAssessment(spec.kind, spec.skill_id ?? undefined);
        navigate(`/assess/${a.id}`);
      }
    } catch (e) {
      setError(e instanceof ApiError ? e.message : "Couldn't start. Please try again.");
      setBusy(false);
    }
  }

  return { launch, busy, error };
}

/** Map a skill page's `next_activity` or a practice summary's `next` to a launch. */
export function launchFor(action: SkillDetail["next_activity"]["action"] | PracticeSummary["next"]["action"], skillId: number | null, targetSkillId?: number): Launch | null {
  switch (action) {
    case "skill_check":
      return skillId === null ? null : { endpoint: "assessment", kind: "skill_check", skill_id: skillId };
    case "reassess":
      return skillId === null ? null : { endpoint: "assessment", kind: "reassessment", skill_id: skillId };
    case "practice":
      return skillId === null ? null : { endpoint: "practice", skill_id: skillId, guided: false };
    case "foundation":
      return skillId === null ? null : { endpoint: "practice", skill_id: skillId, guided: true };
    case "prerequisite": {
      const id = targetSkillId ?? skillId;
      return id === null ? null : { endpoint: "practice", skill_id: id, guided: true };
    }
    case "learn":
      return skillId === null ? null : { endpoint: "learn", skill_id: skillId };
    case "review":
      return { endpoint: "review" };
    case "mixed":
      return { endpoint: "mixed" };
    case "home":
      return null; // the summary already has "Back to Home"
  }
}

type BtnProps = {
  action: NextAction | Launch;
  children?: ReactNode;
  variant?: "primary" | "secondary" | "soft";
  size?: "sm" | "md" | "lg";
  className?: string;
};

/** A Start button for a NextAction (or a raw launch spec). Shows its own error underneath. */
export function StartButton({ action, children = "Start", variant = "primary", size = "md", className }: BtnProps) {
  const { launch, busy, error } = useLauncher();
  const spec: Launch = "start" in action ? action.start : action;
  return (
    <div className={className}>
      <Button variant={variant} size={size} onClick={() => void launch(spec)} loading={busy} icon={busy ? undefined : <ArrowRight className="size-4" />}>
        {children}
      </Button>
      {error && (
        <p className="mt-2 text-sm text-developing" role="alert">
          {error}
        </p>
      )}
    </div>
  );
}
