import { render, screen } from "@testing-library/react";
import { MemoryRouter } from "react-router";
import { afterEach, describe, expect, it, vi } from "vitest";
import { AppRoutes } from "./App";
import { setAccessToken } from "./api/client";
import { AuthProvider } from "./auth/AuthContext";
import { loggedIn, mockApi, user } from "./test/mockApi";

function renderAt(path: string) {
  return render(
    <MemoryRouter initialEntries={[path]}>
      <AuthProvider>
        <AppRoutes />
      </AuthProvider>
    </MemoryRouter>,
  );
}

afterEach(() => {
  vi.unstubAllGlobals();
  setAccessToken(null);
});

const emptyDashboard = {
  subject: "ML",
  diagnostic_completed: false,
  concepts_total: 19,
  concepts_assessed: 0,
  concepts_mastered: 0,
  mastered_threshold: 0.8,
  mean_mastery: null,
  questions_answered: 0,
  accuracy: null,
  sessions_completed: 0,
  strongest: [],
  weakest: [],
  active_sessions: [],
};

describe("routing and auth", () => {
  it("shows the landing page when logged out", async () => {
    mockApi({ "POST /auth/refresh": { status: 401 } });
    renderAt("/");
    expect(await screen.findByRole("link", { name: /create a free account/i })).toBeInTheDocument();
  });

  it("sends logged-out visitors of protected pages to login", async () => {
    mockApi({ "POST /auth/refresh": { status: 401 } });
    renderAt("/dashboard");
    expect(await screen.findByRole("heading", { name: "Log in" })).toBeInTheDocument();
  });

  it("sends students who aren't enrolled to onboarding", async () => {
    mockApi({
      ...loggedIn,
      "GET /me": { body: { ...user, enrolled_subjects: [] } },
      "GET /subjects": {
        body: [
          {
            code: "ML",
            name: "Machine Learning",
            description: "",
            concept_count: 19,
            enrolled: false,
          },
        ],
      },
    });
    renderAt("/dashboard");
    expect(await screen.findByRole("button", { name: /start the diagnostic/i })).toBeInTheDocument();
    expect(screen.getByText(/19 questions, one per concept/)).toBeInTheDocument();
  });

  it("dashboard empty state shows no placeholder numbers (FR-DASH-08)", async () => {
    mockApi({
      ...loggedIn,
      "GET /dashboard": { body: emptyDashboard },
      "GET /learning-path": {
        body: {
          id: "p",
          subject: "ML",
          trigger: "manual",
          generated_at: "2026-11-08T10:00:00Z",
          model_version: "ednet-gbm-v1",
          items: [],
        },
      },
      "GET /revision": {
        body: { subject: "ML", threshold: 0.6, due: [], upcoming: [], horizon_days: 180 },
      },
      "GET /dashboard/trends": {
        body: {
          subject: "ML",
          days: 30,
          points: [{ day: "2026-11-08", answered: 0, accuracy: null, mean_mastery: null }],
        },
      },
      "GET /dashboard/activity": {
        body: { weeks: 12, timezone: "Asia/Kolkata", days: [{ day: "2026-11-08", answered: 0 }] },
      },
    });
    renderAt("/dashboard");
    expect(await screen.findByText("Hi, Asha")).toBeInTheDocument();
    expect(screen.getByText("Mean mastery").nextSibling).toHaveTextContent("—");
    expect(screen.getByText("Accuracy").nextSibling).toHaveTextContent("—");
    expect(screen.getByRole("button", { name: /start the diagnostic/i })).toBeInTheDocument();
    expect(await screen.findByText("No activity yet")).toBeInTheDocument();
    expect(screen.getAllByText("Not enough answers yet")).toHaveLength(2);
  });

  it("unknown pages get a 404 page", async () => {
    mockApi({ "POST /auth/refresh": { status: 401 } });
    renderAt("/nope");
    expect(await screen.findByRole("heading", { name: "Page not found" })).toBeInTheDocument();
  });
});
