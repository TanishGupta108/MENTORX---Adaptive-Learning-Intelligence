import { Link } from "react-router";
import { CalendarClock, CheckCircle2, ChevronRight } from "lucide-react";
import type { SkillSummary } from "../api/tutor";
import { cx, StatusBadge } from "./ui";

/** One skill as a calm row: name, plain status, one line of progress. No model numbers. */
export function SkillRow({ skill, note, className }: { skill: Pick<SkillSummary, "id" | "name" | "status"> & Partial<SkillSummary>; note?: string | null; className?: string }) {
  const hint = note ?? skill.mastery?.progress_hint ?? (skill.attempts ? `${skill.correct} of ${skill.attempts} correct` : null);
  return (
    <Link to={`/skills/${skill.id}`} className={cx("group flex min-h-14 items-center gap-3 rounded-xl px-3 py-2.5 hover:bg-surface-2", className)}>
      <span className="min-w-0 flex-1">
        <span className="flex items-center gap-2">
          <span className="truncate font-medium">{skill.name}</span>
          {skill.completed && <CheckCircle2 className="size-4 shrink-0 text-strength" aria-label="Completed" />}
          {skill.review_due && <CalendarClock className="size-4 shrink-0 text-accent" aria-label="Due for review" />}
        </span>
        {hint && <span className="block truncate text-sm text-ink-muted">{hint}</span>}
      </span>
      <StatusBadge status={skill.status} className="shrink-0" />
      <ChevronRight className="size-4 shrink-0 text-ink-faint transition-transform group-hover:translate-x-0.5" aria-hidden />
    </Link>
  );
}
