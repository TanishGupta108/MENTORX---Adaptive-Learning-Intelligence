/** Types and calls for the MENTORX tutor API (/api/v2). Answer keys never appear here. */
import { api } from "./client";

export type Status = "likely_strength" | "developing" | "potential_weakness" | "needs_assessment";
export type Evidence = "none" | "limited" | "moderate" | "strong";
export type Mode = "foundation" | "guided" | "independent" | "advanced";
export type Difficulty = "easy" | "medium" | "hard" | "unrated";
export type GoalType = "assess_overall" | "improve_weak" | "learn_topic";
export type GoalKind = "strengthen_skills" | "weekly_practice" | "master_skill";
export type AnswerType = "numeric" | "multiple_choice" | "check_all" | "algebraic" | "numeric_expression" | "exact_fraction" | "exact_match";
export const CHOICE_TYPES: AnswerType[] = ["multiple_choice", "check_all"];

export type ModelInfo = {
  available: boolean;
  name: string | null;
  display_name: string | null;
  test_auc: number | null;
  test_accuracy: number | null;
  parameters: number | null;
  reason: string | null;
};

export type Pace = "more_support" | "balanced" | "challenge";

/** Observed mastery rule (single-skill answers only). `to_go` = more correct answers needed. */
export type Mastery = { mastered: boolean; to_go: number | null; stuck: boolean; progress_hint: string | null };

export type SubjectInfo = {
  code: string;
  name: string;
  description: string;
  n_skills: number;
  n_questions: number;
  enrolled: boolean;
  diagnostic_completed: boolean;
  current: boolean;
  has_model: boolean;
  grades: boolean;
  attribution: string;
  notice: string | null;
};

export type SkillSummary = {
  id: number;
  code: string;
  name: string;
  grade: number | null;
  domain_code: string;
  domain_name: string;
  n_items: number;
  status: Status;
  status_label: string;
  evidence: Evidence;
  attempts: number;
  correct: number;
  observed_accuracy: number | null;
  recent_accuracy: number | null;
  hints_used: number;
  predicted_p: number | null;
  mode: Mode;
  mode_label: string;
  mode_is_override: boolean;
  completed: boolean;
  reassessed_accuracy: number | null;
  revision_due_at: string | null;
  last_practiced_at: string | null;
  mastery?: Mastery;
  review_due?: boolean;
};

export type Goal = {
  id: number;
  kind: GoalKind;
  label: string;
  target: number;
  value: number;
  achieved: boolean;
  skill_id: number | null;
};

export type Profile = {
  full_name: string;
  email: string;
  subject: string | null;
  subject_code?: string | null;
  grade?: number | null;
  subjects_enrolled?: string[];
  onboarded: boolean;
  diagnostic_completed: boolean;
  goal_type: GoalType | null;
  focus_skill: { id: number; name: string; code: string } | null;
  pace_preference: Pace;
  hints_enabled: boolean;
  daily_goal: number;
  goal: Goal | null;
  is_admin: boolean;
};

export type Catalog = {
  subject: { code: string; name: string; description: string; attribution?: string; notice?: string | null };
  n_skills: number;
  n_questions: number;
  domains: { code: string; name: string; skills: SkillSummary[] }[];
  model: ModelInfo;
};

export type Recommendation = {
  priority: number;
  reason_code: string;
  reason: string;
  activities: string[];
  resources_available: number;
  skill: SkillSummary;
};

export type Activity = {
  kind: string;
  title: string;
  detail: string;
  at: string;
  id: string;
  skill_id: number | null;
};

export type DayPoint = { date: string; attempts: number; correct: number; accuracy: number | null };

export type Dashboard = {
  name: string;
  diagnostic_completed: boolean;
  goal_type: GoalType | null;
  continue: Recommendation | null;
  overview: {
    skills_assessed: number;
    likely_strengths: number;
    needs_improvement: number;
    practice_sessions: number;
    questions_this_week: number;
    skills_available: number;
  };
  recommendations: Recommendation[];
  skill_map: Partial<Record<Status, SkillSummary[]>>;
  unassessed_count: number;
  revision_due: SkillSummary[];
  progress: DayPoint[];
  activity: Activity[];
  goal: Goal | null;
  streak: Streak;
  mixed: MixedInfo;
  model: ModelInfo;
};

