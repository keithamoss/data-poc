// Data-quality-dimension categorisation (2026-09-19, Keith's own ask,
// scoped via AskUserQuestion): groupChecksByCategory() - the check
// list's grouped-sections rendering (dashboard.qa-reporting-dashboard.
// template.html's own checksBlock, inside openColumnDrawer()).
import { afterEach, describe, expect, it } from "vitest";
import { loadDashboard } from "./support/loadDashboard.js";

let dashboard;

afterEach(() => {
  dashboard?.close();
  dashboard = undefined;
});

function load() {
  dashboard = loadDashboard();
  return dashboard.window;
}

describe("groupChecksByCategory", () => {
  it("groups checks by their real dimension field", () => {
    const w = load();
    const checks = [
      { name: "a", dimension: "completeness" },
      { name: "b", dimension: "conformity" },
      { name: "c", dimension: "completeness" },
    ];
    const groups = w.groupChecksByCategory(checks);
    const byKey = Object.fromEntries(groups.map(g => [g.key, g.checks.map(c => c.name)]));
    expect(byKey.completeness).toEqual(["a", "c"]);
    expect(byKey.conformity).toEqual(["b"]);
  });

  it("orders groups by CATEGORY_ORDER, not by first appearance or alphabetically", () => {
    const w = load();
    const checks = [
      { name: "a", dimension: "timeliness" },
      { name: "b", dimension: "completeness" },
      { name: "c", dimension: "uniqueness" },
    ];
    const groups = w.groupChecksByCategory(checks);
    expect(groups.map(g => g.key)).toEqual(["completeness", "uniqueness", "timeliness"]);
  });

  it("falls back to an 'other' group for a missing or unrecognised dimension", () => {
    const w = load();
    const checks = [
      { name: "a", dimension: "" },
      { name: "b" },
      { name: "c", dimension: "not-a-real-dimension" },
    ];
    const groups = w.groupChecksByCategory(checks);
    expect(groups).toHaveLength(1);
    expect(groups[0].key).toBe("other");
    expect(groups[0].checks.map(c => c.name)).toEqual(["a", "b", "c"]);
  });

  it("omits empty categories entirely rather than rendering an empty section", () => {
    const w = load();
    const groups = w.groupChecksByCategory([{ name: "a", dimension: "consistency" }]);
    expect(groups).toHaveLength(1);
    expect(groups[0].key).toBe("consistency");
  });

  it("real category labels are human-readable, not raw dimension strings", () => {
    const w = load();
    const groups = w.groupChecksByCategory([
      { name: "a", dimension: "completeness" },
      { name: "b", dimension: "" },
    ]);
    expect(groups.find(g => g.key === "completeness").label).toBe("Completeness");
    expect(groups.find(g => g.key === "other").label).toBe("Other");
  });
});
