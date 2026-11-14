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
    <article className={cx("rounded-[var(--radius-card)] border", done ? "border-strength/40" : "border-line")}>
      <div className="flex flex-wrap items-start gap-3 p-4">
        <k.icon className="mt-0.5 size-5 shrink-0 text-ink-muted" aria-hidden />
        <div className="min-w-0 flex-1 basis-[14rem]">
          <h3 className="font-medium">{resource.title}</h3>
          <p className="text-sm text-ink-muted">
            {k.label}, {resource.minutes} min
            {showSkill && resource.skill_code && `, ${resource.skill_code}`}
          </p>
          {showSkill && resource.skill_name && <p className="text-xs text-ink-muted">{resource.skill_name}</p>}
          {resource.description && <p className="mt-1 text-sm text-ink-muted">{resource.description}</p>}
          <p className="mt-1 text-xs text-ink-faint">Source: {resource.source_label}</p>
        </div>
        <button
          type="button"
          onClick={toggle}
          disabled={busy}
          className={cx("flex min-h-11 shrink-0 items-center gap-1.5 rounded-lg px-2.5 text-sm font-medium sm:min-h-9", done ? "text-strength hover:bg-surface-2" : "text-ink-muted hover:bg-surface-2 hover:text-ink")}
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
