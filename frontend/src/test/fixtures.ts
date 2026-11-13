import type { Diagnosis, Home, NextAction, Profile, Question, SkillDetail, SkillSummary, SubjectInfo } from "../api/tutor";

export const skill = (over: Partial<SkillSummary> = {}): SkillSummary => ({
  id: 222,
  code: "7.G.B.4",
  name: "Solve Problems Involving Area & Circumference of Circles",
  grade: 7,
  domain_code: "G",
  domain_name: "Geometry",
  n_items: 41,
  status: "potential_weakness",
  status_label: "Needs practice",
  evidence: "limited",
  attempts: 2,
  correct: 0,
  observed_accuracy: 0,
  recent_accuracy: 0,
  hints_used: 0,
  predicted_p: 0.38,
  mode: "foundation",
  mode_label: "Step by step",
  mode_is_override: false,
  completed: false,
  reassessed_accuracy: null,
  revision_due_at: null,
  last_practiced_at: null,
  mastery: { mastered: false, to_go: 5, stuck: false, progress_hint: "5 more correct to master" },
  review_due: false,
  ...over,
});

export const model = { available: true, name: "dkt_q", display_name: "DKT-Q (LSTM + question embeddings)", test_auc: 0.8117, test_accuracy: 0.7494, parameters: 1580026, reason: null };

export const profile: Profile = {
  full_name: "Asha Rao",
  email: "asha@example.com",
  subject: "Mathematics",
  subject_code: "MATH",
  grade: 7,
  subjects_enrolled: ["MATH"],
  onboarded: true,
  diagnostic_completed: true,
  goal_type: "assess_overall",
  focus_skill: null,
  pace_preference: "balanced",
  hints_enabled: true,
  daily_goal: 10,
  goal: { id: 1, kind: "weekly_practice", label: "Answer 30 questions a week", target: 30, value: 12, achieved: false, skill_id: null },
  is_admin: false,
};

export const subjectInfo = (over: Partial<SubjectInfo> = {}): SubjectInfo => ({
  code: "MATH",
  name: "Mathematics",
  description: "Grades 4-8, Common Core.",
  n_skills: 132,
  n_questions: 2942,
  enrolled: true,
  diagnostic_completed: true,
  current: true,
  has_model: true,
  grades: true,
  attribution: "Mathematics questions: FoundationalASSIST (ASSISTments), CC BY-NC 4.0.",
  notice: null,
  ...over,
});

export const geoInfo = subjectInfo({
  code: "GEO",
  name: "Geography",
  description: "Find countries, cities and rivers on the map.",
  n_skills: 15,
  n_questions: 900,
  enrolled: false,
  diagnostic_completed: false,
  current: false,
  grades: false,
  attribution: "Geography practice data © Adaptive Learning group, Masaryk University (slepemapy.cz), Open Database License 1.0.",
  notice: "Maps are simplified for practice and do not show official international boundaries.",
});

export const nextPractice: NextAction = {
  kind: "practice",
  skill: { id: 222, name: "Circles", code: "7.G.B.4" },
  title: "Practise Circles",
  reason: "Your last answers in Circles were mostly wrong, so a little more practice will help.",
  progress_hint: "5 more correct to master",
  start: { endpoint: "practice", skill_id: 222, guided: true },
};

export const home: Home = {
  name: "Asha",
  subject: { code: "MATH", name: "Mathematics" },
  diagnostic_completed: true,
  next: nextPractice,
  up_next: [
    {
      kind: "skill_check",
      skill: { id: 217, name: "Two-step equations", code: "7.EE.B.4a" },
      title: "Check Two-step equations",
      reason: "You haven't tried this skill yet, and it builds on what you know.",
      progress_hint: null,
      start: { endpoint: "assessment", kind: "skill_check", skill_id: 217 },
    },
  ],
  reviews_due: { count: 0, skills: [] },
  resume: null,
  pace_suggestion: null,
  diagnosis_summary: { strong: 3, getting_there: 5, needs_practice: 2, not_tried: 80, show: false },
  streak: { current: 3, longest: 5, today: 4, daily_goal: 10, goal_met: false, active_today: true },
  goal: profile.goal,
  mixed: { available: true, skills_practised: 10, needs_skills: 2, questions: 354, answered: 0, accuracy: null },
};

