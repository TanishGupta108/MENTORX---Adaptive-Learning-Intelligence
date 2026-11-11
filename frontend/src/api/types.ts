/** The signed-in account (from /api/v1/me). Learning data types are in ./tutor.ts. */
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
