import { createContext, Suspense, useContext, useEffect, useRef, useState } from "react";
import type { ReactNode } from "react";
import { Link, NavLink, Navigate, Outlet, useLocation, useNavigate } from "react-router";
import { BarChart3, FileText, Home, LayoutGrid, LogOut, Shield, UserRound } from "lucide-react";
import { useAuth } from "../auth/AuthContext";
import { tutor } from "../api/tutor";
import type { Profile, SubjectInfo } from "../api/tutor";
import { useApi } from "../hooks/useApi";
import { SubjectSwitcher } from "./SubjectSwitcher";
import { cx, ErrorState, Logo, PageLoader, Spinner } from "./ui";

type ProfileCtx = { profile: Profile; reload: () => Promise<void> };
const Ctx = createContext<ProfileCtx | null>(null);

export function useProfile() {
  const c = useContext(Ctx);
  if (!c) throw new Error("useProfile must be used inside <ProfileGate>");
  return c;
}

type SubjectsCtx = { subjects: SubjectInfo[] | undefined; reload: () => void };
const SubjectsContext = createContext<SubjectsCtx>({ subjects: undefined, reload: () => undefined });

/** Active subjects (GET /subjects); undefined while loading or if the call failed. */
export function useSubjects() {
  return useContext(SubjectsContext);
}

/** Loads the learner profile; sends students who haven't onboarded to onboarding. */
export function ProfileGate({ requireOnboarded = true, children }: { requireOnboarded?: boolean; children?: ReactNode }) {
  const [profile, setProfile] = useState<Profile | null>(null);
  const [error, setError] = useState<Error | null>(null);
  const load = async () => {
    try {
      setProfile(await tutor.profile());
    } catch (e) {
      setError(e as Error);
    }
  };
  useEffect(() => {
    void load();
  }, []);
  if (error) {
    return (
      <div className="mx-auto max-w-lg p-8">
        <ErrorState error={error} onRetry={() => { setError(null); void load(); }} />
      </div>
    );
  }
  if (!profile) {
    return (
      <div className="mx-auto max-w-lg p-8">
        <Spinner label="Loading your learning profile…" />
      </div>
    );
  }
  if (requireOnboarded && !profile.onboarded) return <Navigate to="/onboarding" replace />;
  return <Ctx.Provider value={{ profile, reload: load }}>{children ?? <Outlet />}</Ctx.Provider>;
}

const NAV = [
  { to: "/home", label: "Home", icon: Home },
  { to: "/skills", label: "Skills", icon: LayoutGrid },
  { to: "/progress", label: "Progress", icon: BarChart3 },
];
const ADMIN = { to: "/admin", label: "Admin", icon: Shield };

function SideNav({ admin }: { admin: boolean }) {
  const items = admin ? [...NAV, ADMIN] : NAV;
  return (
    <nav className="space-y-1" aria-label="Main">
      {items.map(({ to, label, icon: Icon }) => (
        <NavLink
          key={to}
          to={to}
          className={({ isActive }) =>
            cx("flex min-h-11 items-center gap-3 rounded-xl px-3 text-sm font-medium transition-colors", isActive ? "bg-brand-soft text-ink" : "text-ink-muted hover:bg-surface-2 hover:text-ink")
          }
        >
          {({ isActive }) => (
            <>
              <Icon className={cx("size-[18px]", isActive && "text-brand")} aria-hidden />
              {label}
            </>
          )}
        </NavLink>
      ))}
    </nav>
  );
}

function BottomNav({ admin }: { admin: boolean }) {
  const items = admin ? [...NAV, ADMIN] : NAV;
  return (
    <nav aria-label="Main (mobile)" className="fixed inset-x-0 bottom-0 z-30 border-t border-line bg-canvas/95 pb-[env(safe-area-inset-bottom)] backdrop-blur lg:hidden">
      <ul className="mx-auto flex max-w-md">
        {items.map(({ to, label, icon: Icon }) => (
          <li key={to} className="flex-1">
            <NavLink to={to} className={({ isActive }) => cx("flex min-h-14 flex-col items-center justify-center gap-0.5 text-[11px] font-medium", isActive ? "text-brand" : "text-ink-muted hover:text-ink")}>
              <Icon className="size-5" aria-hidden />
              {label}
            </NavLink>
          </li>
        ))}
      </ul>
    </nav>
  );
}

