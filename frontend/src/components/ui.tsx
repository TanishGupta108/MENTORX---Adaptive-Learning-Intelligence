/** MENTORX design-system primitives (design.md). Every screen is built from these.
 * Calm and still: one periwinkle signal, hairlines before cards, motion only for state. */
import type { ButtonHTMLAttributes, ReactNode } from "react";
import { Link } from "react-router";
import { AlertTriangle, Loader2 } from "lucide-react";
import type { Evidence, Mode, Status } from "../api/tutor";

/** A design token's live colour (charts: SVG attributes can't read CSS variables). */
export function token(name: string, fallback = "currentColor") {
  if (typeof window === "undefined") return fallback;
  return getComputedStyle(document.documentElement).getPropertyValue(`--color-${name}`).trim() || fallback;
}

export function cx(...parts: (string | false | null | undefined)[]) {
  return parts.filter(Boolean).join(" ");
}

export function pct(x: number | null | undefined, digits = 0) {
  return x === null || x === undefined ? "—" : `${(100 * x).toFixed(digits)}%`;
}

// ---------------------------------------------------------------- buttons

type Variant = "primary" | "secondary" | "ghost" | "danger" | "soft";
const variants: Record<Variant, string> = {
  primary: "bg-brand text-brand-ink hover:bg-brand-hover active:bg-brand-press",
  secondary: "border border-line-strong text-ink hover:bg-surface-2 active:bg-surface-3",
  ghost: "text-ink-muted hover:bg-surface-2 hover:text-ink active:bg-surface-3",
  danger: "border border-danger/50 text-danger hover:bg-danger/10 active:bg-danger/15",
  soft: "bg-brand-soft text-ink hover:bg-brand/25 active:bg-brand/30",
};
// app controls: 40px on a fine pointer, 44px on touch; lg is the focused-flow action
const sizes = { sm: "h-11 px-3 text-sm sm:h-9", md: "h-11 px-4 text-sm sm:h-10", lg: "h-12 px-6 text-base" };

type BtnProps = ButtonHTMLAttributes<HTMLButtonElement> & {
  variant?: Variant;
  size?: keyof typeof sizes;
  loading?: boolean;
  icon?: ReactNode;
  to?: string;
};

export function Button({ variant = "primary", size = "md", loading, icon, to, className, children, disabled, ...rest }: BtnProps) {
  const cls = cx(
    "inline-flex shrink-0 items-center justify-center gap-2 whitespace-nowrap rounded-[var(--radius-control)] font-medium transition-colors duration-[120ms] disabled:cursor-not-allowed disabled:opacity-55 aria-disabled:cursor-not-allowed aria-disabled:opacity-55",
    variants[variant],
    sizes[size],
    className,
  );
  const inner = (
    <>
      {loading ? <Loader2 className="size-4 animate-spin" aria-hidden /> : icon}
      {children}
    </>
  );
  if (to) {
    return (
      <Link to={to} className={cls}>
        {inner}
      </Link>
    );
  }
  return (
    <button type="button" className={cls} disabled={disabled || loading} {...rest}>
      {inner}
    </button>
  );
}

// ---------------------------------------------------------------- surfaces

export function Card({ className, children, as: As = "section" }: { className?: string; children: ReactNode; as?: "section" | "div" | "article" }) {
  return <As className={cx("rounded-[var(--radius-card)] border border-line bg-surface p-5 sm:p-6", className)}>{children}</As>;
}

export function CardTitle({ icon, title, action, subtitle }: { icon?: ReactNode; title: string; action?: ReactNode; subtitle?: string }) {
  return (
    <div className="mb-4 flex items-start justify-between gap-3">
      <div className="flex items-start gap-2.5">
        {icon && <span className="mt-0.5 text-brand">{icon}</span>}
        <div>
          <h2 className="text-[19px] font-semibold tracking-tight">{title}</h2>
          {subtitle && <p className="mt-0.5 text-sm text-ink-muted">{subtitle}</p>}
        </div>
      </div>
      {action}
    </div>
  );
}

export function PageHeader({ title, subtitle, actions }: { title: string; subtitle?: ReactNode; actions?: ReactNode }) {
  return (
    <header className="mb-8 flex flex-col gap-4 sm:flex-row sm:items-end sm:justify-between">
      <div className="min-w-0">
        <h1 className="text-[28px] font-semibold leading-tight tracking-tight sm:text-[32px]">{title}</h1>
        {subtitle && <div className="mt-2 max-w-2xl text-ink-muted">{subtitle}</div>}
      </div>
      {actions && <div className="flex flex-wrap gap-2">{actions}</div>}
    </header>
  );
}

// ---------------------------------------------------------------- status language