/** One thing to do next, with everything needed to start it in one click (GET /home). */
export type StartSpec =
  | { endpoint: "practice"; skill_id: number; guided: boolean }
  | { endpoint: "assessment"; kind: "diagnostic" | "skill_check" | "reassessment"; skill_id: number | null }
  | { endpoint: "review" }
  | { endpoint: "resume_practice"; session_id: string }
  | { endpoint: "resume_assessment"; assessment_id: string }
  | { endpoint: "learn"; skill_id: number };

export type NextAction = {
  kind: "diagnostic" | "skill_check" | "practice" | "review" | "reassess" | "resume" | "learn" | "prerequisite";
  skill: { id: number; name: string; code: string } | null;
  title: string;
  reason: string;
  progress_hint: string | null;
  start: StartSpec;
};

export type Home = {
  name: string;
  subject: { code: string; name: string };
  diagnostic_completed: boolean;
  next: NextAction | null;
  up_next: NextAction[];
  reviews_due: { count: number; skills: { id: number; name: string }[] };
  resume: NextAction | null;
  pace_suggestion: { suggested: "more_support" | "challenge"; message: string } | null;
  diagnosis_summary: { strong: number; getting_there: number; needs_practice: number; not_tried: number; show: boolean };
  streak: Streak;
  goal: Goal | null;
  mixed: MixedInfo;
};

export type Streak = { current: number; longest: number; today: number; daily_goal: number; goal_met: boolean; active_today: boolean };
export type MixedInfo = { available: boolean; skills_practised: number; needs_skills: number; questions: number; answered: number; accuracy: number | null };

export type TraceStep = {
  position: number;
  skill_id: number | null;
  skill: string | null;
  kind: "start" | "model" | "prerequisite";
  reason: string;
  predicted_p: number | null;
  correct: boolean | null;
};

export type Diagnosis = {
  assessment: { id: string; kind: string; correct: number; answered: number; completed_at: string } | null;
  headline: string;
  counts: Record<Status, number>;
  assessed: SkillSummary[];
  model_estimates_for_unassessed: SkillSummary[];
  recommendations: Recommendation[];
  selection_trace: TraceStep[];
  model: ModelInfo;
};

export type Resource = {
  id: number;
  skill_id: number | null;
  skill_name: string | null;
  skill_code: string | null;
  kind: "notes" | "worked_example" | "standard" | "video" | "article" | "practice_tip";
  title: string;
  description: string;
  url: string | null;
  content_md: string | null;
  minutes: number;
  source_label: string;
  is_original: boolean;
  completed: boolean;
};

export type CorrectAnswer =
  | { type: "numeric"; values: string[] }
  | { type: "text"; values: string[] }
  | { type: "multiple_choice" | "check_all"; option_ids: string[]; options_html: string[] };

export type Mistake = {
  interaction_id: number;
  item_id: number;
  body_html: string;
  answer_type: AnswerType;
  options: { id: string; html: string }[];
  your_response: { value?: string; choice?: string; choices?: string[]; revealed?: boolean };
  correct_answer: CorrectAnswer;
  revealed: boolean;
  at: string;
  media?: MapMedia | null;
};

export type ReassessmentResult = {
  accuracy: number;
  correct: number;
  answered: number;
  initial_accuracy?: number | null;
  initial_attempts?: number;
  reassessment_accuracy?: number;
  outcome?: "improved" | "progressing" | "not_improved";
  predicted_before?: number | null;
  predicted_after?: number | null;
  completed?: boolean;
  revision_due_at?: string | null;
  status_counts?: Partial<Record<Status, number>>;
};

export type MapName = "europe" | "africa" | "samerica" | "namerica" | "oceania" | "us";
export type MapRegion = { label: string | null; d: string; anchor: [number, number]; shape: "area" | "line" | "point" };
/** Geography items: the regions to draw over a static base map (no place codes, no answer). */
export type MapMedia = { kind: "map"; map: MapName; regions: MapRegion[] };
/** Static outline file served by the frontend at /maps/<map>.json. */
export type BaseMap = { viewBox: string; land: string[] };

