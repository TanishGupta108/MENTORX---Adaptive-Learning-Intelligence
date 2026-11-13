/** Component tests: one-click launching, map questions and the AI status cache. */
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter, Route, Routes, useLocation } from "react-router";
import { afterEach, describe, expect, it, vi } from "vitest";
import type { Launch } from "./StartAction";
import { StartButton } from "./StartAction";
import { QuestionView } from "./QuestionView";
import { resetMapCache } from "./MapQuestion";
import { AiExplain, resetAiStatus } from "./AiTutor";
import { setAccessToken } from "../api/client";
import { mockApi } from "../test/mockApi";
import { baseMap, locateQuestion } from "../test/fixtures";

afterEach(() => {
  vi.unstubAllGlobals();
  setAccessToken(null);
  resetAiStatus();
  resetMapCache();
});

function Where() {
  const l = useLocation();
  return <p data-testid="where">{l.pathname + l.search}</p>;
}

function renderStart(spec: Launch) {
  return render(
    <MemoryRouter initialEntries={["/"]}>
      <Routes>
        <Route path="/" element={<StartButton action={spec} />} />
        <Route path="*" element={<Where />} />
      </Routes>
    </MemoryRouter>,
  );
}

const practiceStart = { id: "p1", kind: "skill", skill_id: 5, mode: "guided", guided: true, difficulty: "easy", total: 8, answered: 0 };
const assessmentStart = { id: "a1", kind: "skill_check", status: "active", skill: null, answered: 0, correct: 0, total: 5, started_at: "", completed_at: null, result: null };

describe("StartButton", () => {
  const cases: { name: string; spec: Launch; call?: [string, unknown]; to: string }[] = [
    { name: "practice", spec: { endpoint: "practice", skill_id: 5, guided: true }, call: ["POST /api/v2/practice", { skill_id: 5, guided: true }], to: "/practice/p1" },
    { name: "assessment", spec: { endpoint: "assessment", kind: "skill_check", skill_id: 5 }, call: ["POST /api/v2/assessments", { kind: "skill_check", skill_id: 5 }], to: "/assess/a1" },
    { name: "review", spec: { endpoint: "review" }, call: ["POST /api/v2/practice", { kind: "review" }], to: "/practice/p1" },
    { name: "mixed", spec: { endpoint: "mixed" }, call: ["POST /api/v2/practice", { kind: "mixed" }], to: "/practice/p1" },
    { name: "resume practice", spec: { endpoint: "resume_practice", session_id: "s7" }, to: "/practice/s7" },
    { name: "resume assessment", spec: { endpoint: "resume_assessment", assessment_id: "a7" }, to: "/assess/a7" },
    { name: "learn", spec: { endpoint: "learn", skill_id: 5 }, to: "/skills/5?tab=learn" },
  ];
  for (const c of cases) {
    it(`routes ${c.name}`, async () => {
      const calls = mockApi({ "POST /api/v2/practice": { body: practiceStart }, "POST /api/v2/assessments": { body: assessmentStart } });
      renderStart(c.spec);
      await userEvent.click(screen.getByRole("button", { name: /start/i }));
      expect(await screen.findByTestId("where")).toHaveTextContent(c.to);
      if (c.call) {
        const [key, body] = c.call;
        expect(calls.map((x) => `${x.method} ${x.path}`)).toEqual([key]);
        expect(calls[0]!.body).toEqual(body);
      } else {
        expect(calls).toHaveLength(0);
      }
    });
  }

  it("shows the server's message when nothing is due", async () => {
    mockApi({ "POST /api/v2/practice": { status: 409, body: { error: { code: "nothing_due", message: "Nothing is due for review right now." } } } });
    renderStart({ endpoint: "review" });
    await userEvent.click(screen.getByRole("button", { name: /start/i }));
    expect(await screen.findByRole("alert")).toHaveTextContent("Nothing is due for review right now.");
  });
});

