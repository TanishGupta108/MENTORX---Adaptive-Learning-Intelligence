import { api, downloadFile, setAccessToken } from "./client";
import type {
  Activity,
  AnswerResult,
  Concept,
  Dashboard,
  FeedbackCategory,
  LearningPath,
  OptionKey,
  PilotMetrics,
  PilotStatus,
  Question,
  RevisionQueue,
  Session,
  SessionType,
  Streak,
  Subject,
  Trends,
  User,
  Weekly,
} from "./types";

/** The MVP has one subject. Kept as a constant so adding subjects later is a small change. */
export const SUBJECT = "ML";

type Token = { access_token: string; expires_in: number };
const q = (subject: string) => `subject=${encodeURIComponent(subject)}`;

export const auth = {
  async login(email: string, password: string) {
    const t = await api.post<Token>("/auth/login", { email, password }, { noRetry: true });
    setAccessToken(t.access_token);
  },
  async register(body: {
    email: string;
    password: string;
    full_name: string;
    privacy_accepted: boolean;
    timezone?: string;
  }) {
    const t = await api.post<Token>("/auth/register", body, { noRetry: true });
    setAccessToken(t.access_token);
  },
  async logout() {
    try {
      await api.post<void>("/auth/logout", undefined, { noRetry: true });
    } finally {
      setAccessToken(null);
    }
  },
};

export const me = {
  get: (signal?: AbortSignal) => api.get<User>("/me", { signal }),
  update: (body: Partial<Pick<User, "full_name" | "daily_goal" | "timezone" | "consent_research">>) =>
    api.patch<User>("/me", body),
  export: () => api.get<unknown>("/me/export"),
  delete: (confirm_email: string) => api.delete<void>("/me", { confirm_email }),
};

export const subjects = {
  list: (signal?: AbortSignal) => api.get<Subject[]>("/subjects", { signal }),
  enroll: (code: string) => api.post<unknown>(`/subjects/${code}/enroll`),
  concepts: (code: string, signal?: AbortSignal) =>
    api.get<Concept[]>(`/subjects/${code}/concepts`, { signal }),
};

export const sessions = {
  start: (type: SessionType, concept?: string) =>
    api.post<Session>("/sessions", { subject: SUBJECT, type, ...(concept ? { concept } : {}) }),
  get: (id: string, signal?: AbortSignal) => api.get<Session>(`/sessions/${id}`, { signal }),
  list: (signal?: AbortSignal) => api.get<Session[]>("/sessions", { signal }),
  next: (id: string) => api.post<Question>(`/sessions/${id}/next`),
  answer: (id: string, question_id: number, selected_key: OptionKey | null) =>
    api.post<AnswerResult>(`/sessions/${id}/answer`, { question_id, selected_key }),
  end: (id: string) => api.post<Session>(`/sessions/${id}/end`),
  flag: (questionId: number, comment: string) =>
    api.post<unknown>(`/questions/${questionId}/flag`, { comment }),
};

export const learning = {
  path: (signal?: AbortSignal) => api.get<LearningPath>(`/learning-path?${q(SUBJECT)}`, { signal }),
  regenerate: () => api.post<LearningPath>(`/learning-path/regenerate?${q(SUBJECT)}`),
  revision: (signal?: AbortSignal) => api.get<RevisionQueue>(`/revision?${q(SUBJECT)}`, { signal }),
};

export const dashboard = {
  summary: (signal?: AbortSignal) => api.get<Dashboard>(`/dashboard?${q(SUBJECT)}`, { signal }),
  trends: (days = 30, signal?: AbortSignal) =>
    api.get<Trends>(`/dashboard/trends?${q(SUBJECT)}&days=${days}`, { signal }),
  activity: (weeks = 12, signal?: AbortSignal) =>
    api.get<Activity>(`/dashboard/activity?weeks=${weeks}`, { signal }),
};

export const engagement = {
  streak: (signal?: AbortSignal) => api.get<Streak>("/engagement/streak", { signal }),
  weekly: (signal?: AbortSignal) =>
    api.get<Weekly>(`/engagement/weekly?${q(SUBJECT)}`, { signal }),
  feedback: (body: { rating: number; category: FeedbackCategory; message: string; page: string }) =>
    api.post<{ id: number }>("/feedback", body),
};

export const pilot = {
  status: (signal?: AbortSignal) => api.get<PilotStatus>(`/pilot/status?${q(SUBJECT)}`, { signal }),
  sus: (answers: number[], comment: string) =>
    api.post<{ score: number }>(`/pilot/sus?${q(SUBJECT)}`, { answers, comment }),
};

export const admin = {
  metrics: (signal?: AbortSignal) => api.get<PilotMetrics>("/admin/pilot/metrics", { signal }),
  exportAttempts: () => downloadFile("/admin/export/attempts.csv", "mentorx-attempts.csv"),
  exportOutcomes: () => downloadFile("/admin/export/outcomes.csv", "mentorx-outcomes.csv"),
};