export type NextActivityAction = "skill_check" | "foundation" | "reassess" | "practice" | "review" | "prerequisite" | "learn";

export type SkillDetail = SkillSummary & {
  description: string;
  standard_url: string | null;
  difficulty_counts: Partial<Record<Difficulty, number>>;
  fresh_questions: number;
  /** Unseen questions a fresh check needs (the server's rule). */
  check_min_fresh?: number;
  resources: Resource[];
  resources_done: number;
  prerequisites: (SkillSummary & { source: string })[];
  leads_to: SkillSummary[];
  recent_mistakes: Mistake[];
  last_reassessment: { id: string; result: ReassessmentResult; completed_at: string } | null;
  support_plan: {
    message: string;
    steps: string[];
    prerequisites_to_check: SkillSummary[];
    no_prerequisite_note: string | null;
  } | null;
  next_activity: { action: NextActivityAction; label: string; skill_id?: number };
  subject?: { code: string; name: string };
  attribution?: string | null;
  notice?: string | null;
  mode_policy: { start: Difficulty; target_p: number; hints: string };
  reassessment_length: number;
};

export type Question = {
  item_id: number;
  skill: { id: number; code: string; name: string };
  skills?: { id: number; code: string; name: string }[];
  mixed?: boolean;
  body_html: string;
  answer_type: AnswerType;
  input_hint?: string | null;
  options: { id: string; html: string }[];
  difficulty: Difficulty;
  position: number | null;
  total: number | null;
  // why this question was chosen (practice, and the adaptive diagnostic)
  selection?: { requested?: string; served?: string; how: string; technical?: string | null; fallback_note?: string | null } | null;
  media?: MapMedia | null;
  mode?: Mode;
  hint_used?: boolean;
};

export type AnswerBody = { item_id: number; value?: string; choice?: string; choices?: string[] };

export type Assessment = {
  id: string;
  kind: "diagnostic" | "skill_check" | "reassessment";
  status: "active" | "completed" | "abandoned";
  skill: { id: number; name: string; code: string } | null;
  answered: number;
  correct: number;
  total: number;
  started_at: string;
  completed_at: string | null;
  result: ReassessmentResult | null;
};

export type AssessmentAnswer = {
  interaction_id: number;
  correct: boolean;
  correct_answer: CorrectAnswer;
  message: string;
  answered: number;
  total: number;
  complete: boolean;
  result: ReassessmentResult | null;
};

export type PracticeKind = "skill" | "mixed" | "review";
export type PracticeStart = { id: string; kind: PracticeKind; skill_id: number | null; mode: Mode; guided: boolean; difficulty: Difficulty; total: number; answered: number };

export type PracticeSummary = {
  accuracy: number;
  correct: number;
  answered: number;
  skill_accuracy: number | null;
  skill_attempts: number;
  predicted_p: number | null;
  mode: Mode | null;
  mixed?: boolean;
  review?: boolean;
  next: { action: "reassess" | "foundation" | "practice" | "mixed" | "review" | "prerequisite" | "learn" | "home"; label: string; why: string; skill_id?: number };
};

export type PracticeAnswer = {
  interaction_id: number;
  correct: boolean;
  hint_used: boolean;
  revealed: boolean;
  correct_answer: CorrectAnswer;
  message: string;
  difficulty_before: Difficulty;
  difficulty_next: Difficulty;
  difficulty_change: "up" | "down" | null;
  answered: number;
  total: number;
  complete: boolean;
  summary: PracticeSummary | null;
  early_stop?: null | { reason: "mastered" | "stuck" | "enough" | "completed"; message: string };
};

export type PathStep = {
  skill: SkillSummary;
  path_status: string;
  reason: string | null;
  next_activity: string | null;
  resources_done: number;
  resources_total: number;
};

export type Analytics = {
  totals: {
    questions: number;
    correct: number;
    observed_accuracy: number | null;
    assessment_accuracy: number | null;
    practice_accuracy: number | null;
    hint_rate: number | null;
    mixed_accuracy: number | null;
    assessments: number;
    practice_sessions: number;
    resources_completed: number;
    resources_total: number;
  };
  daily: DayPoint[];
  skills: SkillSummary[];
  assessments: { id: string; kind: string; skill: string | null; accuracy: number; correct: number; answered: number; completed_at: string; outcome: string | null }[];
  practice: { id: string; skill: string; kind: PracticeKind; mode: Mode; accuracy: number; answered: number; started_at: string }[];
  activity: Activity[];
  model: ModelInfo;
};

