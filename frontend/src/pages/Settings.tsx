import { useState } from "react";
import type { FormEvent } from "react";
import { useNavigate } from "react-router";
import { ApiError } from "../api/client";
import { me } from "../api/endpoints";
import { useAuth } from "../auth/AuthContext";
import { Button, Card, Field, inputClass, PageHeader } from "../components/ui";

function timezones(current: string) {
  try {
    const all = (Intl as unknown as { supportedValuesOf?: (k: string) => string[] }).supportedValuesOf?.(
      "timeZone",
    );
    if (all?.length) return all.includes(current) ? all : [current, ...all];
  } catch {
    // older browsers: fall through
  }
  return [current];
}

export function SettingsPage() {
  const { user, setUser, logout } = useAuth();
  const navigate = useNavigate();
  const [form, setForm] = useState(() => ({
    full_name: user?.full_name ?? "",
    daily_goal: user?.daily_goal ?? 10,
    timezone: user?.timezone ?? "Asia/Kolkata",
    consent_research: user?.consent_research ?? false,
  }));
  const [status, setStatus] = useState<{ ok: boolean; text: string }>();
  const [errors, setErrors] = useState<Record<string, string>>({});
  const [confirmEmail, setConfirmEmail] = useState("");
  const [deleteError, setDeleteError] = useState<string>();
  if (!user) return null;

  async function save(e: FormEvent) {
    e.preventDefault();
    setStatus(undefined);
    setErrors({});
    try {
      setUser(await me.update(form));
      setStatus({ ok: true, text: "Saved." });
    } catch (err) {
      if (err instanceof ApiError) setErrors(err.fields);
      setStatus({ ok: false, text: err instanceof ApiError ? err.message : "Couldn't save." });
    }
  }

  async function download() {
    const data = await me.export();
    const url = URL.createObjectURL(new Blob([JSON.stringify(data, null, 2)], { type: "application/json" }));
    const a = document.createElement("a");
    a.href = url;
    a.download = "mentorx-my-data.json";
    a.click();
    URL.revokeObjectURL(url);
  }

  async function remove() {
    setDeleteError(undefined);
    try {
      await me.delete(confirmEmail);
      await logout();
      navigate("/", { replace: true });
    } catch (err) {
      setDeleteError(err instanceof ApiError ? err.message : "Couldn't delete the account.");
    }
  }

  return (
    <>
      <PageHeader title="Settings" />
      <div className="grid max-w-2xl gap-6">
        <Card title="Profile">
          <form className="space-y-4" onSubmit={save}>
            <Field label="Name" error={errors.full_name}>
              <input
                className={inputClass}
                value={form.full_name}
                onChange={(e) => setForm({ ...form, full_name: e.target.value })}
              />
            </Field>
            <Field label="Email">
              <input className={inputClass} value={user.email} disabled />
            </Field>
            <Field
              label="Daily goal (questions)"
              hint="A day counts towards your streak when you answer this many questions."
              error={errors.daily_goal}
            >
              <input
                className={inputClass}
                type="number"
                min={1}
                max={100}
                value={form.daily_goal}
                onChange={(e) => setForm({ ...form, daily_goal: Number(e.target.value) })}
              />
            </Field>
            <Field label="Time zone" hint="Used to decide where your days start and end." error={errors.timezone}>
              <select
                className={inputClass}
                value={form.timezone}
                onChange={(e) => setForm({ ...form, timezone: e.target.value })}
              >
                {timezones(form.timezone).map((tz) => (
                  <option key={tz} value={tz}>
                    {tz}
                  </option>
                ))}
              </select>
            </Field>
            <label className="flex items-start gap-3 text-sm">
              <input
                type="checkbox"
                className="mt-0.5 size-5 shrink-0 accent-brand"
                checked={form.consent_research}
                onChange={(e) => setForm({ ...form, consent_research: e.target.checked })}
              />
              <span>
                Allow my pseudonymised answers to be used in the MENTORX research study. Optional;
                you can change this at any time.
              </span>
            </label>
            <div className="flex items-center gap-3">
              <Button type="submit">Save</Button>
              {status && (
                <p role="status" className={status.ok ? "text-sm text-success" : "text-sm text-danger"}>
                  {status.text}
                </p>
              )}
            </div>
          </form>
        </Card>

        <Card title="Your data">
          <p className="text-sm text-ink-muted">
            Download everything MENTORX stores about you: profile, answers, mastery and sessions.
          </p>
          <Button variant="secondary" className="mt-3" onClick={() => void download()}>
            Download my data
          </Button>
        </Card>

        <Card title="Delete account" className="border-danger/40">
          <p className="text-sm text-ink-muted">
            Permanently deletes your account and all your answers. This can't be undone. Type your
            email to confirm.
          </p>
          <input
            className={`${inputClass} mt-3`}
            aria-label="Confirm your email"
            placeholder={user.email}
            value={confirmEmail}
            onChange={(e) => setConfirmEmail(e.target.value)}
          />
          {deleteError && (
            <p role="alert" className="mt-2 text-sm text-danger">
              {deleteError}
            </p>
          )}
          <Button
            variant="danger"
            className="mt-3"
            disabled={confirmEmail.trim().toLowerCase() !== user.email.toLowerCase()}
            onClick={() => void remove()}
          >
            Delete my account
          </Button>
        </Card>
      </div>
    </>
  );
}
