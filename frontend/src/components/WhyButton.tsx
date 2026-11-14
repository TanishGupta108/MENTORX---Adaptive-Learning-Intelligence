/** A small "Why?" button that reveals one plain sentence (and optional extra content) inline. */
import { useId, useState } from "react";
import type { ReactNode } from "react";
import { HelpCircle } from "lucide-react";
import { cx } from "./ui";

export function WhyButton({ label = "Why?", children, className, align = "start" }: { label?: string; children: ReactNode; className?: string; align?: "start" | "end" }) {
  const [open, setOpen] = useState(false);
  const id = useId();
  return (
    <div className={cx("flex flex-col", align === "end" ? "items-end" : "items-start", className)}>
      <button
        type="button"
        onClick={() => setOpen((o) => !o)}
        aria-expanded={open}
        aria-controls={id}
        className="inline-flex min-h-11 items-center gap-1 rounded-lg px-1 text-sm text-ink-muted hover:text-ink sm:min-h-8"
      >
        <HelpCircle className="size-4" aria-hidden />
        {label}
      </button>
      {open && (
        <div id={id} className="mt-1 w-full rounded-xl bg-surface-2 px-3 py-2.5 text-left text-sm text-ink-muted animate-rise">
          {children}
        </div>
      )}
    </div>
  );
}