export const STATUS_META: Record<Status, { label: string; dot: string; text: string; bg: string; hex: string }> = {
  likely_strength: { label: "Strong", dot: "bg-strength", text: "text-strength", bg: "bg-strength/12", hex: "var(--color-strength)" },
  developing: { label: "Getting there", dot: "bg-developing", text: "text-developing", bg: "bg-developing/12", hex: "var(--color-developing)" },
  potential_weakness: { label: "Needs practice", dot: "bg-weakness", text: "text-weakness", bg: "bg-weakness/12", hex: "var(--color-weakness)" },
  needs_assessment: { label: "Not tried yet", dot: "bg-unassessed", text: "text-unassessed", bg: "bg-unassessed/12", hex: "var(--color-unassessed)" },
};

export function StatusBadge({ status, className }: { status: Status; className?: string }) {
  const m = STATUS_META[status];
  return (
    <span className={cx("inline-flex shrink-0 items-center whitespace-nowrap rounded-full px-2.5 py-1 text-xs font-medium", m.bg, m.text, className)}>
      {m.label}
    </span>
  );
}

const MODE_META: Record<Mode, { label: string; cls: string }> = {
  foundation: { label: "Step by step", cls: "border border-line-strong text-ink-muted" },
  guided: { label: "Guided", cls: "border border-line-strong text-ink-muted" },
  independent: { label: "On my own", cls: "border border-line-strong text-ink-muted" },
  advanced: { label: "Challenge", cls: "border border-line-strong text-ink-muted" },
};

export const MODE_LABEL: Record<Mode, string> = {
  foundation: MODE_META.foundation.label,
  guided: MODE_META.guided.label,
  independent: MODE_META.independent.label,
  advanced: MODE_META.advanced.label,
};

export function ModeBadge({ mode }: { mode: Mode }) {
  return <span className={cx("rounded-full px-2.5 py-1 text-xs font-medium", MODE_META[mode].cls)}>{MODE_META[mode].label}</span>;
}

const EVIDENCE: Record<Evidence, { n: number; label: string }> = {
  none: { n: 0, label: "No evidence yet" },
  limited: { n: 1, label: "Limited evidence" },
  moderate: { n: 2, label: "Moderate evidence" },
  strong: { n: 3, label: "Strong evidence" },
};

export function EvidenceMeter({ evidence, attempts }: { evidence: Evidence; attempts?: number }) {
  const e = EVIDENCE[evidence];
  return (
    <span className="inline-flex items-center gap-2 text-xs text-ink-muted" title={`${e.label}${attempts !== undefined ? ` (${attempts} answers)` : ""}`}>
      <span className="flex gap-0.5" aria-hidden>
        {[1, 2, 3].map((i) => (
          <span key={i} className={cx("h-2.5 w-1.5 rounded-sm", i <= e.n ? "bg-brand" : "bg-line-strong")} />
        ))}
      </span>
      {e.label}
      {attempts !== undefined && attempts > 0 && <span className="text-ink-faint">({attempts} answers)</span>}
    </span>
  );
}

/** Model output is always shown with this label so it is never mistaken for mastery. */
export function ModelEstimate({ p, className }: { p: number | null; className?: string }) {
  if (p === null || p === undefined) {
    return <span className={cx("text-xs text-ink-faint", className)}>No prediction yet</span>;
  }
  return (
    <span className={cx("inline-flex items-center gap-1.5 text-xs text-ink-muted", className)} title="A model's predicted chance of getting a typical question in this skill right first time. A prediction, not a result.">
      <span className="rounded border border-line-strong px-1.5 py-0.5 text-xs font-medium text-ink">Prediction</span>
      {pct(p)} chance of a right answer
    </span>
  );
}

// ---------------------------------------------------------------- progress

export function ProgressBar({ value, max = 1, className, tone = "brand" }: { value: number; max?: number; className?: string; tone?: "brand" | "strength" | "developing" | "weakness" }) {
  const w = Math.max(0, Math.min(100, (100 * value) / (max || 1)));
  const color = { brand: "bg-brand", strength: "bg-strength", developing: "bg-developing", weakness: "bg-weakness" }[tone];
  return (
    <div className={cx("h-2 w-full overflow-hidden rounded-full bg-surface-3", className)} role="progressbar" aria-valuenow={Math.round(w)} aria-valuemin={0} aria-valuemax={100}>
      <div className={cx("h-full w-full origin-left rounded-full transition-transform duration-500", color)} style={{ transform: `scaleX(${w / 100})` }} />
    </div>
  );
}

