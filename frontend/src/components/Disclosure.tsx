/**
 * A collapsed section that opens on click. Used for everything secondary: details, model numbers,
 * explanations. The toggle is a real button with aria-expanded/aria-controls.
 */
import { useId, useState } from "react";
import type { ReactNode } from "react";
import { ChevronDown } from "lucide-react";
import { cx } from "./ui";

type Props = {
  title: ReactNode;
  children: ReactNode;
  defaultOpen?: boolean;
  /** Controlled mode (optional). */
  open?: boolean;
  onToggle?: (open: boolean) => void;
  className?: string;
  /** "card": bordered block; "plain": just a text toggle. */
  variant?: "card" | "plain";
  icon?: ReactNode;
};

export function Disclosure({ title, children, defaultOpen = false, open: openProp, onToggle, className, variant = "card", icon }: Props) {
  const [inner, setInner] = useState(defaultOpen);
  const open = openProp ?? inner;
  const id = useId();
  const toggle = () => {
    setInner(!open);
    onToggle?.(!open);
  };
  if (variant === "plain") {
    return (
      <div className={className}>
        <button
          type="button"
          onClick={toggle}
          aria-expanded={open}
          aria-controls={id}
          className="inline-flex min-h-11 items-center gap-1.5 rounded-lg text-sm text-ink-muted hover:text-ink sm:min-h-8"
        >
          {icon}
          {title}
          <ChevronDown className={cx("size-4 transition-transform", open && "rotate-180")} aria-hidden />
        </button>
        {open && (
          <div id={id} className="mt-2 animate-rise">
            {children}
          </div>
        )}
      </div>
    );
  }
  return (
    <section className={cx("rounded-[var(--radius-card)] border border-line bg-surface", className)}>
      <button
        type="button"
        onClick={toggle}
        aria-expanded={open}
        aria-controls={id}
        className="flex min-h-12 w-full items-center justify-between gap-3 rounded-[var(--radius-card)] px-5 py-3 text-left font-medium hover:bg-surface-2/60"
      >
        <span className="flex items-center gap-2">
          {icon}
          {title}
        </span>
        <ChevronDown className={cx("size-4 shrink-0 text-ink-muted transition-transform", open && "rotate-180")} aria-hidden />
      </button>
      {open && (
        <div id={id} className="border-t border-line px-5 py-4 animate-rise">
          {children}
        </div>
      )}
    </section>
  );
}
