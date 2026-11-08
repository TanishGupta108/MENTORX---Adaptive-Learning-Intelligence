import { render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
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

const emptyStreak = {
  daily_goal: 10,
  today_valid: 0,
  goal_met_today: false,
  just_met: false,
  current_streak: 0,
  longest_streak: 0,
  today: "2026-11-09",
  timezone: "Asia/Kolkata",
};

const emptyWeekly = {
  subject: "ML",
  start: "2026-11-03",
  end: "2026-11-09",
  questions: 0,
  accuracy: null,
  goal_days_met: 0,
  mean_mastery_start: null,
  mean_mastery_end: null,
  mastery_change: null,
  concepts_improved: [],
};

const dashboardRoutes = {
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
  "GET /engagement/streak": { body: emptyStreak },
  "GET /engagement/weekly": { body: emptyWeekly },
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
    mockApi(dashboardRoutes);
    renderAt("/dashboard");
    expect(await screen.findByText("Hi, Asha")).toBeInTheDocument();
    expect(screen.getByText("Mean mastery").nextSibling).toHaveTextContent("—");
    expect(screen.getByText("Accuracy").nextSibling).toHaveTextContent("—");
    expect(screen.getByRole("button", { name: /start the diagnostic/i })).toBeInTheDocument();
    expect(await screen.findByText("No activity yet")).toBeInTheDocument();
    expect(screen.getAllByText("Not enough answers yet")).toHaveLength(2);
    expect(await screen.findByText(/to reach today's goal/)).toHaveTextContent(
      "10 more questions to reach today's goal.",
    );
    expect(await screen.findByText("No activity this week")).toBeInTheDocument();
  });

  it("dashboard shows the streak and the weekly report (FR-ENG-03/05)", async () => {
    mockApi({
      ...dashboardRoutes,
      "GET /engagement/streak": {
        body: { ...emptyStreak, today_valid: 12, goal_met_today: true, current_streak: 4, longest_streak: 9 },
      },
      "GET /engagement/weekly": {
        body: {
          ...emptyWeekly,
          questions: 40,
          accuracy: 0.75,
          goal_days_met: 5,
          mean_mastery_start: 0.5,
          mean_mastery_end: 0.62,
          mastery_change: 0.12,
          concepts_improved: [{ concept: "ml.knn", name: "k-Nearest Neighbours", before: 0.4, after: 0.7 }],
        },
      },
    });
    renderAt("/dashboard");
    expect(await screen.findByText("Goal reached today.")).toBeInTheDocument();
    expect(screen.getByRole("progressbar", { name: "Today's goal" })).toHaveAttribute("aria-valuenow", "10");
    expect(screen.getByText("Current streak").nextSibling).toHaveTextContent("4 days");
    expect(screen.getByText("Longest streak").nextSibling).toHaveTextContent("9 days");
    expect(await screen.findByText("Goal days")).toBeInTheDocument();
    expect(screen.getByText("Goal days").nextSibling).toHaveTextContent("5 / 7");
    expect(screen.getByText("(+12 pts)")).toBeInTheDocument();
    expect(screen.getByText("k-Nearest Neighbours: 40% → 70%")).toBeInTheDocument();
  });

  it("feedback can be sent from any page (FR-PILOT-03)", async () => {
    const calls = mockApi({ ...dashboardRoutes, "POST /feedback": { status: 201, body: { id: 1 } } });
    renderAt("/dashboard");
    await userEvent.click(await screen.findByRole("button", { name: "Feedback" }));
    const dialog = screen.getByRole("dialog", { name: "Send feedback" });
    await userEvent.click(within(dialog).getByRole("button", { name: "Send" }));
    expect(within(dialog).getByRole("alert")).toHaveTextContent("Pick a rating");
    expect(calls.some((c) => c.path === "/feedback")).toBe(false);

    await userEvent.click(within(dialog).getByRole("radio", { name: "4 out of 5" }));
    await userEvent.selectOptions(within(dialog).getByRole("combobox"), "content");
    await userEvent.type(within(dialog).getByRole("textbox"), "  Question 3 is unclear ");
    await userEvent.click(within(dialog).getByRole("button", { name: "Send" }));
    expect(await within(dialog).findByText(/Thank you/)).toBeInTheDocument();
    expect(calls.find((c) => c.path === "/feedback")!.body).toEqual({
      rating: 4,
      category: "content",
      message: "Question 3 is unclear",
      page: "/dashboard",
    });
    await userEvent.click(within(dialog).getByRole("button", { name: "Close" }));
    expect(screen.queryByRole("dialog")).not.toBeInTheDocument();
  });

  it("unknown pages get a 404 page", async () => {
    mockApi({ "POST /auth/refresh": { status: 401 } });
    renderAt("/nope");
    expect(await screen.findByRole("heading", { name: "Page not found" })).toBeInTheDocument();
  });
});
