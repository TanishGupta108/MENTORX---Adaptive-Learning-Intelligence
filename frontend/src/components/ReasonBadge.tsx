import type { PathReason } from "../api/types";
import { cx } from "./ui";

const STYLES: Record<PathReason, { label: string; cls: string }> = {
  revision: { label: "Revise", cls: "bg-warning/15 text-warning" },
  prerequisite: { label: "Prerequisite", cls: "bg-danger/10 text-danger" },
  weak: { label: "Strengthen", cls: "bg-brand/10 text-brand" },
  new: { label: "New", cls: "bg-success/15 text-success" },
};

export function ReasonBadge({ reason }: { reason: PathReason }) {
  const s = STYLES[reason];
  return (
    <span className={cx("ml-1 inline-block rounded-full px-2 py-0.5 align-middle text-xs font-medium", s.cls)}>
      {s.label}
    </span>
  );
}

export const DIFFICULTY = { 1: "Easier", 2: "Medium", 3: "Harder" } as const;
