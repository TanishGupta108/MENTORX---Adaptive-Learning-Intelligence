import { createContext, Suspense, useContext, useEffect, useState } from "react";
import type { ReactNode } from "react";
import { NavLink, Navigate, Outlet, useLocation, useNavigate } from "react-router";
import { BarChart3, BookOpen, Compass, LayoutDashboard, LogOut, Menu, Route as RouteIcon, Settings2, Shield, Sigma, X } from "lucide-react";
import { useAuth } from "../auth/AuthContext";
import { tutor } from "../api/tutor";
import type { Profile } from "../api/tutor";
import { cx, ErrorState, Logo, PageLoader, Spinner } from "./ui";

type ProfileCtx = { profile: Profile; reload: () => Promise<void> };
const Ctx = createContext<ProfileCtx | null>(null);

export function useProfile() {
  const c = useContext(Ctx);
  if (!c) throw new Error("useProfile must be used inside <ProfileGate>");
  return c;
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
  { to: "/dashboard", label: "Dashboard", icon: LayoutDashboard },
  { to: "/path", label: "Learning path", icon: RouteIcon },
  { to: "/skills", label: "Mathematics", icon: Sigma },
  { to: "/resources", label: "Resources", icon: BookOpen },
  { to: "/analytics", label: "Analytics", icon: BarChart3 },
  { to: "/profile", label: "Profile", icon: Settings2 },
];

function NavItems({ admin, onNavigate }: { admin: boolean; onNavigate?: () => void }) {
  const items = admin ? [...NAV, { to: "/admin", label: "Content admin", icon: Shield }] : NAV;
  return (
    <nav className="space-y-1" aria-label="Main">
      {items.map(({ to, label, icon: Icon }) => (
        <NavLink
          key={to}
          to={to}
          onClick={onNavigate}
          className={({ isActive }) =>
            cx(
              "flex items-center gap-3 rounded-xl px-3 py-2.5 text-sm font-medium transition-colors",
              isActive ? "bg-brand-soft text-ink" : "text-ink-muted hover:bg-surface-2 hover:text-ink",
            )
          }
        >
          {({ isActive }) => (
            <>
              <Icon className={cx("size-[18px]", isActive ? "text-brand" : "")} />
              {label}
            </>
          )}
        </NavLink>
      ))}
    </nav>
  );
}

export function AppShell() {
  const { profile } = useProfile();
  const { logout } = useAuth();
  const navigate = useNavigate();
  const location = useLocation();
  const [open, setOpen] = useState(false);
  useEffect(() => setOpen(false), [location.pathname]);

  async function signOut() {
    await logout();
    navigate("/", { replace: true });
  }

  const initials = profile.full_name
    .split(" ")
    .map((p) => p[0])
    .slice(0, 2)
    .join("")
    .toUpperCase();

  const side = (
    <div className="flex h-full flex-col gap-6 p-4">
      <div className="px-2 pt-1">
        <Logo />
      </div>
      <div className="rounded-xl border border-line bg-surface-2 px-3 py-2.5">
        <p className="text-[11px] font-semibold uppercase tracking-wider text-ink-faint">Subject</p>
        <p className="mt-0.5 flex items-center gap-2 text-sm font-medium">
          <Compass className="size-4 text-accent" /> Mathematics
        </p>
      </div>
      <NavItems admin={profile.is_admin} onNavigate={() => setOpen(false)} />
      <div className="mt-auto flex items-center gap-3 rounded-xl border border-line p-3">
        <span className="grid size-9 place-items-center rounded-full bg-surface-3 text-sm font-semibold">{initials}</span>
        <div className="min-w-0 flex-1">
          <p className="truncate text-sm font-medium">{profile.full_name}</p>
          <p className="truncate text-xs text-ink-faint">{profile.email}</p>
        </div>
        <button type="button" onClick={signOut} className="rounded-lg p-2 text-ink-muted hover:bg-surface-2 hover:text-ink" aria-label="Log out" title="Log out">
          <LogOut className="size-4" />
        </button>
      </div>
    </div>
  );

  return (
    <div className="min-h-screen lg:grid lg:grid-cols-[260px_1fr]">
      <aside className="sticky top-0 hidden h-screen border-r border-line bg-surface/60 lg:block">{side}</aside>

      <div className="sticky top-0 z-30 flex items-center justify-between border-b border-line bg-canvas/90 px-4 py-3 backdrop-blur lg:hidden">
        <Logo />
        <button type="button" onClick={() => setOpen(true)} className="rounded-lg p-2 hover:bg-surface-2" aria-label="Open menu">
          <Menu className="size-5" />
        </button>
      </div>
      {open && (
        <div className="fixed inset-0 z-40 lg:hidden" role="dialog" aria-modal>
          <button type="button" className="absolute inset-0 bg-black/60" aria-label="Close menu" onClick={() => setOpen(false)} />
          <div className="absolute inset-y-0 left-0 w-72 border-r border-line bg-surface">
            <button type="button" onClick={() => setOpen(false)} className="absolute right-3 top-4 rounded-lg p-2 hover:bg-surface-2" aria-label="Close menu">
              <X className="size-5" />
            </button>
            {side}
          </div>
        </div>
      )}

      <main className="mx-auto w-full max-w-6xl px-4 py-6 sm:px-6 lg:px-10 lg:py-10">
        <Suspense fallback={<PageLoader />}>
          <Outlet />
        </Suspense>
      </main>
    </div>
  );
}