export type Hint = { kind: string; text: string; source: string; label?: string; note?: string; ai_failed?: boolean };
export type AiStatus = { enabled: boolean; model: string | null; daily_limit: number; used_today: number; label: string; key_ok?: boolean | null };
export type AiTest = { ok: boolean; model: string | null; latency_ms: number | null; error_code: string | null; message: string };

/** AI calls can take a while on free models; the server gives up after ~50 s. */
export const AI_TIMEOUT_MS = 65_000;
export type AiText = { kind: "explanation" | "hint"; content: string; model: string; cached: boolean; label: string };

const V2 = "/api/v2";

export type OnboardBody = {
  goal_type: GoalType;
  focus_skill_id?: number | null;
  goal_kind: GoalKind;
  goal_target?: number | null;
  subject_code?: string;
  grade?: number | null;
  pace_preference?: Pace;
};

export const tutor = {
  profile: () => api.get<Profile>(`${V2}/profile`),
  onboard: (body: OnboardBody) => api.post<Profile>(`${V2}/onboarding`, body),
  updateProfile: (body: Partial<{ pace_preference: Pace; hints_enabled: boolean; goal_type: GoalType; focus_skill_id: number | null; daily_goal: number; grade: number | null }>) =>
    api.patch<Profile>(`${V2}/profile`, body),
  subjects: () => api.get<SubjectInfo[]>(`${V2}/subjects`),
  setSubject: (code: string) => api.put<Profile>(`${V2}/profile/subject`, { code }),
  home: () => api.get<Home>(`${V2}/home`),
  paceSuggestion: (accept: boolean) => api.post<Profile>(`${V2}/home/pace-suggestion`, { accept }),
  setGoal: (body: { kind: GoalKind; target?: number | null; skill_id?: number | null }) => api.put<Goal>(`${V2}/goal`, body),
  catalog: () => api.get<Catalog>(`${V2}/subject`),
  diagnosis: () => api.get<Diagnosis>(`${V2}/diagnosis`),
  dashboard: () => api.get<Dashboard>(`${V2}/dashboard`),
  path: () => api.get<{ steps: PathStep[]; completed: PathStep[] }>(`${V2}/path`),
  analytics: () => api.get<Analytics>(`${V2}/analytics`),
  skill: (id: number) => api.get<SkillDetail>(`${V2}/skills/${id}`),
  setMode: (id: number, mode: Mode | null) => api.patch<SkillDetail>(`${V2}/skills/${id}/mode`, { mode }),
  startAssessment: (kind: Assessment["kind"], skill_id?: number) => api.post<Assessment>(`${V2}/assessments`, { kind, skill_id }),
  assessment: (id: string) => api.get<Assessment>(`${V2}/assessments/${id}`),
  assessmentNext: (id: string) => api.get<Question>(`${V2}/assessments/${id}/next`),
  assessmentAnswer: (id: string, body: AnswerBody) => api.post<AssessmentAnswer>(`${V2}/assessments/${id}/answer`, body),
  startPractice: (skill_id: number, guided: boolean) => api.post<PracticeStart>(`${V2}/practice`, { skill_id, guided }),
  startMixed: () => api.post<PracticeStart>(`${V2}/practice`, { kind: "mixed" }),
  startReview: () => api.post<PracticeStart>(`${V2}/practice`, { kind: "review" }),
  practiceNext: (id: string) => api.get<Question>(`${V2}/practice/${id}/next`),
  practiceHint: (id: string, ai = false) =>
    api.post<Hint>(`${V2}/practice/${id}/hint${ai ? "?ai=true" : ""}`, undefined, ai ? { timeoutMs: AI_TIMEOUT_MS } : undefined),
  aiStatus: () => api.get<AiStatus>(`${V2}/ai/status`),
  aiExplain: (interaction_id: number) => api.post<AiText>(`${V2}/ai/explain`, { interaction_id }, { timeoutMs: AI_TIMEOUT_MS }),
  practiceAnswer: (id: string, body: AnswerBody & { reveal?: boolean }) => api.post<PracticeAnswer>(`${V2}/practice/${id}/answer`, body),
  practiceEnd: (id: string) => api.post<{ status: string; summary: PracticeSummary | null }>(`${V2}/practice/${id}/end`),
  resources: (params: { kind?: string; q?: string } = {}) => {
    const qs = new URLSearchParams(Object.entries(params).filter(([, v]) => v) as [string, string][]).toString();
    return api.get<Resource[]>(`${V2}/resources${qs ? `?${qs}` : ""}`);
  },
  completeResource: (id: number, completed: boolean) => api.post<{ id: number; completed: boolean }>(`${V2}/resources/${id}/complete`, { completed }),
};