export function Ring({ value, size = 64, stroke = 6, label, color = "var(--color-brand)" }: { value: number; size?: number; stroke?: number; label?: ReactNode; color?: string }) {
  const r = (size - stroke) / 2;
  const c = 2 * Math.PI * r;
  const v = Math.max(0, Math.min(1, value));
  return (
    <div className="relative inline-grid place-items-center" style={{ width: size, height: size }}>
      <svg width={size} height={size} className="-rotate-90" aria-hidden>
        <circle cx={size / 2} cy={size / 2} r={r} stroke="var(--color-line)" strokeWidth={stroke} fill="none" />
        <circle cx={size / 2} cy={size / 2} r={r} stroke={color} strokeWidth={stroke} fill="none" strokeLinecap="round" strokeDasharray={c} strokeDashoffset={c * (1 - v)} className="transition-[stroke-dashoffset] duration-700" />
      </svg>
      <span className="absolute text-sm font-semibold">{label}</span>
    </div>
  );
}

export function Stat({ label, value, hint, icon }: { label: string; value: ReactNode; hint?: ReactNode; icon?: ReactNode }) {
  return (
    <div className="min-w-0 border-t border-line pt-4">
      <div className="flex items-center justify-between gap-2 text-ink-muted">
        <span className="text-sm">{label}</span>
        {icon}
      </div>
      <div className="mt-1 text-[28px] font-semibold tabular-nums tracking-tight">{value}</div>
      {hint && <div className="mt-1 text-xs text-ink-faint">{hint}</div>}
    </div>
  );
}

// ---------------------------------------------------------------- states

export function Spinner({ label = "Loading…" }: { label?: string }) {
  return (
    <div className="flex items-center gap-3 py-10 text-ink-muted" role="status">
      <Loader2 className="size-5 animate-spin text-brand" aria-hidden />
      {label}
    </div>
  );
}

export function PageLoader({ label }: { label?: string }) {
  return (
    <div className="space-y-4" aria-busy>
      <Spinner label={label} />
      <div className="grid gap-4 md:grid-cols-3">
        {[0, 1, 2].map((i) => (
          <div key={i} className="h-28 animate-pulse rounded-[var(--radius-card)] bg-surface" />
        ))}
      </div>
    </div>
  );
}

export function ErrorState({ error, onRetry }: { error: Error; onRetry?: () => void }) {
  return (
    <div className="flex flex-col items-start gap-3 rounded-[var(--radius-card)] border border-danger/40 p-5" role="alert">
      <div className="flex items-center gap-2 font-medium text-danger">
        <AlertTriangle className="size-4" /> Couldn’t load this
      </div>
      <p className="text-sm text-ink-muted">{error.message}</p>
      {onRetry && (
        <Button variant="secondary" size="sm" onClick={onRetry}>
          Try again
        </Button>
      )}
    </div>
  );
}

export function EmptyState({ icon, title, children, action }: { icon?: ReactNode; title: string; children?: ReactNode; action?: ReactNode }) {
  return (
    <div className="flex flex-col items-center gap-3 rounded-[var(--radius-card)] border border-dashed border-line-strong px-6 py-10 text-center">
      {icon && <div className="text-brand">{icon}</div>}
      <h3 className="font-semibold">{title}</h3>
      {children && <div className="max-w-md text-sm text-ink-muted">{children}</div>}
      {action}
    </div>
  );
}

// ---------------------------------------------------------------- forms

export const inputClass =
  "h-11 w-full rounded-[var(--radius-control)] border border-line-strong bg-surface-2 px-3.5 text-base text-ink placeholder:text-ink-faint disabled:cursor-not-allowed disabled:opacity-55";

export function Field({ label, error, children, hint }: { label: string; error?: string; children: ReactNode; hint?: string }) {
  return (
    <label className="block space-y-1.5">
      <span className="text-sm font-medium">{label}</span>
      {children}
      {hint && !error && <span className="block text-xs text-ink-faint">{hint}</span>}
      {error && <span className="block text-xs text-danger">{error}</span>}
    </label>
  );
}

export function Logo({ className }: { className?: string }) {
  return (
    <span className={cx("inline-flex items-center gap-2 font-semibold tracking-tight", className)}>
      <span className="grid size-8 place-items-center rounded-[10px] bg-brand font-display text-sm font-bold text-brand-ink" aria-hidden>
        M
      </span>
      <span className="font-display">
        MENTOR<span className="text-brand">X</span>
      </span>
    </span>
  );
}

export function timeAgo(iso: string) {
  const s = (Date.now() - new Date(iso).getTime()) / 1000;
  if (s < 60) return "just now";
  if (s < 3600) return `${Math.floor(s / 60)} min ago`;
  if (s < 86400) return `${Math.floor(s / 3600)} h ago`;
  return `${Math.floor(s / 86400)} d ago`;
}
