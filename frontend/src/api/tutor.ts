/** Types and calls for the MENTORX tutor API (/api/v2). Answer keys never appear here. */
import { api } from "./client";

export type Status = "likely_strength" | "developing" | "potential_weakness" | "needs_assessment";
export type Evidence = "none" | "limited" | "moderate" | "strong";
export type Mode = "foundation" | "guided" | "independent" | "advanced";
export type Difficulty = "easy" | "medium" | "hard" | "unrated";
export type GoalType = "assess_overall" | "improve_weak" | "learn_topic";
export type GoalKind = "strengthen_skills" | "weekly_practice" | "master_skill";
export type AnswerType = "numeric" | "multiple_choice" | "check_all";

export type ModelInfo = {
  available: boolean;
  name: string | null;
  display_name: string | null;
  test_auc: number | null;
  test_accuracy: number | null;
  parameters: number | null;
  reason: string | null;
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
  onboarded: boolean;
  diagnostic_completed: boolean;
  goal_type: GoalType | null;
  focus_skill: { id: number; name: string; code: string } | null;
  pace_preference: "more_support" | "balanced" | "challenge";
  hints_enabled: boolean;
  goal: Goal | null;
  is_admin: boolean;
};

export type Catalog = {
  subject: { code: string; name: string; description: string };
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
  model: ModelInfo;
};

export type Diagnosis = {
  assessment: { id: string; kind: string; correct: number; answered: number; completed_at: string } | null;
  headline: string;
  counts: Record<Status, number>;
  assessed: SkillSummary[];
  model_estimates_for_unassessed: SkillSummary[];
  recommendations: Recommendation[];
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
  | { type: "multiple_choice" | "check_all"; option_ids: string[]; options_html: string[] };

export type Mistake = {
  item_id: number;
  body_html: string;
  answer_type: AnswerType;
  options: { id: string; html: string }[];
  your_response: { value?: string; choice?: string; choices?: string[]; revealed?: boolean };
  correct_answer: CorrectAnswer;
  revealed: boolean;
  at: string;
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

export type SkillDetail = SkillSummary & {
  description: string;
  standard_url: string | null;
  difficulty_counts: Partial<Record<Difficulty, number>>;
  fresh_questions: number;
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
  next_activity: { action: "skill_check" | "foundation" | "reassess" | "practice"; label: string };
  mode_policy: { start: Difficulty; target_p: number; hints: string };
  reassessment_length: number;
};

export type Question = {
  item_id: number;
  skill: { id: number; code: string; name: string };
  body_html: string;
  answer_type: AnswerType;
  options: { id: string; html: string }[];
  difficulty: Difficulty;
  position: number | null;
  total: number | null;
  // practice only
  selection?: { requested: string; served: string; how: string; fallback_note: string | null };
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
  correct: boolean;
  correct_answer: CorrectAnswer;
  message: string;
  answered: number;
  total: number;
  complete: boolean;
  result: ReassessmentResult | null;
};

export type PracticeStart = { id: string; skill_id: number; mode: Mode; guided: boolean; difficulty: Difficulty; total: number; answered: number };

export type PracticeSummary = {
  accuracy: number;
  correct: number;
  answered: number;
  skill_accuracy: number | null;
  skill_attempts: number;
  predicted_p: number | null;
  mode: Mode | null;
  next: { action: "reassess" | "foundation" | "practice"; label: string; why: string };
};

export type PracticeAnswer = {
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
    assessments: number;
    practice_sessions: number;
    resources_completed: number;
    resources_total: number;
  };
  daily: DayPoint[];
  skills: SkillSummary[];
  assessments: { id: string; kind: string; skill: string | null; accuracy: number; correct: number; answered: number; completed_at: string; outcome: string | null }[];
  practice: { id: string; skill: string; mode: Mode; accuracy: number; answered: number; started_at: string }[];
  activity: Activity[];
  model: ModelInfo;
};

const V2 = "/api/v2";

export const tutor = {
  profile: () => api.get<Profile>(`${V2}/profile`),
  onboard: (body: { goal_type: GoalType; focus_skill_id?: number | null; goal_kind: GoalKind; goal_target?: number | null }) =>
    api.post<Profile>(`${V2}/onboarding`, body),
  updateProfile: (body: Partial<{ pace_preference: Profile["pace_preference"]; hints_enabled: boolean; goal_type: GoalType; focus_skill_id: number | null }>) =>
    api.patch<Profile>(`${V2}/profile`, body),
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
  practiceNext: (id: string) => api.get<Question>(`${V2}/practice/${id}/next`),
  practiceHint: (id: string) => api.post<{ kind: string; text: string; source: string }>(`${V2}/practice/${id}/hint`),
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
export type AdminPrereq = { skill_id: number; skill: string; prerequisite_id: number; prerequisite: string; source: string };

export const adminApi = {
  overview: () => api.get<{ skills: number; available_skills: number; items: number; usable_items: number; disabled_by_admin: number; exclusions: { reason: string; count: number }[]; resources: number; prerequisites: number }>(`${V2}/admin/overview`),
  skills: (q?: string) => api.get<AdminSkill[]>(`${V2}/admin/skills${q ? `?q=${encodeURIComponent(q)}` : ""}`),
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
