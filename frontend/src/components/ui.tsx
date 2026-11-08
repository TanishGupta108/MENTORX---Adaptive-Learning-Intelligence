import type { ComponentPropsWithRef, ReactNode } from "react";
import { Link } from "react-router";

export function cx(...parts: (string | false | null | undefined)[]) {
  return parts.filter(Boolean).join(" ");
}

type Variant = "primary" | "secondary" | "ghost" | "danger";

const variants: Record<Variant, string> = {
  primary: "bg-brand text-brand-ink hover:opacity-90",
  secondary: "border border-line bg-surface text-ink hover:bg-canvas",
  ghost: "text-ink-muted hover:text-ink hover:bg-canvas",
  danger: "bg-danger text-white hover:opacity-90",
};

const base =
  "inline-flex min-h-11 items-center justify-center gap-2 rounded-lg px-4 text-sm font-medium transition " +
  "focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-brand disabled:cursor-not-allowed disabled:opacity-50";

export function Button({
  variant = "primary",
  className,
  ...props
}: ComponentPropsWithRef<"button"> & { variant?: Variant }) {
  return <button type="button" className={cx(base, variants[variant], className)} {...props} />;
}

export function ButtonLink({
  to,
  variant = "primary",
  className,
  children,
}: {
  to: string;
  variant?: Variant;
  className?: string;
  children: ReactNode;
}) {
  return (
    <Link to={to} className={cx(base, variants[variant], className)}>
      {children}
    </Link>
  );
}

export function Card({
  title,
  action,
  children,
  className,
}: {
  title?: ReactNode;
  action?: ReactNode;
  children: ReactNode;
  className?: string;
}) {
  return (
    <section className={cx("rounded-xl border border-line bg-surface p-4 sm:p-5", className)}>
      {(title || action) && (
        <div className="mb-3 flex items-center justify-between gap-3">
          {title && <h2 className="text-base font-semibold">{title}</h2>}
          {action}
        </div>
      )}
      {children}
    </section>
  );
}

export function Spinner({ label = "Loading…" }: { label?: string }) {
  return (
    <div role="status" className="flex items-center gap-3 py-8 text-ink-muted">
      <span className="size-5 animate-spin rounded-full border-2 border-line border-t-brand" />
      <span>{label}</span>
    </div>
  );
}

export function ErrorState({ error, onRetry }: { error: Error; onRetry?: () => void }) {
  return (
    <div role="alert" className="rounded-xl border border-danger/40 bg-danger/5 p-4">
      <p className="font-medium text-danger">Couldn't load this.</p>
      <p className="mt-1 text-sm text-ink-muted">{error.message}</p>
      {onRetry && (
        <Button variant="secondary" className="mt-3" onClick={onRetry}>
          Try again
        </Button>
      )}
    </div>
  );
}

/** FR-DASH-08: empty states explain what to do instead of showing placeholder numbers. */
export function EmptyState({ title, children }: { title: string; children?: ReactNode }) {
  return (
    <div className="rounded-lg border border-dashed border-line p-5 text-center">
      <p className="font-medium">{title}</p>
      {children && <div className="mt-1 text-sm text-ink-muted">{children}</div>}
    </div>
  );
}

export const pct = (p: number) => `${Math.round(p * 100)}%`;

/** Mastery colour bands (also used by the concept map). */
export function masteryTone(p: number | null | undefined) {
  if (p == null) return "unknown";
  if (p >= 0.8) return "mastered";
  if (p >= 0.6) return "ok";
  if (p >= 0.4) return "weak";
  return "low";
}

export const toneClass: Record<ReturnType<typeof masteryTone>, string> = {
  mastered: "bg-success",
  ok: "bg-brand",
  weak: "bg-warning",
  low: "bg-danger",
  unknown: "bg-line",
};

export function MasteryBar({ value, label }: { value: number | null; label?: string }) {
  return (
    <div className="flex items-center gap-3">
      <div
        className="h-2 flex-1 overflow-hidden rounded-full bg-canvas"
        role="meter"
        aria-label={label ?? "Mastery"}
        aria-valuemin={0}
        aria-valuemax={100}
        aria-valuenow={value == null ? undefined : Math.round(value * 100)}
        aria-valuetext={value == null ? "not assessed yet" : pct(value)}
      >
        {value != null && (
          <div
            className={cx("h-full rounded-full", toneClass[masteryTone(value)])}
            style={{ width: `${Math.max(2, value * 100)}%` }}
          />
        )}
      </div>
      <span className="w-12 text-right text-sm tabular-nums text-ink-muted">
        {value == null ? "—" : pct(value)}
      </span>
    </div>
  );
}

export function Stat({ label, value, hint }: { label: string; value: ReactNode; hint?: ReactNode }) {
  return (
    <div className="rounded-xl border border-line bg-surface p-4">
      <p className="text-sm text-ink-muted">{label}</p>
      <p className="mt-1 text-2xl font-semibold tabular-nums">{value}</p>
      {hint && <p className="mt-1 text-xs text-ink-muted">{hint}</p>}
    </div>
  );
}

export function PageHeader({ title, children }: { title: string; children?: ReactNode }) {
  return (
    <header className="mb-6">
      <h1 className="text-2xl font-semibold tracking-tight sm:text-3xl">{title}</h1>
      {children && <div className="mt-2 text-ink-muted">{children}</div>}
    </header>
  );
}

export function Field({
  label,
  hint,
  error,
  children,
}: {
  label: string;
  hint?: string;
  error?: string;
  children: ReactNode;
}) {
  return (
    <label className="block">
      <span className="text-sm font-medium">{label}</span>
      <div className="mt-1">{children}</div>
      {hint && !error && <span className="mt-1 block text-xs text-ink-muted">{hint}</span>}
      {error && <span className="mt-1 block text-xs text-danger">{error}</span>}
    </label>
  );
}

export const inputClass =
  "block min-h-11 w-full rounded-lg border border-line bg-surface px-3 text-base text-ink " +
  "focus:border-brand focus:outline-2 focus:outline-brand/30";
