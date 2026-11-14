/** Subject picker in the top bar. Hidden unless at least two subjects are active. */
import { useState } from "react";
import { useNavigate } from "react-router";
import { tutor } from "../api/tutor";
import type { SubjectInfo } from "../api/tutor";
import { ApiError } from "../api/client";
import { cx } from "./ui";

export function SubjectSwitcher({ subjects, current, onSwitched, className }: { subjects: SubjectInfo[] | undefined; current: string | null | undefined; onSwitched: () => Promise<void>; className?: string }) {
  const navigate = useNavigate();
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string>();
  if (!subjects || subjects.length < 2) return null;
  const value = current ?? subjects.find((s) => s.current)?.code ?? subjects[0]!.code;

  async function change(code: string) {
    if (code === value) return;
    setBusy(true);
    setError(undefined);
    try {
      await tutor.setSubject(code);
      await onSwitched();
      navigate("/home");
    } catch (e) {
      setError(e instanceof ApiError ? e.message : "Couldn't switch subject.");
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className={cx("relative", className)}>
      <label htmlFor="subject-switcher" className="sr-only">
        Subject
      </label>
      <select
        id="subject-switcher"
        value={value}
        disabled={busy}
        onChange={(e) => void change(e.target.value)}
        className="h-11 max-w-[11rem] rounded-[var(--radius-control)] border border-line-strong bg-surface-2 px-3 text-sm font-medium text-ink disabled:cursor-not-allowed disabled:opacity-55 sm:h-10"
      >
        {subjects.map((s) => (
          <option key={s.code} value={s.code}>
            {s.name}
          </option>
        ))}
      </select>
      {error && (
        <p role="alert" className="absolute right-0 top-full mt-1 w-56 rounded-lg border border-line-strong bg-surface-2 p-2 text-xs text-developing">
          {error}
        </p>
      )}
    </div>
  );
}
