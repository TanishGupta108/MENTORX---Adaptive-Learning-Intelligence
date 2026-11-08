import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter, Route, Routes } from "react-router";
import { afterEach, describe, expect, it, vi } from "vitest";
import { setAccessToken } from "../api/client";
import { mockApi } from "../test/mockApi";
import { SessionPage } from "./Session";

afterEach(() => {
  vi.unstubAllGlobals();
  setAccessToken(null);
});

const session = (type: string, answered = 0, target = 2) => ({
  id: "s1",
  subject: "ML",
  type,
  status: "active",
  focus_concept: null,
  answered,
  target,
  started_at: "2026-11-08T10:00:00Z",
  ended_at: null,
  correct: null,
  changes: null,
});

const question = (id: number, position: number) => ({
  session_id: "s1",
  question_id: id,
  concept: "ml.knn",
  concept_name: "k-Nearest Neighbours",
  stem: `Question ${id} stem`,
  options: [
    { key: "A", text: "first" },
    { key: "B", text: "second" },
    { key: "C", text: "third" },
    { key: "D", text: "fourth" },
  ],
  allow_dont_know: true,
  position,
  total: 2,
});

function renderSession() {
  setAccessToken("tok");
  return render(
    <MemoryRouter initialEntries={["/session/s1"]}>
      <Routes>
        <Route path="/session/:id" element={<SessionPage />} />
      </Routes>
    </MemoryRouter>,
  );
}

describe("session player", () => {
  it("practice: shows feedback, explanation and the mastery change", async () => {
    let served = 0;
    const calls = mockApi({
      "GET /sessions/s1": { body: session("practice") },
      "POST /sessions/s1/next": () => ({ body: question(10 + served++, served) }),
      "POST /sessions/s1/answer": {
        body: {
          feedback: { correct: false, correct_key: "C", explanation: "Because k controls smoothing." },
          mastery: { concept: "ml.knn", before: 0.5, after: 0.46 },
          answered: 1,
          target: 2,
          session_complete: false,
          summary: null,
          changes: null,
        },
      },
      "GET /subjects/ML/concepts": { body: [] },
    });
    renderSession();
    expect(await screen.findByText("Question 10 stem")).toBeInTheDocument();
    const submit = screen.getByRole("button", { name: "Check answer" });
    expect(submit).toBeDisabled();

    await userEvent.click(screen.getByLabelText(/B\.\s*second/));
    await userEvent.click(submit);

    expect(await screen.findByText("Not quite")).toBeInTheDocument();
    expect(screen.getByText(/You chose B/)).toHaveTextContent("The answer is C: third");
    expect(screen.getByText("Because k controls smoothing.")).toBeInTheDocument();
    expect(screen.getByText(/50%/)).toBeInTheDocument();
    expect(screen.getByText("(−4 pts)")).toBeInTheDocument();
    expect(calls.find((c) => c.path === "/sessions/s1/answer")!.body).toEqual({
      question_id: 10,
      selected_key: "B",
    });

    await userEvent.click(screen.getByRole("button", { name: "Next question" }));
    expect(await screen.findByText("Question 11 stem")).toBeInTheDocument();
  });

  it("diagnostic: no feedback between questions; 'I don't know yet' sends null", async () => {
    let served = 0;
    const calls = mockApi({
      "GET /sessions/s1": { body: session("diagnostic") },
      "POST /sessions/s1/next": () => ({ body: question(20 + served++, served) }),
      "POST /sessions/s1/answer": {
        body: {
          feedback: null,
          mastery: null,
          answered: 1,
          target: 2,
          session_complete: false,
          summary: null,
          changes: null,
        },
      },
    });
    renderSession();
    expect(await screen.findByText("Question 20 stem")).toBeInTheDocument();
    await userEvent.click(screen.getByRole("button", { name: "I don't know yet" }));
    expect(await screen.findByText("Question 21 stem")).toBeInTheDocument();
    expect(screen.queryByText(/The answer is/)).not.toBeInTheDocument();
    expect(calls.find((c) => c.path === "/sessions/s1/answer")!.body).toEqual({
      question_id: 20,
      selected_key: null,
    });
  });

  it("keyboard: pressing 3 selects option C", async () => {
    mockApi({
      "GET /sessions/s1": { body: session("practice") },
      "POST /sessions/s1/next": { body: question(30, 1) },
    });
    renderSession();
    await screen.findByText("Question 30 stem");
    await userEvent.keyboard("3");
    expect(screen.getByLabelText(/C\.\s*third/)).toBeChecked();
  });

  it("completed diagnostic shows strongest and weakest concepts", async () => {
    let done = false;
    mockApi({
      "GET /sessions/s1": () => ({
        body: done ? { ...session("diagnostic", 2), status: "completed" } : session("diagnostic", 1),
      }),
      "POST /sessions/s1/next": { body: question(40, 2) },
      "POST /sessions/s1/answer": () => {
        done = true;
        return {
          body: {
            feedback: null,
            mastery: null,
            answered: 2,
            target: 2,
            session_complete: true,
            summary: {
              strongest: [{ concept: "ml.knn", name: "k-NN", mastery: 0.81 }],
              weakest: [{ concept: "ml.svm", name: "SVMs", mastery: 0.33 }],
            },
            changes: null,
          },
        };
      },
      "GET /subjects/ML/concepts": { body: [] },
    });
    renderSession();
    await screen.findByText("Question 40 stem");
    await userEvent.click(screen.getByLabelText(/A\.\s*first/));
    await userEvent.click(screen.getByRole("button", { name: "Next" }));
    expect(await screen.findByText("Session complete")).toBeInTheDocument();
    expect(screen.getByText("k-NN")).toBeInTheDocument();
    expect(screen.getByText("33%")).toBeInTheDocument();
  });
});