function AvatarMenu({ profile }: { profile: Profile }) {
  const { logout } = useAuth();
  const navigate = useNavigate();
  const location = useLocation();
  const [open, setOpen] = useState(false);
  const ref = useRef<HTMLDivElement>(null);
  useEffect(() => setOpen(false), [location.pathname, location.hash]);
  useEffect(() => {
    if (!open) return;
    const onDown = (e: MouseEvent) => {
      if (ref.current && !ref.current.contains(e.target as Node)) setOpen(false);
    };
    const onKey = (e: KeyboardEvent) => e.key === "Escape" && setOpen(false);
    document.addEventListener("mousedown", onDown);
    document.addEventListener("keydown", onKey);
    return () => {
      document.removeEventListener("mousedown", onDown);
      document.removeEventListener("keydown", onKey);
    };
  }, [open]);

  const initials = profile.full_name
    .split(" ")
    .filter(Boolean)
    .map((p) => p[0])
    .slice(0, 2)
    .join("")
    .toUpperCase();

  async function signOut() {
    await logout();
    navigate("/", { replace: true });
  }

  const item = "flex min-h-11 w-full items-center gap-2.5 rounded-lg px-3 text-left text-sm hover:bg-surface-3";
  return (
    <div className="relative" ref={ref}>
      <button
        type="button"
        onClick={() => setOpen((o) => !o)}
        aria-haspopup="menu"
        aria-expanded={open}
        aria-label="Account menu"
        className="grid size-11 place-items-center rounded-full border border-line-strong bg-surface-3 text-sm font-semibold hover:border-brand sm:size-10"
      >
        {initials || <UserRound className="size-4" />}
      </button>
      {open && (
        <div role="menu" className="absolute right-0 top-full z-40 mt-2 w-60 rounded-2xl border border-line-strong bg-surface-2 p-1.5 shadow-2xl animate-rise">
          <div className="px-3 py-2">
            <p className="truncate text-sm font-medium">{profile.full_name}</p>
            <p className="truncate text-xs text-ink-faint">{profile.email}</p>
          </div>
          <div className="my-1 h-px bg-line" />
          <Link role="menuitem" to="/profile" className={item}>
            <UserRound className="size-4 text-ink-muted" aria-hidden /> Profile
          </Link>
          <Link role="menuitem" to="/profile#credits" className={item}>
            <FileText className="size-4 text-ink-muted" aria-hidden /> Data &amp; credits
          </Link>
          <button role="menuitem" type="button" onClick={signOut} className={item}>
            <LogOut className="size-4 text-ink-muted" aria-hidden /> Log out
          </button>
        </div>
      )}
    </div>
  );
}

export function AppShell() {
  const { profile, reload } = useProfile();
  const subjects = useApi(() => tutor.subjects(), [profile.subject_code]);
  const location = useLocation();
  // practice and assessments get a narrower, focused column
  const focused = /^\/(practice|assess)\//.test(location.pathname);

  const topRight = (
    <div className="flex items-center gap-2">
      <SubjectSwitcher subjects={subjects.data} current={profile.subject_code} onSwitched={reload} />
      <AvatarMenu profile={profile} />
    </div>
  );

  return (
    <SubjectsContext.Provider value={{ subjects: subjects.data, reload: subjects.reload }}>
      <div className="min-h-screen lg:grid lg:grid-cols-[232px_1fr]">
        <aside className="sticky top-0 hidden h-screen border-r border-line bg-surface/60 lg:block">
          <div className="flex h-full flex-col gap-8 p-4">
            <Link to="/home" className="px-2 pt-1" aria-label="MENTORX home">
              <Logo />
            </Link>
            <SideNav admin={profile.is_admin} />
          </div>
        </aside>

        <div className="min-w-0">
          <header className="sticky top-0 z-30 border-b border-line bg-canvas/90 backdrop-blur">
            <div className="mx-auto flex h-16 max-w-[960px] items-center justify-between gap-3 px-4 sm:px-6">
              <Link to="/home" className="lg:invisible" aria-label="MENTORX home">
                <Logo />
              </Link>
              {topRight}
            </div>
          </header>
          <main className={cx("mx-auto w-full px-4 pb-28 pt-6 sm:px-6 lg:pb-12 lg:pt-8", focused ? "max-w-[720px]" : "max-w-[960px]")}>
            <Suspense fallback={<PageLoader />}>
              <Outlet />
            </Suspense>
          </main>
        </div>
        <BottomNav admin={profile.is_admin} />
      </div>
    </SubjectsContext.Provider>
  );
}