export type AdminSkill = { id: number; code: string; name: string; description: string; domain_name: string; n_items: number; is_available: boolean };
export type AdminItem = { id: number; preview: string; answer_type: string; difficulty: Difficulty; success_rate: number | null; train_attempts: number; exclusion_reason: string | null; is_active: boolean };
export type Metrics = { n: number; observed_rate: number | null; mean_predicted: number | null; auc: number | null; log_loss: number | null; brier: number | null; accuracy: number | null };
export type ModelMonitor = {
  model: ModelInfo;
  overall: Metrics;
  by_context: Record<string, Metrics>;
  calibration: { bin: string; mean_predicted: number; observed_rate: number; n: number }[];
  min_for_metrics: number;
};
export type AdminAiText = { id: number; item_id: number; question: string; kind: "explanation" | "hint"; answer_sig: string; content: string; model: string; status: "ok" | "hidden"; latency_ms: number | null; created_at: string };
export type AdminPrereq = { skill_id: number; skill: string; prerequisite_id: number; prerequisite: string; source: string };

const subjectQs = (subject?: string, sep = "?") => (subject ? `${sep}subject=${encodeURIComponent(subject)}` : "");

export const adminApi = {
  model: (subject?: string) => api.get<ModelMonitor>(`${V2}/admin/model${subjectQs(subject)}`),
  testAi: () => api.post<AiTest>(`${V2}/admin/ai/test`, undefined, { timeoutMs: AI_TIMEOUT_MS }),
  aiTexts: () => api.get<AdminAiText[]>(`${V2}/admin/ai`),
  setAiText: (id: number, status: "ok" | "hidden") => api.patch<{ id: number; status: string }>(`${V2}/admin/ai/${id}`, { status }),
  overview: (subject?: string) => api.get<{ skills: number; available_skills: number; items: number; usable_items: number; usable_mixed_items: number; disabled_by_admin: number; exclusions: { reason: string; count: number }[]; resources: number; prerequisites: number }>(`${V2}/admin/overview${subjectQs(subject)}`),
  skills: (q?: string, subject?: string) =>
    api.get<AdminSkill[]>(`${V2}/admin/skills${q ? `?q=${encodeURIComponent(q)}` : ""}${subjectQs(subject, q ? "&" : "?")}`),
  updateSkill: (id: number, description: string) => api.patch<{ id: number }>(`${V2}/admin/skills/${id}`, { description }),
  items: (skillId: number) => api.get<AdminItem[]>(`${V2}/admin/skills/${skillId}/items`),
  setItem: (id: number, is_active: boolean) => api.patch<{ id: number }>(`${V2}/admin/items/${id}`, { is_active }),
  resources: (skillId?: number) => api.get<(Resource & { is_active: boolean })[]>(`${V2}/admin/resources${skillId ? `?skill_id=${skillId}` : ""}`),
  createResource: (body: Record<string, unknown>) => api.post<Resource>(`${V2}/admin/resources`, body),
  deleteResource: (id: number) => api.delete<void>(`${V2}/admin/resources/${id}`),
  prerequisites: () => api.get<AdminPrereq[]>(`${V2}/admin/prerequisites`),
  addPrerequisite: (skill_id: number, prerequisite_id: number) => api.post<unknown>(`${V2}/admin/prerequisites`, { skill_id, prerequisite_id }),
  removePrerequisite: (skill_id: number, prerequisite_id: number) => api.delete<void>(`${V2}/admin/prerequisites/${skill_id}/${prerequisite_id}`),
};
