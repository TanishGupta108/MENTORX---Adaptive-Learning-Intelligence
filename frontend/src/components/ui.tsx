/** MENTORX design-system primitives. Every screen is built from these. */
import type { ButtonHTMLAttributes, ReactNode } from "react";
import { Link } from "react-router";
import { AlertTriangle, Loader2 } from "lucide-react";
import type { Evidence, Mode, Status } from "../api/tutor";

export function cx(...parts: (string | false | null | undefined)[]) {
  return parts.filter(Boolean).join(" ");
}

export function pct(x: number | null | undefined, digits = 0) {
  return x === null || x === undefined ? "—" : `${(100 * x).toFixed(digits)}%`;
}

// ---------------------------------------------------------------- buttons

type Variant = "primary" | "secondary" | "ghost" | "danger" | "soft";
const variants: Record<Variant, string> = {
  primary: "bg-brand text-brand-ink hover:bg-[#a3a4ff] shadow-[0_6px_20px_-8px_#8b8cff]",
  secondary: "border border-line-strong bg-surface-2 text-ink hover:bg-surface-3",
  ghost: "text-ink-muted hover:bg-surface-2 hover:text-ink",
  danger: "bg-danger/15 text-danger hover:bg-danger/25",
  soft: "bg-brand-soft text-brand hover:bg-brand/25",
};
const sizes = { sm: "h-9 px-3 text-sm", md: "h-11 px-4 text-sm", lg: "h-12 px-6 text-base" };

type BtnProps = ButtonHTMLAttributes<HTMLButtonElement> & {
  variant?: Variant;
  size?: keyof typeof sizes;
  loading?: boolean;
  icon?: ReactNode;
  to?: string;
};

export function Button({ variant = "primary", size = "md", loading, icon, to, className, children, disabled, ...rest }: BtnProps) {
  const cls = cx(
    "inline-flex items-center justify-center gap-2 rounded-xl font-medium transition-colors disabled:cursor-not-allowed disabled:opacity-50",
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
  return <As className={cx("rounded-[var(--radius-card)] border border-line bg-surface p-5 animate-rise", className)}>{children}</As>;
}

export function CardTitle({ icon, title, action, subtitle }: { icon?: ReactNode; title: string; action?: ReactNode; subtitle?: string }) {
  return (
    <div className="mb-4 flex items-start justify-between gap-3">
      <div className="flex items-start gap-2.5">
        {icon && <span className="mt-0.5 text-brand">{icon}</span>}
        <div>
          <h2 className="text-[15px] font-semibold tracking-tight">{title}</h2>
          {subtitle && <p className="mt-0.5 text-sm text-ink-muted">{subtitle}</p>}
        </div>
      </div>
      {action}
    </div>
  );
}

export function PageHeader({ eyebrow, title, subtitle, actions }: { eyebrow?: string; title: string; subtitle?: ReactNode; actions?: ReactNode }) {
  return (
    <header className="mb-6 flex flex-col gap-4 sm:flex-row sm:items-end sm:justify-between">
      <div>
        {eyebrow && <p className="mb-1 text-xs font-semibold uppercase tracking-[0.14em] text-brand">{eyebrow}</p>}
        <h1 className="text-2xl font-semibold tracking-tight sm:text-[28px]">{title}</h1>
        {subtitle && <div className="mt-1.5 max-w-2xl text-ink-muted">{subtitle}</div>}
      </div>
      {actions && <div className="flex flex-wrap gap-2">{actions}</div>}
    </header>
  );
}

// ---------------------------------------------------------------- status language

export const STATUS_META: Record<Status, { label: string; dot: string; text: string; bg: string; hex: string }> = {
  likely_strength: { label: "Likely Strength", dot: "bg-strength", text: "text-strength", bg: "bg-strength/12", hex: "#34d399" },
  developing: { label: "Developing", dot: "bg-developing", text: "text-developing", bg: "bg-developing/12", hex: "#fbbf24" },
  potential_weakness: { label: "Potential Weakness", dot: "bg-weakness", text: "text-weakness", bg: "bg-weakness/12", hex: "#fb7185" },
  needs_assessment: { label: "Needs Assessment", dot: "bg-unassessed", text: "text-unassessed", bg: "bg-unassessed/12", hex: "#94a3b8" },
};

export function StatusBadge({ status, className }: { status: Status; className?: string }) {
  const m = STATUS_META[status];
  return (
    <span className={cx("inline-flex items-center gap-1.5 rounded-full px-2.5 py-1 text-xs font-medium", m.bg, m.text, className)}>
      <span className={cx("size-1.5 rounded-full", m.dot)} />
      {m.label}
    </span>
  );
}

const MODE_META: Record<Mode, { label: string; cls: string }> = {
  foundation: { label: "Foundation", cls: "bg-[#5aa9ff1f] text-accent" },
  guided: { label: "Guided", cls: "bg-brand-soft text-brand" },
  independent: { label: "Independent", cls: "bg-[#34d3991f] text-strength" },
  advanced: { label: "Advanced", cls: "bg-[#f472b61f] text-[#f472b6]" },
};

export function ModeBadge({ mode }: { mode: Mode }) {
  return <span className={cx("rounded-full px-2.5 py-1 text-xs font-medium", MODE_META[mode].cls)}>{MODE_META[mode].label} mode</span>;
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
      {attempts !== undefined && attempts > 0 && <span className="text-ink-faint">· {attempts} answers</span>}
    </span>
  );
}