const rec = {
  priority: 1,
  reason_code: "weakness",
  reason: "Circles needs more practice.",
  activities: ["Read the notes"],
  resources_available: 3,
  skill: skill(),
};

export const diagnosis: Diagnosis = {
  assessment: { id: "a1", kind: "diagnostic", correct: 6, answered: 10, completed_at: "2026-11-10T10:00:00Z" },
  headline: "Your recent performance suggests that Circles may need additional practice.",
  counts: { likely_strength: 3, developing: 5, potential_weakness: 2, needs_assessment: 80 },
  assessed: [skill(), skill({ id: 130, name: "Solve Unit Rate Problems", status: "likely_strength", correct: 2, attempts: 2, observed_accuracy: 1, predicted_p: 0.81 })],
  model_estimates_for_unassessed: [skill({ id: 217, name: "Solve 2-Step Equations", status: "needs_assessment", evidence: "none", attempts: 0, correct: 0, observed_accuracy: null, predicted_p: 0.41 })],
  recommendations: [rec],
  selection_trace: [
    { position: 1, skill_id: 129, skill: "Create Tables to Compare Equivalent Ratios", kind: "start", reason: "A typical grade-6 question to start with.", predicted_p: null, correct: true },
    { position: 2, skill_id: 166, skill: "Write & Solve 1-Step Equations", kind: "prerequisite", reason: "You missed the 2-step question, so MENTORX checks one of its building blocks.", predicted_p: null, correct: false },
  ],
  model,
};

export const skillDetail: SkillDetail = {
  ...skill(),
  description: "Area and circumference of circles.",
  standard_url: null,
  difficulty_counts: { easy: 10, medium: 20, hard: 11 },
  fresh_questions: 39,
  resources: [
    { id: 1, skill_id: 222, skill_name: "Circles", skill_code: "7.G.B.4", kind: "notes", title: "Circles: key idea", description: "", url: null, content_md: "### Key idea\nArea = πr².", minutes: 4, source_label: "MENTORX", is_original: true, completed: false },
  ],
  resources_done: 0,
  prerequisites: [],
  leads_to: [],
  recent_mistakes: [
    {
      interaction_id: 55,
      item_id: 9,
      body_html: "<p>What is the area of a circle with radius 2?</p>",
      answer_type: "numeric",
      options: [],
      your_response: { value: "8" },
      correct_answer: { type: "numeric", values: ["4π"] },
      revealed: false,
      at: "2026-11-10T10:00:00Z",
    },
  ],
  last_reassessment: null,
  support_plan: null,
  next_activity: { action: "practice", label: "Practise this skill" },
  mode_policy: { start: "easy", target_p: 0.8, hints: "offered" },
  reassessment_length: 5,
  subject: { code: "MATH", name: "Mathematics" },
  attribution: null,
  notice: null,
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
  selection: {
    requested: "medium",
    served: "hard",
    how: "A harder question, because your last two were right.",
    technical: "Predicted success 61%, close to the 70% target for guided mode.",
    fallback_note: "No unused medium questions are left in this skill, so this one is hard.",
  },
  mode: "guided",
  hint_used: false,
};

export const baseMap = { viewBox: "0 0 200 100", land: ["M0 0L200 0L200 100L0 100Z"] };

export const locateQuestion: Question = {
  item_id: 100012345,
  skill: { id: 1000101, code: "GEO.EU.COUNTRY", name: "Europe: countries" },
  body_html: "<p>Where is France? Choose the letter on the map.</p>",
  answer_type: "multiple_choice",
  options: [
    { id: "A", html: "A" },
    { id: "B", html: "B" },
    { id: "C", html: "C" },
    { id: "D", html: "D" },
  ],
  difficulty: "medium",
  position: 1,
  total: 8,
  media: {
    kind: "map",
    map: "europe",
    regions: [
      { label: "A", d: "M10 10L20 10L20 20Z", anchor: [15, 15], shape: "area" },
      { label: "B", d: "M50 10L60 10L60 20Z", anchor: [55, 15], shape: "area" },
      { label: "C", d: "", anchor: [100, 50], shape: "point" },
      { label: "D", d: "M150 50L190 60", anchor: [170, 55], shape: "line" },
    ],
  },
};
