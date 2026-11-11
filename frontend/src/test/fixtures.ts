import type { Dashboard, Diagnosis, Profile, Question, SkillSummary } from "../api/tutor";

export const skill = (over: Partial<SkillSummary> = {}): SkillSummary => ({
  id: 222,
  code: "7.G.B.4",
  name: "Solve Problems Involving Area & Circumference of Circles",
  grade: 7,
  domain_code: "G",
  domain_name: "Geometry",
  n_items: 41,
  status: "potential_weakness",
  status_label: "Potential Weakness",
  evidence: "limited",
  attempts: 2,
  correct: 0,
  observed_accuracy: 0,
  recent_accuracy: 0,
  hints_used: 0,
  predicted_p: 0.38,
  mode: "foundation",
  mode_label: "Foundation",
  mode_is_override: false,
  completed: false,
  reassessed_accuracy: null,
  revision_due_at: null,
  last_practiced_at: null,
  ...over,
});

export const model = { available: true, name: "dkt_q", display_name: "DKT-Q (LSTM + question embeddings)", test_auc: 0.8117, test_accuracy: 0.7494, parameters: 1580026, reason: null };

export const profile: Profile = {
  full_name: "Asha Rao",
  email: "asha@example.com",
  subject: "Mathematics",
  onboarded: true,
  diagnostic_completed: true,
  goal_type: "assess_overall",
  focus_skill: null,
  pace_preference: "balanced",
  hints_enabled: true,
  goal: { id: 1, kind: "strengthen_skills", label: "Build 3 likely strengths", target: 3, value: 1, achieved: false, skill_id: null },
  is_admin: false,
};

const rec = {
  priority: 1,
  reason_code: "weakness",
  reason: "Circles is recommended because your answers so far (0 of 2 correct, 0%) suggest you may benefit from additional practice.",
  activities: ["Read the concept notes", "Study the worked example"],
  resources_available: 3,
  skill: skill(),
};

export const dashboard: Dashboard = {
  name: "Asha",
  diagnostic_completed: true,
  goal_type: "assess_overall",
  continue: rec,
  overview: { skills_assessed: 10, likely_strengths: 3, needs_improvement: 7, practice_sessions: 2, questions_this_week: 26, skills_available: 90 },
  recommendations: [rec],
  skill_map: { potential_weakness: [skill()], developing: [], likely_strength: [skill({ id: 130, name: "Solve Unit Rate Problems", status: "likely_strength" })] },
  unassessed_count: 80,
  revision_due: [],
  progress: [{ date: "2026-11-10", attempts: 12, correct: 8, accuracy: 0.66 }],
  activity: [{ kind: "diagnostic", title: "Diagnostic assessment", detail: "6/10 correct", at: "2026-11-10T10:00:00Z", id: "a1", skill_id: null }],
  goal: profile.goal,
  model,
};

export const diagnosis: Diagnosis = {
  assessment: { id: "a1", kind: "diagnostic", correct: 6, answered: 10, completed_at: "2026-11-10T10:00:00Z" },
  headline: "Your recent performance suggests that Circles may need additional practice.",
  counts: { likely_strength: 3, developing: 5, potential_weakness: 2, needs_assessment: 80 },
  assessed: [skill(), skill({ id: 130, name: "Solve Unit Rate Problems", status: "likely_strength", correct: 2, attempts: 2, observed_accuracy: 1, predicted_p: 0.81 })],
  model_estimates_for_unassessed: [skill({ id: 217, name: "Solve 2-Step Equations", status: "needs_assessment", evidence: "none", attempts: 0, correct: 0, observed_accuracy: null, predicted_p: 0.41 })],
  recommendations: [rec],
  model,
};

export const numericQuestion: Question = {
  item_id: 448752,
  skill: { id: 222, code: "7.G.B.4", name: "Circles" },
  body_html: '<p>Circle A has area 500 in<sup>2</sup>. Estimate the area of circle B.</p><p><span class="answer-blank">?</span></p>',
  answer_type: "numeric",
  options: [],
  difficulty: "medium",
  position: 1,
  total: 10,
};

export const choiceQuestion: Question = {
  item_id: 178083,
  skill: { id: 222, code: "7.G.B.4", name: "Circles" },
  body_html: "<p>Which could be the area of circle B?</p>",
  answer_type: "multiple_choice",
  options: [
    { id: "0", html: "About 100 in²" },
    { id: "1", html: "About 900 in²" },
    { id: "2", html: "About 2,700 in²" },
  ],
  difficulty: "hard",
  position: 2,
  total: 8,
  selection: { requested: "medium", served: "hard", how: "Chosen by the model: predicted success 61%, close to the 70% target for guided mode.", fallback_note: "No unused medium questions are left in this skill, so this one is hard." },
  mode: "guided",
  hint_used: false,
};