/** Model output is always shown with this label so it is never mistaken for mastery. */
export function ModelEstimate({ p, className }: { p: number | null; className?: string }) {
  if (p === null || p === undefined) {
    return <span className={cx("text-xs text-ink-faint", className)}>No model estimate yet</span>;
  }
  return (
    <span className={cx("inline-flex items-center gap-1.5 text-xs text-ink-muted", className)} title="DKT-Q model: predicted chance of getting a typical question in this skill right on the first try. A prediction, not verified mastery.">
      <span className="rounded bg-surface-3 px-1.5 py-0.5 font-mono text-[11px] text-accent">model</span>
      {pct(p)} predicted success
    </span>
  );
}

// ---------------------------------------------------------------- progress

export function ProgressBar({ value, max = 1, className, tone = "brand" }: { value: number; max?: number; className?: string; tone?: "brand" | "strength" | "developing" | "weakness" }) {
  const w = Math.max(0, Math.min(100, (100 * value) / (max || 1)));
  const color = { brand: "bg-brand", strength: "bg-strength", developing: "bg-developing", weakness: "bg-weakness" }[tone];
  return (
    <div className={cx("h-2 w-full overflow-hidden rounded-full bg-surface-3", className)} role="progressbar" aria-valuenow={Math.round(w)} aria-valuemin={0} aria-valuemax={100}>
      <div className={cx("h-full rounded-full transition-[width] duration-500", color)} style={{ width: `${w}%` }} />
    </div>
  );
}

export function Ring({ value, size = 64, stroke = 6, label, color = "#8b8cff" }: { value: number; size?: number; stroke?: number; label?: ReactNode; color?: string }) {
  const r = (size - stroke) / 2;
  const c = 2 * Math.PI * r;
  const v = Math.max(0, Math.min(1, value));
  return (
    <div className="relative inline-grid place-items-center" style={{ width: size, height: size }}>
      <svg width={size} height={size} className="-rotate-90" aria-hidden>
        <circle cx={size / 2} cy={size / 2} r={r} stroke="#253150" strokeWidth={stroke} fill="none" />
        <circle cx={size / 2} cy={size / 2} r={r} stroke={color} strokeWidth={stroke} fill="none" strokeLinecap="round" strokeDasharray={c} strokeDashoffset={c * (1 - v)} className="transition-[stroke-dashoffset] duration-700" />
      </svg>
      <span className="absolute text-sm font-semibold">{label}</span>
    </div>
  );
}

export function Stat({ label, value, hint, icon }: { label: string; value: ReactNode; hint?: ReactNode; icon?: ReactNode }) {
  return (
    <div className="rounded-2xl border border-line bg-surface p-4 animate-rise">
      <div className="flex items-center justify-between text-ink-muted">
        <span className="text-xs font-medium uppercase tracking-wider">{label}</span>
        {icon}
      </div>
      <div className="mt-2 text-2xl font-semibold tracking-tight">{value}</div>
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
          <div key={i} className="h-28 animate-pulse rounded-2xl bg-surface" />
        ))}
      </div>
    </div>
  );
}

export function ErrorState({ error, onRetry }: { error: Error; onRetry?: () => void }) {
  return (
    <div className="flex flex-col items-start gap-3 rounded-2xl border border-danger/30 bg-danger/8 p-5" role="alert">
      <div className="flex items-center gap-2 font-medium text-danger">
        <AlertTriangle className="size-4" /> Couldn't load this
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
    <div className="flex flex-col items-center gap-3 rounded-2xl border border-dashed border-line-strong px-6 py-10 text-center">
      {icon && <div className="text-brand">{icon}</div>}
      <h3 className="font-semibold">{title}</h3>
      {children && <div className="max-w-md text-sm text-ink-muted">{children}</div>}
      {action}
    </div>
  );
}

// ---------------------------------------------------------------- forms

export const inputClass =
  "h-11 w-full rounded-xl border border-line-strong bg-surface-2 px-3.5 text-ink placeholder:text-ink-faint focus:border-brand focus:outline-none";

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
      <span className="grid size-8 place-items-center rounded-xl bg-gradient-to-br from-brand to-accent text-sm font-bold text-brand-ink shadow-[0_4px_16px_-4px_#8b8cff]">
        M
      </span>
      <span>
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
