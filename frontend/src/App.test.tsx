/**
 * Screen-level tests: each page is rendered against a mocked API and checked for the
 * behaviours the product depends on (honest labels, no answer leaks, adaptive feedback).
 */
import { render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter } from "react-router";
import { afterEach, describe, expect, it, vi } from "vitest";
import { AuthProvider } from "./auth/AuthContext";
import { AppRoutes } from "./App";
import { Markdown } from "./components/Markdown";
import { QuestionView } from "./components/QuestionView";
import { setAccessToken } from "./api/client";
import { loggedIn, mockApi } from "./test/mockApi";
import { choiceQuestion, dashboard, diagnosis, numericQuestion, profile } from "./test/fixtures";

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

describe("public pages", () => {
  it("shows the landing page with the brand headline and calls to action", async () => {
    mockApi({ "POST /auth/refresh": { status: 401 } });
    renderAt("/");
    expect(await screen.findByRole("heading", { level: 1 })).toHaveTextContent("Your Learning Journey. Your Pace. Your Mentor.");
    expect(screen.getAllByRole("link", { name: /get started/i }).length).toBeGreaterThan(0);
    expect(screen.getByRole("link", { name: /how it works/i })).toBeInTheDocument();
  });

  it("validates registration before calling the API", async () => {
    const calls = mockApi({ "POST /auth/refresh": { status: 401 } });
    renderAt("/register");
    await userEvent.click(await screen.findByRole("button", { name: /create account/i }));
    expect(screen.getByText("Tell us your name.")).toBeInTheDocument();
    expect(calls.some((c) => c.path === "/auth/register")).toBe(false);
  });
});

describe("signed-in screens", () => {
  it("sends students who haven't onboarded to onboarding", async () => {
    mockApi({ ...loggedIn, "GET /api/v2/profile": { body: { ...profile, onboarded: false } }, "GET /api/v2/subject": { body: { subject: { code: "MATH", name: "Mathematics", description: "Maths" }, n_skills: 90, n_questions: 1942, domains: [], model: dashboard.model } } });
    renderAt("/dashboard");
    expect(await screen.findByRole("heading", { name: /what would you like to achieve/i })).toBeInTheDocument();
  });

  it("dashboard greets the student and explains its recommendation", async () => {
    mockApi({ ...loggedIn, "GET /api/v2/profile": { body: profile }, "GET /api/v2/dashboard": { body: dashboard } });
    renderAt("/dashboard");
    // the dashboard is lazy-loaded (it carries the charts), so allow it time to arrive
    expect(await screen.findByRole("heading", { level: 1, name: /, Asha$/ }, { timeout: 8000 })).toBeInTheDocument();
    expect(screen.getByText("Let's make progress today.")).toBeInTheDocument();
    expect(screen.getAllByText(/may benefit from additional practice/).length).toBeGreaterThan(0);
    expect(screen.getByRole("link", { name: /continue/i })).toHaveAttribute("href", "/skills/222");
    expect(screen.getByText("Build 3 likely strengths")).toBeInTheDocument();
  });

  it("diagnosis separates observed results from model estimates", async () => {
    mockApi({ ...loggedIn, "GET /api/v2/profile": { body: profile }, "GET /api/v2/diagnosis": { body: diagnosis } });
    renderAt("/diagnosis");
    expect(await screen.findByRole("heading", { name: "Your learning profile is ready." }, { timeout: 8000 })).toBeInTheDocument();
    expect(screen.getByText("6 of 10 correct")).toBeInTheDocument();
    // unassessed skills are never labelled weak, even with a low model estimate
    const unassessed = screen.getByText("Solve 2-Step Equations").closest("a")!;
    expect(within(unassessed).getByText("Needs Assessment")).toBeInTheDocument();
    expect(within(unassessed).getByText(/41% predicted success/)).toBeInTheDocument();
    expect(within(unassessed).getByText("Not attempted yet")).toBeInTheDocument();
  });
});

describe("questions", () => {
  it("submits a numeric answer and only then shows the correct answer", async () => {
    const onSubmit = vi.fn();
    const { rerender } = render(<QuestionView question={numericQuestion} onSubmit={onSubmit} submitting={false} locked={false} />);
    expect(screen.queryByText(/correct answer/i)).not.toBeInTheDocument();
    await userEvent.type(screen.getByLabelText("Your answer"), "4500");
    await userEvent.click(screen.getByRole("button", { name: /submit answer/i }));
    expect(onSubmit).toHaveBeenCalledWith({ item_id: 448752, value: "4500" });
    rerender(
      <QuestionView
        question={numericQuestion}
        onSubmit={onSubmit}
        submitting={false}
        locked
        feedback={{ correct: false, correct_answer: { type: "numeric", values: ["4500"] }, message: "Not quite." }}
      />,
    );
    expect(screen.getByText("Not quite.")).toBeInTheDocument();
    expect(screen.getByText("4500")).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: /submit answer/i })).not.toBeInTheDocument();
  });

  it("practice shows why a question was chosen, offers hints and reports difficulty changes", async () => {
    const calls = mockApi({
      ...loggedIn,
      "GET /api/v2/profile": { body: profile },
      "GET /api/v2/practice/p1/next": { body: choiceQuestion },
      "POST /api/v2/practice/p1/hint": { body: { kind: "concept", text: "Area = πr².", source: "Circumference and area of circles" } },
      "POST /api/v2/practice/p1/answer": {
        body: { correct: true, hint_used: true, revealed: false, correct_answer: { type: "multiple_choice", option_ids: ["2"], options_html: ["About 2,700 in²"] }, message: "You're improving! Two in a row, so the next question is a little harder.", difficulty_before: "medium", difficulty_next: "hard", difficulty_change: "up", answered: 2, total: 8, complete: false, summary: null },
      },
    });
    renderAt("/practice/p1");
    expect(await screen.findByText("Which could be the area of circle B?")).toBeInTheDocument();
    expect(screen.getByText(/No unused medium questions/)).toBeInTheDocument();
    await userEvent.click(screen.getByRole("button", { name: /need a hint/i }));
    expect(await screen.findByText("Area = πr².")).toBeInTheDocument();
    await userEvent.click(screen.getByText("About 2,700 in²"));
    await userEvent.click(screen.getByRole("button", { name: /submit answer/i }));
    expect(await screen.findByText(/You're improving!/)).toBeInTheDocument();
    expect(screen.getByText(/Next question: hard/)).toBeInTheDocument();
    const answer = calls.find((c) => c.path === "/api/v2/practice/p1/answer")!;
    expect(answer.body).toEqual({ item_id: 178083, choice: "2", reveal: false });
  });
});

describe("markdown", () => {
  it("renders the notes subset and never injects HTML", () => {
    const { container } = render(<Markdown source={"### Key idea\nUse **ratios**.\n\n- one\n- two\n\n<img src=x onerror=alert(1)>"} />);
    expect(screen.getByText("Key idea").tagName).toBe("H4");
    expect(screen.getByText("ratios").tagName).toBe("STRONG");
    expect(container.querySelectorAll("li")).toHaveLength(2);
    expect(container.querySelector("img")).toBeNull();
    expect(container.textContent).toContain("<img src=x onerror=alert(1)>");
  });
});
