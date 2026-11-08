import { useState } from "react";
import type { FormEvent, ReactNode } from "react";
import { Link, useNavigate, useSearchParams } from "react-router";
import { ApiError } from "../api/client";
import { useAuth } from "../auth/AuthContext";
import { Button, Field, inputClass } from "../components/ui";

function AuthShell({ title, children, footer }: { title: string; children: ReactNode; footer: ReactNode }) {
  return (
    <main className="mx-auto flex min-h-screen max-w-sm flex-col justify-center px-4 py-10">
      <Link to="/" className="mb-8 text-lg font-semibold tracking-tight">
        MENTOR<span className="text-brand">X</span>
      </Link>
      <h1 className="text-2xl font-semibold">{title}</h1>
      <div className="mt-6">{children}</div>
      <p className="mt-6 text-sm text-ink-muted">{footer}</p>
    </main>
  );
}

/** Only allow redirects to paths inside the app (no open redirect). */
function safeNext(next: string | null) {
  return next && next.startsWith("/") && !next.startsWith("//") ? next : "/dashboard";
}

export function LoginPage() {
  const { login } = useAuth();
  const navigate = useNavigate();
  const [params] = useSearchParams();
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState<string>();
  const [busy, setBusy] = useState(false);

  async function submit(e: FormEvent) {
    e.preventDefault();
    setBusy(true);
    setError(undefined);
    try {
      await login(email, password);
      navigate(safeNext(params.get("next")), { replace: true });
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Couldn't reach the server.");
    } finally {
      setBusy(false);
    }
  }

  return (
    <AuthShell
      title="Log in"
      footer={
        <>
          New here?{" "}
          <Link className="font-medium text-brand" to="/register">
            Create an account
          </Link>
        </>
      }
    >
      <form className="space-y-4" onSubmit={submit} noValidate>
        <Field label="Email">
          <input
            className={inputClass}
            type="email"
            autoComplete="email"
            required
            value={email}
            onChange={(e) => setEmail(e.target.value)}
          />
        </Field>
        <Field label="Password">
          <input
            className={inputClass}
            type="password"
            autoComplete="current-password"
            required
            value={password}
            onChange={(e) => setPassword(e.target.value)}
          />
        </Field>
        {error && (
          <p role="alert" className="text-sm text-danger">
            {error}
          </p>
        )}
        <Button type="submit" className="w-full" disabled={busy || !email || !password}>
          {busy ? "Logging in…" : "Log in"}
        </Button>
      </form>
    </AuthShell>
  );
}

function browserTimezone() {
  try {
    return Intl.DateTimeFormat().resolvedOptions().timeZone || undefined;
  } catch {
    return undefined;
  }
}

export function RegisterPage() {
  const { register } = useAuth();
  const navigate = useNavigate();
  const [form, setForm] = useState({ full_name: "", email: "", password: "", privacy: false });
  const [errors, setErrors] = useState<Record<string, string>>({});
  const [error, setError] = useState<string>();
  const [busy, setBusy] = useState(false);
  const set = (k: keyof typeof form) => (v: string | boolean) => setForm((f) => ({ ...f, [k]: v }));

  async function submit(e: FormEvent) {
    e.preventDefault();
    const local: Record<string, string> = {};
    if (!form.full_name.trim()) local.full_name = "Please enter your name.";
    if (!/^\S+@\S+\.\S+$/.test(form.email)) local.email = "Please enter a valid email address.";
    if (form.password.length < 8) local.password = "Use at least 8 characters.";
    if (!form.privacy) local.privacy_accepted = "You need to accept the privacy notice.";
    setErrors(local);
    if (Object.keys(local).length) return;

    setBusy(true);
    setError(undefined);
    try {
      await register({
        full_name: form.full_name,
        email: form.email,
        password: form.password,
        privacy_accepted: form.privacy,
        timezone: browserTimezone(),
      });
      navigate("/onboarding", { replace: true });
    } catch (err) {
      if (err instanceof ApiError) {
        setErrors(err.fields);
        setError(err.message);
      } else setError("Couldn't reach the server.");
    } finally {
      setBusy(false);
    }
  }

  return (
    <AuthShell
      title="Create your account"
      footer={
        <>
          Already have one?{" "}
          <Link className="font-medium text-brand" to="/login">
            Log in
          </Link>
        </>
      }
    >
      <form className="space-y-4" onSubmit={submit} noValidate>
        <Field label="Name" error={errors.full_name}>
          <input
            className={inputClass}
            autoComplete="name"
            value={form.full_name}
            onChange={(e) => set("full_name")(e.target.value)}
          />
        </Field>
        <Field label="Email" error={errors.email}>
          <input
            className={inputClass}
            type="email"
            autoComplete="email"
            value={form.email}
            onChange={(e) => set("email")(e.target.value)}
          />
        </Field>
        <Field label="Password" hint="At least 8 characters." error={errors.password}>
          <input
            className={inputClass}
            type="password"
            autoComplete="new-password"
            value={form.password}
            onChange={(e) => set("password")(e.target.value)}
          />
        </Field>
        <div>
          <label className="flex items-start gap-3 text-sm">
            <input
              type="checkbox"
              className="mt-0.5 size-5 shrink-0 accent-brand"
              checked={form.privacy}
              onChange={(e) => set("privacy")(e.target.checked)}
            />
            <span>
              I accept the privacy notice: MENTORX stores my answers and response times to estimate
              what I know. I can download or delete my data at any time from Settings.
            </span>
          </label>
          {errors.privacy_accepted && (
            <p className="mt-1 text-xs text-danger">{errors.privacy_accepted}</p>
          )}
        </div>
        {error && !Object.keys(errors).length && (
          <p role="alert" className="text-sm text-danger">
            {error}
          </p>
        )}
        <Button type="submit" className="w-full" disabled={busy}>
          {busy ? "Creating account…" : "Create account"}
        </Button>
      </form>
    </AuthShell>
  );
}
