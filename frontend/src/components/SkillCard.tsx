import { Link } from "react-router";
import { ChevronRight } from "lucide-react";
import type { SkillSummary } from "../api/tutor";
import { cx, EvidenceMeter, ModelEstimate, pct, StatusBadge } from "./ui";

/** One skill with its evidence. Observed numbers and the model estimate are labelled apart. */
export function SkillCard({ skill, compact = false, explain }: { skill: SkillSummary; compact?: boolean; explain?: string }) {
  return (
    <Link
      to={`/skills/${skill.id}`}
      className={cx("group block rounded-2xl border border-line bg-surface-2/60 transition-colors hover:border-line-strong hover:bg-surface-2", compact ? "p-3.5" : "p-4")}
    >
      <div className="flex items-start justify-between gap-3">
        <div className="min-w-0">
          <p className="truncate font-medium">{skill.name}</p>
          <p className="mt-0.5 text-xs text-ink-faint">
            {skill.code} · {skill.domain_name}
          </p>
        </div>
        <StatusBadge status={skill.status} className="shrink-0" />
      </div>
      {!compact && (
        <div className="mt-3 grid gap-2 text-sm sm:grid-cols-2">
          <div>
            <p className="text-[11px] font-semibold uppercase tracking-wider text-ink-faint">Your answers</p>
            <p className="mt-0.5">
              {skill.attempts ? (
                <>
                  <span className="font-semibold">{skill.correct}</span>
                  <span className="text-ink-muted"> of {skill.attempts} correct · {pct(skill.observed_accuracy)}</span>
                </>
              ) : (
                <span className="text-ink-muted">Not attempted yet</span>
              )}
            </p>
          </div>
          <div>
            <p className="text-[11px] font-semibold uppercase tracking-wider text-ink-faint">Model estimate</p>
            <ModelEstimate p={skill.predicted_p} className="mt-1" />
          </div>
        </div>
      )}
      <div className="mt-3 flex items-center justify-between">
        <EvidenceMeter evidence={skill.evidence} />
        <ChevronRight className="size-4 text-ink-faint transition-transform group-hover:translate-x-0.5" />
      </div>
      {explain && <p className="mt-2 text-sm text-ink-muted">{explain}</p>}
    </Link>
  );
}
