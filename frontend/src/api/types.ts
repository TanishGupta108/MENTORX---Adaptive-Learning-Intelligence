/** Response and request shapes. These mirror the backend's Pydantic schemas (see /docs). */

export type User = {
  id: string;
  email: string;
  full_name: string;
  role: "student" | "admin";
  daily_goal: number;
  timezone: string;
  consent_research: boolean;
  created_at: string;
  enrolled_subjects: string[];
};

export type Subject = {
  code: string;
  name: string;
  description: string;
  concept_count: number;
  enrolled: boolean;
};

export type Concept = {
  code: string;
  name: string;
  description: string;
  topo_order: number;
  prerequisites: string[];
  mastery: number | null;
  n_attempts: number;
};

export type SessionType = "diagnostic" | "practice" | "revision";

export type MasteryChange = { concept: string; before: number | null; after: number };

export type Session = {
  id: string;
  subject: string;
  type: SessionType;
  status: "active" | "completed" | "abandoned";
  focus_concept: string | null;
  answered: number;
  target: number;
  started_at: string;
  ended_at: string | null;
  correct: number | null;
  changes: MasteryChange[] | null;
};

export type Question = {
  session_id: string;
  question_id: number;
  concept: string;
  concept_name: string;
  stem: string;
  options: { key: OptionKey; text: string }[];
  allow_dont_know: boolean;
  position: number;
  total: number;
};

export type OptionKey = "A" | "B" | "C" | "D";

export type ConceptSummary = { concept: string; name: string; mastery: number };

export type AnswerResult = {
  feedback: { correct: boolean; correct_key: OptionKey; explanation: string } | null;
  mastery: MasteryChange | null;
  answered: number;
  target: number;
  session_complete: boolean;
  summary: { strongest: ConceptSummary[]; weakest: ConceptSummary[] } | null;
  changes: MasteryChange[] | null;
  goal?: GoalProgress | null;
};

/** FR-ENG-03: progress toward today's goal of valid answers. */
export type GoalProgress = {
  daily_goal: number;
  today_valid: number;
  goal_met_today: boolean;
  just_met: boolean;
  current_streak: number;
};

export type Streak = GoalProgress & { longest_streak: number; today: string; timezone: string };

export type Weekly = {
  subject: string;
  start: string;
  end: string;
  questions: number;
  accuracy: number | null;
  goal_days_met: number;
  mean_mastery_start: number | null;
  mean_mastery_end: number | null;
  mastery_change: number | null;
  concepts_improved: { concept: string; name: string; before: number; after: number }[];
};

export type FeedbackCategory = "bug" | "content" | "idea" | "other";

export type PathReason = "revision" | "prerequisite" | "weak" | "new";

export type PathItem = {
  position: number;
  concept: string;
  name: string;
  reason: PathReason;
  target_difficulty: 1 | 2 | 3;
  mastery_at_generation: number | null;
  mastery: number | null;
  explanation: string;
};

export type LearningPath = {
  id: string;
  subject: string;
  trigger: string;
  generated_at: string;
  model_version: string | null;
  items: PathItem[];
};

export type RevisionQueue = {
  subject: string;
  threshold: number;
  due: {
    concept: string;
    name: string;
    peak: number;
    mastery: number;
    drop: number;
    last_practised_at: string | null;
  }[];
  upcoming: {
    concept: string;
    name: string;
    peak: number;
    mastery: number;
    due_in_days: number | null;
  }[];
  horizon_days: number;
};

export type ConceptMastery = { concept: string; name: string; mastery: number; n_attempts: number };

export type Dashboard = {
  subject: string;
  diagnostic_completed: boolean;
  concepts_total: number;
  concepts_assessed: number;
  concepts_mastered: number;
  mastered_threshold: number;
  mean_mastery: number | null;
  questions_answered: number;
  accuracy: number | null;
  sessions_completed: number;
  strongest: ConceptMastery[];
  weakest: ConceptMastery[];
  active_sessions: { id: string; type: SessionType; answered: number; target: number }[];
};

export type Trends = {
  subject: string;
  days: number;
  points: {
    day: string;
    answered: number;
    accuracy: number | null;
    mean_mastery: number | null;
  }[];
};

export type Activity = { weeks: number; timezone: string; days: { day: string; answered: number }[] };
