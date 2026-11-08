import { BrowserRouter, Navigate, Outlet, Route, Routes, useLocation } from "react-router";
import { SUBJECT } from "./api/endpoints";
import { AuthProvider, useAuth } from "./auth/AuthContext";
import { ErrorBoundary } from "./components/ErrorBoundary";
import { Layout } from "./components/Layout";
import { Spinner } from "./components/ui";
import { ConceptsPage } from "./pages/Concepts";
import { DashboardPage } from "./pages/Dashboard";
import { HistoryPage } from "./pages/History";
import { LandingPage } from "./pages/Landing";
import { LoginPage, RegisterPage } from "./pages/Auth";
import { NotFoundPage } from "./pages/NotFound";
import { OnboardingPage } from "./pages/Onboarding";
import { PathPage } from "./pages/Path";
import { RevisionPage } from "./pages/Revision";
import { SessionPage } from "./pages/Session";
import { SettingsPage } from "./pages/Settings";

function Checking() {
  return (
    <div className="mx-auto max-w-md px-4 py-16">
      <Spinner label="Checking your session…" />
    </div>
  );
}

function RequireAuth() {
  const { user } = useAuth();
  const location = useLocation();
  if (user === undefined) return <Checking />;
  if (user === null) {
    const next = encodeURIComponent(location.pathname + location.search);
    return <Navigate to={`/login?next=${next}`} replace />;
  }
  return <Outlet />;
}

function RequireEnrolled() {
  const { user } = useAuth();
  if (user && !user.enrolled_subjects.includes(SUBJECT)) return <Navigate to="/onboarding" replace />;
  return <Outlet />;
}

function PublicOnly() {
  const { user } = useAuth();
  if (user === undefined) return <Checking />;
  if (user) return <Navigate to="/dashboard" replace />;
  return <Outlet />;
}

export function AppRoutes() {
  return (
    <Routes>
      <Route element={<PublicOnly />}>
        <Route index element={<LandingPage />} />
        <Route path="login" element={<LoginPage />} />
        <Route path="register" element={<RegisterPage />} />
      </Route>
      <Route element={<RequireAuth />}>
        <Route path="onboarding" element={<OnboardingPage />} />
        <Route element={<RequireEnrolled />}>
          <Route element={<Layout />}>
            <Route path="dashboard" element={<DashboardPage />} />
            <Route path="path" element={<PathPage />} />
            <Route path="revision" element={<RevisionPage />} />
            <Route path="concepts" element={<ConceptsPage />} />
            <Route path="history" element={<HistoryPage />} />
            <Route path="settings" element={<SettingsPage />} />
            <Route path="session/:id" element={<SessionPage />} />
          </Route>
        </Route>
      </Route>
      <Route path="*" element={<NotFoundPage />} />
    </Routes>
  );
}

export default function App() {
  return (
    <ErrorBoundary>
      <BrowserRouter>
        <AuthProvider>
          <AppRoutes />
        </AuthProvider>
      </BrowserRouter>
    </ErrorBoundary>
  );
}