describe("MapQuestion", () => {
  it("draws the lettered regions and a tap on region B selects option B", async () => {
    const calls = mockApi({ "GET /maps/europe.json": { body: baseMap } });
    const onSubmit = vi.fn();
    const { container, rerender } = render(<QuestionView question={locateQuestion} onSubmit={onSubmit} submitting={false} locked={false} />);
    expect(await screen.findByRole("img", { name: /map of europe with 4 lettered places/i })).toBeInTheDocument();
    expect(calls.map((c) => c.path)).toEqual(["/maps/europe.json"]);
    for (const l of ["A", "B", "C", "D"]) expect(container.querySelector(`[data-region="${l}"]`)).not.toBeNull();
    expect(screen.getByText(/do not show official international boundaries/)).toBeInTheDocument();

    // tapping a letter badge works too
    await userEvent.click(container.querySelector('[data-badge="D"] circle')!);
    expect(screen.getByRole("radio", { name: "D" })).toBeChecked();
    await userEvent.click(container.querySelector('[data-region="B"] path')!);
    expect(screen.getByRole("radio", { name: "B" })).toBeChecked();
    await userEvent.click(screen.getByRole("button", { name: /submit answer/i }));
    expect(onSubmit).toHaveBeenCalledWith({ item_id: locateQuestion.item_id, choice: "B" });

    // after the answer: the correct region turns green and the wrong pick red
    rerender(
      <QuestionView
        question={locateQuestion}
        onSubmit={onSubmit}
        submitting={false}
        locked
        feedback={{ correct: false, correct_answer: { type: "multiple_choice", option_ids: ["A"], options_html: ["A"] }, message: "Not quite." }}
      />,
    );
    expect(container.querySelector('[data-region="A"] path')!.getAttribute("class")).toContain("fill-strength");
    expect(container.querySelector('[data-region="B"] path')!.getAttribute("class")).toContain("fill-weakness");
    // the map is read-only once answered
    await userEvent.click(container.querySelector('[data-region="C"] circle')!);
    expect(screen.getByRole("radio", { name: "B" })).toBeChecked();
  });

  it("highlights one unlabelled region for 'name the place' questions", async () => {
    mockApi({ "GET /maps/europe.json": { body: baseMap } });
    const q = {
      ...locateQuestion,
      body_html: "<p>What is the name of the highlighted country?</p>",
      options: [
        { id: "0", html: "France" },
        { id: "1", html: "Spain" },
      ],
      media: { kind: "map" as const, map: "europe" as const, regions: [{ label: null, d: "M10 10L20 10L20 20Z", anchor: [15, 15] as [number, number], shape: "area" as const }] },
    };
    const { container } = render(<QuestionView question={q} onSubmit={vi.fn()} submitting={false} locked={false} />);
    expect(await screen.findByRole("img", { name: /one highlighted place/i })).toBeInTheDocument();
    expect(container.querySelector('[data-region="highlight"]')).not.toBeNull();
    expect(screen.getByRole("radio", { name: "France" })).toBeInTheDocument();
  });

  it("offers a retry when the map can't load", async () => {
    let n = 0;
    mockApi({ "GET /maps/europe.json": () => (n++ === 0 ? { status: 404 } : { body: baseMap }) });
    render(<QuestionView question={locateQuestion} onSubmit={vi.fn()} submitting={false} locked={false} />);
    await userEvent.click(await screen.findByRole("button", { name: /try again/i }));
    expect(await screen.findByRole("img", { name: /map of europe/i })).toBeInTheDocument();
  });
});

describe("AI status", () => {
  it("fetches the status again after a failure instead of hiding AI until reload", async () => {
    let n = 0;
    const calls = mockApi({
      "GET /api/v2/ai/status": () => (n++ === 0 ? { status: 502 } : { body: { enabled: true, model: "m", daily_limit: 40, used_today: 0, label: "AI-generated", key_ok: true } }),
    });
    const first = render(<AiExplain interactionId={1} />);
    await waitFor(() => expect(calls).toHaveLength(1));
    expect(screen.queryByRole("button", { name: /explain with ai/i })).not.toBeInTheDocument();
    first.unmount();
    render(<AiExplain interactionId={1} />);
    expect(await screen.findByRole("button", { name: /explain with ai/i })).toBeInTheDocument();
    expect(calls).toHaveLength(2);
  });

  it("hides AI buttons when the server says the key was rejected", async () => {
    const calls = mockApi({ "GET /api/v2/ai/status": { body: { enabled: true, model: "m", daily_limit: 40, used_today: 0, label: "", key_ok: false } } });
    render(<AiExplain interactionId={1} />);
    await waitFor(() => expect(calls).toHaveLength(1));
    expect(screen.queryByRole("button", { name: /explain with ai/i })).not.toBeInTheDocument();
  });
});
