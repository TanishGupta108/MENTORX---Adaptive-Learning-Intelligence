import { useState } from "react";
import { NavLink, Outlet, useNavigate } from "react-router";
import { useAuth } from "../auth/AuthContext";
import { FeedbackDialog } from "./FeedbackDialog";
import { cx } from "./ui";

const links = [
  { to: "/dashboard", label: "Dashboard" },
  { to: "/path", label: "Learning path" },
  { to: "/revision", label: "Revision" },
  { to: "/concepts", label: "Concepts" },
  { to: "/history", label: "History" },
  { to: "/settings", label: "Settings" },
];

export function Layout() {
  const { user, logout } = useAuth();
  const navigate = useNavigate();
  const [open, setOpen] = useState(false);
  const [feedback, setFeedback] = useState(false);

  const linkClass = ({ isActive }: { isActive: boolean }) =>
    cx(
      "flex min-h-11 items-center rounded-lg px-3 text-sm font-medium",
      isActive ? "bg-brand/10 text-brand" : "text-ink-muted hover:bg-canvas hover:text-ink",
    );

  return (
    <div className="min-h-screen">
      <a
        href="#main"
        className="sr-only focus:not-sr-only focus:absolute focus:left-4 focus:top-4 focus:z-50 focus:rounded focus:bg-surface focus:px-3 focus:py-2"
      >
        Skip to content
      </a>
      <header className="sticky top-0 z-40 border-b border-line bg-surface/95 backdrop-blur">
        <div className="mx-auto flex max-w-6xl items-center justify-between gap-4 px-4 py-2">
          <NavLink to="/dashboard" className="text-lg font-semibold tracking-tight">
            MENTOR<span className="text-brand">X</span>
          </NavLink>
          <nav aria-label="Main" className="hidden items-center gap-1 lg:flex">
            {links.map((l) => (
              <NavLink key={l.to} to={l.to} className={linkClass}>
                {l.label}
              </NavLink>
            ))}
          </nav>
          <div className="flex items-center gap-2">
            <button
              type="button"
              className="min-h-11 rounded-lg border border-line px-3 text-sm text-ink-muted hover:text-ink"
              onClick={() => setFeedback(true)}
            >
              Feedback
            </button>
            <span className="hidden max-w-40 truncate text-sm text-ink-muted sm:inline">
              {user?.full_name}
            </span>
            <button
              type="button"
              className="hidden min-h-11 rounded-lg px-3 text-sm text-ink-muted hover:text-ink lg:inline"
              onClick={async () => {
                await logout();
                navigate("/login");
              }}
            >
              Log out
            </button>
            <button
              type="button"
              className="min-h-11 min-w-11 rounded-lg border border-line lg:hidden"
              aria-expanded={open}
              aria-controls="mobile-nav"
              aria-label={open ? "Close menu" : "Open menu"}
              onClick={() => setOpen((o) => !o)}
            >
              {open ? "✕" : "☰"}
            </button>
          </div>
        </div>
        {open && (
          <nav id="mobile-nav" aria-label="Main" className="border-t border-line px-4 py-2 lg:hidden">
            {links.map((l) => (
              <NavLink key={l.to} to={l.to} className={linkClass} onClick={() => setOpen(false)}>
                {l.label}
              </NavLink>
            ))}
            <button
              type="button"
              className="flex min-h-11 w-full items-center rounded-lg px-3 text-sm text-ink-muted"
              onClick={async () => {
                await logout();
                navigate("/login");
              }}
            >
              Log out
            </button>
          </nav>
        )}
      </header>
      <main id="main" className="mx-auto max-w-6xl px-4 py-6 sm:py-8">
        <Outlet />
      </main>
      {feedback && <FeedbackDialog onClose={() => setFeedback(false)} />}
    </div>
  );
}
