import { useMemo } from "react";
import { subjects, SUBJECT } from "../api/endpoints";
import { useApi } from "./useApi";

/** The subject's concepts (prerequisite order, with the student's mastery). */
export function useConcepts() {
  return useApi((signal) => subjects.concepts(SUBJECT, signal));
}

/** concept code -> display name. Empty until loaded (callers fall back to the code). */
export function useConceptNames(): Record<string, string> {
  const { data } = useConcepts();
  return useMemo(() => Object.fromEntries((data ?? []).map((c) => [c.code, c.name])), [data]);
}
