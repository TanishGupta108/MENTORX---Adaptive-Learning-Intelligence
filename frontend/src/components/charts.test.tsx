import { describe, expect, it } from "vitest";
import type { Concept } from "../api/types";
import { level, segments } from "./charts";
import { depths } from "./ConceptMap";
import { masteryTone } from "./ui";

describe("chart helpers", () => {
  it("keeps days without data as gaps, never zeros", () => {
    expect(segments([null, 0.5, 0.6, null, 0.7])).toEqual([
      [
        { i: 1, v: 0.5 },
        { i: 2, v: 0.6 },
      ],
      [{ i: 4, v: 0.7 }],
    ]);
    expect(segments([null, null])).toEqual([]);
  });

  it("heatmap levels are relative to the busiest day", () => {
    expect([0, 1, 5, 10].map((c) => level(c, 10))).toEqual([0, 1, 2, 4]);
    expect(level(3, 0)).toBe(0);
  });

  it("mastery bands", () => {
    expect([null, 0.1, 0.45, 0.65, 0.85].map(masteryTone)).toEqual([
      "unknown",
      "low",
      "weak",
      "ok",
      "mastered",
    ]);
  });
});

const c = (code: string, prerequisites: string[] = []): Concept => ({
  code,
  name: code,
  description: "",
  topo_order: 0,
  prerequisites,
  mastery: null,
  n_attempts: 0,
});

describe("concept map layout", () => {
  it("puts each concept one level below its deepest prerequisite", () => {
    expect(depths([c("a"), c("b", ["a"]), c("c", ["a", "b"]), c("d")])).toEqual({
      a: 0,
      b: 1,
      c: 2,
      d: 0,
    });
  });

  it("rejects cycles", () => {
    expect(() => depths([c("a", ["b"]), c("b", ["a"])])).toThrow(/cycle/);
  });
});
