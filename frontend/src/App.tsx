import { lazy } from "react";
import { BrowserRouter, Navigate, Outlet, Route, Routes, useLocation } from "react-router";
import { AuthProvider, useAuth } from "./auth/AuthContext";
import { AppShell, ProfileGate } from "./components/AppShell";
import { ErrorBoundary } from "./components/ErrorBoundary";
import { Spinner } from "./components/ui";
import { AssessmentRunPage, AssessmentStartPage, ReassessmentResultPage } from "./pages/Assessment";
import { LoginPage, RegisterPage } from "./pages/Auth";
import { LandingPage } from "./pages/Landing";
import { NotFoundPage } from "./pages/NotFound";
import { HomePage } from "./pages/Home";
import { OnboardingPage } from "./pages/Onboarding";
import { PracticePage } from "./pages/Practice";
import { ProfilePage } from "./pages/Profile";
import { SkillPage } from "./pages/Skill";
import { SkillsPage } from "./pages/Skills";

// Chart-heavy and admin screens load on demand, so the landing and sign-in pages stay small.

const DiagnosisPage = lazy(() => import("./pages/Diagnosis").then((m) => ({ default: m.DiagnosisPage })));
const ProgressPage = lazy(() => import("./pages/Progress").then((m) => ({ default: m.ProgressPage })));
const AdminPage = lazy(() => import("./pages/Admin").then((m) => ({ default: m.AdminPage })));

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

function PublicOnly() {
  const { user } = useAuth();
  if (user === undefined) return <Checking />;
  if (user) return <Navigate to="/home" replace />;
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
        <Route element={<ProfileGate />}>
          <Route element={<AppShell />}>
            <Route path="home" element={<HomePage />} />
            <Route path="diagnosis" element={<DiagnosisPage />} />
            <Route path="skills" element={<SkillsPage />} />
            <Route path="skills/:id" element={<SkillPage />} />
            <Route path="progress" element={<ProgressPage />} />
            {/* old addresses from v2 */}
            <Route path="dashboard" element={<Navigate to="/home" replace />} />
            <Route path="path" element={<Navigate to="/home" replace />} />
            <Route path="analytics" element={<Navigate to="/progress" replace />} />
            <Route path="resources" element={<Navigate to="/skills" replace />} />
            <Route path="profile" element={<ProfilePage />} />
            <Route path="assess/start" element={<AssessmentStartPage />} />
            <Route path="assess/:id" element={<AssessmentRunPage />} />
            <Route path="assess/:id/result" element={<ReassessmentResultPage />} />
            <Route path="practice/:id" element={<PracticePage />} />
            <Route path="admin" element={<AdminPage />} />
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
