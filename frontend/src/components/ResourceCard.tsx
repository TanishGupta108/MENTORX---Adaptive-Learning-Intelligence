import { useState } from "react";
import { BookOpenText, CheckCircle2, ChevronDown, Circle, ExternalLink, FileText, Lightbulb, PenLine, PlayCircle } from "lucide-react";
import type { Resource } from "../api/tutor";
import { tutor } from "../api/tutor";
import { Markdown } from "./Markdown";
import { cx } from "./ui";

const KIND: Record<Resource["kind"], { label: string; icon: typeof FileText }> = {
  notes: { label: "Concept notes", icon: BookOpenText },
  worked_example: { label: "Worked example", icon: PenLine },
  standard: { label: "Official standard", icon: FileText },
  video: { label: "Video", icon: PlayCircle },
  article: { label: "Article", icon: FileText },
  practice_tip: { label: "Practice tip", icon: Lightbulb },
};

/** A resource with inline content (notes/examples) or an external link, and a completion toggle.
 * Completing a resource never changes a skill estimate. Only answers do. */
export function ResourceCard({ resource, defaultOpen = false, showSkill = false, onChange }: { resource: Resource; defaultOpen?: boolean; showSkill?: boolean; onChange?: (r: Resource) => void }) {
  const [open, setOpen] = useState(defaultOpen);
  const [done, setDone] = useState(resource.completed);
  const [busy, setBusy] = useState(false);
  const k = KIND[resource.kind];

  async function toggle() {
    setBusy(true);
    try {
      const res = await tutor.completeResource(resource.id, !done);
      setDone(res.completed);
      onChange?.({ ...resource, completed: res.completed });
    } finally {
      setBusy(false);
    }
  }

  return (
    <article className={cx("rounded-2xl border bg-surface-2/50", done ? "border-strength/30" : "border-line")}>
      <div className="flex items-start gap-3 p-4">
        <span className="grid size-9 shrink-0 place-items-center rounded-xl bg-surface-3 text-brand">
          <k.icon className="size-4" />
        </span>
        <div className="min-w-0 flex-1">
          <p className="text-[11px] font-semibold uppercase tracking-wider text-ink-faint">
            {k.label} · {resource.minutes} min
            {showSkill && resource.skill_code && <span className="normal-case tracking-normal"> · {resource.skill_code}</span>}
          </p>
          <h3 className="mt-0.5 font-medium">{resource.title}</h3>
          {showSkill && resource.skill_name && <p className="text-xs text-ink-muted">{resource.skill_name}</p>}
          {resource.description && <p className="mt-1 text-sm text-ink-muted">{resource.description}</p>}
          <p className="mt-1 text-xs text-ink-faint">Source: {resource.source_label}</p>
        </div>
        <button
          type="button"
          onClick={toggle}
          disabled={busy}
          className={cx("flex shrink-0 items-center gap-1.5 rounded-lg px-2.5 py-1.5 text-xs font-medium", done ? "text-strength" : "text-ink-muted hover:bg-surface-3")}
          aria-pressed={done}
        >
          {done ? <CheckCircle2 className="size-4" /> : <Circle className="size-4" />}
          {done ? "Completed" : "Mark complete"}
        </button>
      </div>
      {resource.content_md && (
        <>
          <button type="button" onClick={() => setOpen((o) => !o)} className="flex w-full items-center justify-between border-t border-line px-4 py-2.5 text-sm text-brand hover:bg-surface-2" aria-expanded={open}>
            {open ? "Hide" : "Read"} {k.label.toLowerCase()}
            <ChevronDown className={cx("size-4 transition-transform", open && "rotate-180")} />
          </button>
          {open && (
            <div className="border-t border-line px-5 py-4">
              <Markdown source={resource.content_md} />
            </div>
          )}
        </>
      )}
      {resource.url && (
        <a href={resource.url} target="_blank" rel="noopener noreferrer" className="flex items-center justify-between border-t border-line px-4 py-2.5 text-sm text-brand hover:bg-surface-2">
          Open {resource.kind === "standard" ? "the standard" : "resource"} on {new URL(resource.url).hostname}
          <ExternalLink className="size-4" />
        </a>
      )}
    </article>
  );
}
