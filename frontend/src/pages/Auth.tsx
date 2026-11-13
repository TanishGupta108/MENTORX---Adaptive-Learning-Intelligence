import { useState } from "react";
import type { FormEvent, ReactNode } from "react";
import { Link, useNavigate, useSearchParams } from "react-router";
import { ApiError } from "../api/client";
import { useAuth } from "../auth/AuthContext";
import { Button, Field, inputClass, Logo } from "../components/ui";

function AuthShell({ title, subtitle, children, footer }: { title: string; subtitle: string; children: ReactNode; footer: ReactNode }) {
  return (
    <div className="relative grid min-h-screen place-items-center px-4 py-10">
      <div className="pointer-events-none absolute inset-0 bg-[radial-gradient(50%_40%_at_50%_0%,#6d6ef72b,transparent)]" />
      <main className="relative w-full max-w-md">
        <Link to="/" className="mb-8 inline-block">
          <Logo />
        </Link>
        <div className="rounded-3xl border border-line bg-surface p-7 shadow-[0_30px_80px_-40px_#6d6ef766]">
          <h1 className="text-2xl font-semibold tracking-tight">{title}</h1>
          <p className="mt-1 text-sm text-ink-muted">{subtitle}</p>
          <div className="mt-6">{children}</div>
        </div>
        <p className="mt-5 text-center text-sm text-ink-muted">{footer}</p>
      </main>
    </div>
  );
}

/** Only allow redirects to paths inside the app (no open redirect). */
function safeNext(next: string | null) {
  return next && next.startsWith("/") && !next.startsWith("//") ? next : "/home";
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
      setError(err instanceof ApiError ? err.message : "Couldn't sign in. Check your connection and try again.");
    } finally {
      setBusy(false);
    }
  }

  return (
    <AuthShell title="Welcome back" subtitle="Sign in to continue your learning journey." footer={<>New to MENTORX? <Link to="/register" className="font-medium text-brand hover:underline">Create an account</Link></>}>
      <form onSubmit={submit} className="space-y-4" noValidate>
        <Field label="Email">
          <input className={inputClass} type="email" autoComplete="email" required value={email} onChange={(e) => setEmail(e.target.value)} />
        </Field>
        <Field label="Password">
          <input className={inputClass} type="password" autoComplete="current-password" required value={password} onChange={(e) => setPassword(e.target.value)} />
        </Field>
        {error && <p className="rounded-xl bg-danger/10 px-3 py-2 text-sm text-danger" role="alert">{error}</p>}
        <Button type="submit" size="lg" className="w-full" loading={busy}>
          Sign in
        </Button>
      </form>
    </AuthShell>
  );
}

export function RegisterPage() {
  const { register } = useAuth();
  const navigate = useNavigate();
  const [name, setName] = useState("");
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [accepted, setAccepted] = useState(false);
  const [fields, setFields] = useState<Record<string, string>>({});
  const [error, setError] = useState<string>();
  const [busy, setBusy] = useState(false);

  async function submit(e: FormEvent) {
    e.preventDefault();
    const local: Record<string, string> = {};
    if (!name.trim()) local.full_name = "Tell us your name.";
    if (!/^\S+@\S+\.\S+$/.test(email)) local.email = "Enter a valid email address.";
    if (password.length < 8) local.password = "Use at least 8 characters.";
    if (!accepted) local.privacy_accepted = "Please accept to continue.";
    setFields(local);
    if (Object.keys(local).length) return;
    setBusy(true);
    setError(undefined);
    try {
      await register({
        email,
        password,
        full_name: name,
        privacy_accepted: true,
        timezone: Intl.DateTimeFormat().resolvedOptions().timeZone,
      });
      navigate("/onboarding", { replace: true });
    } catch (err) {
      if (err instanceof ApiError) {
        setFields(err.fields);
        setError(Object.keys(err.fields).length ? undefined : err.message);
      } else {
        setError("Couldn't create your account. Check your connection and try again.");
      }
    } finally {
      setBusy(false);
    }
  }

  return (
    <AuthShell title="Create your account" subtitle="It takes less than a minute." footer={<>Already have an account? <Link to="/login" className="font-medium text-brand hover:underline">Sign in</Link></>}>
      <form onSubmit={submit} className="space-y-4" noValidate>
        <Field label="Full name" error={fields.full_name}>
          <input className={inputClass} autoComplete="name" value={name} onChange={(e) => setName(e.target.value)} />
        </Field>
        <Field label="Email" error={fields.email}>
          <input className={inputClass} type="email" autoComplete="email" value={email} onChange={(e) => setEmail(e.target.value)} />
        </Field>
        <Field label="Password" error={fields.password} hint="At least 8 characters.">
          <input className={inputClass} type="password" autoComplete="new-password" value={password} onChange={(e) => setPassword(e.target.value)} />
        </Field>
        <label className="flex items-start gap-3 text-sm text-ink-muted">
          <input type="checkbox" className="mt-1 size-4 accent-[#8b8cff]" checked={accepted} onChange={(e) => setAccepted(e.target.checked)} />
          <span>
            I agree that MENTORX stores my answers to personalise my learning. My data is never sold or shared.
            {fields.privacy_accepted && <span className="block text-danger">{fields.privacy_accepted}</span>}
          </span>
        </label>
        {error && <p className="rounded-xl bg-danger/10 px-3 py-2 text-sm text-danger" role="alert">{error}</p>}
        <Button type="submit" size="lg" className="w-full" loading={busy}>
          Create account
        </Button>
      </form>
    </AuthShell>
  );
}
