// plans/qa-pipeline.md item 74, Bug A (fixed 2026-09-19).
//
// The dashboard used to derive every status purely from warn/fail
// thresholds, and build_dashboard_data.py substituted 0 for a threshold
// that was genuinely None. For any check whose real rule can't be stated
// as a one-sided "value > threshold" bound, that fabricated a red.
//
// The measured case, against this repo's own committed history: the ODCS
// `rowCount` rule is `mustBeBetween: [500, 20000]` with
// `severity: warning` - a two-sided range, so both bounds are correctly
// null. The tools evaluated it and said `pass`; the dashboard showed
// `1939 > 0` => RED, on 352/352 BDM runs and 18/18 CP runs. Across both
// datasets 1,829 results disagreed with their own tool - every single
// one in the same direction (tool pass -> dashboard amber/red), never
// the reverse, so the bug only ever manufactured false alarms.
//
// These cover the fix from both sides: the real verdict wins, AND the
// threshold fallback still treats a genuine zero-tolerance check as red
// (the regression the naive "just pass null through" fix would cause).
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

describe("checkStatus prefers the tool's own verdict", () => {
  it("is green for a two-sided range check the tool passed", () => {
    const w = load();
    // The real rowCount shape: big legitimate value, no single-sided bound.
    expect(w.checkStatus({
      current: 1939, warn: null, fail: null, current_status: "green",
    })).toBe("green");
  });

  it("does not fabricate a red from null thresholds even with no verdict", () => {
    const w = load();
    expect(w.checkStatus({ current: 1939, warn: null, fail: null })).toBe("green");
  });

  it("still honours a real tool failure the thresholds would have missed", () => {
    const w = load();
    expect(w.checkStatus({
      current: 0, warn: null, fail: null, current_status: "red",
    })).toBe("red");
  });

  it("falls back to threshold math when no verdict was recorded", () => {
    const w = load();
    expect(w.checkStatus({ current: 11, warn: 5, fail: 10 })).toBe("red");
    expect(w.checkStatus({ current: 7, warn: 5, fail: 10 })).toBe("amber");
    expect(w.checkStatus({ current: 1, warn: 5, fail: 10 })).toBe("green");
  });
});

describe("statusForValue treats a null bound as absent, not zero", () => {
  it("never reds on a null fail threshold", () => {
    const w = load();
    expect(w.statusForValue(1939, null, null)).toBe("green");
  });

  it("still ambers on a real warn when fail is genuinely absent", () => {
    const w = load();
    // A warn-only Soda check: warn configured, no stricter tier to escalate to.
    expect(w.statusForValue(7, 5, null)).toBe("amber");
    expect(w.statusForValue(3, 5, null)).toBe("green");
  });

  it("still reds on a real zero-tolerance fail threshold", () => {
    const w = load();
    // A dbt not_null-style violation count: fail=0 genuinely means
    // "any violation is a failure", and must keep reading red.
    expect(w.statusForValue(14, null, 0)).toBe("red");
    expect(w.statusForValue(0, null, 0)).toBe("green");
  });
});

describe("historyStatus", () => {
  it("prefers a history entry's own recorded verdict", () => {
    const w = load();
    expect(w.historyStatus({ value: 2119, status: "green" },
                           { warn: null, fail: null })).toBe("green");
  });

  it("falls back to the check's thresholds when the entry has no status", () => {
    const w = load();
    expect(w.historyStatus({ value: 14 }, { warn: 5, fail: 10 })).toBe("red");
  });
});

describe("fmtMetric", () => {
  it("renders an absent threshold rather than throwing on null", () => {
    const w = load();
    // Pre-fix this was null.toFixed(2), a hard TypeError that took the
    // whole check-detail panel down the moment a null threshold reached it.
    expect(() => w.fmtMetric(null, "%")).not.toThrow();
    expect(w.fmtMetric(null, "%")).toBe("—");
    expect(w.fmtMetric(null, "count")).toBe("—");
  });

  it("still formats real values exactly as before", () => {
    const w = load();
    expect(w.fmtMetric(1.959773, "%")).toBe("1.96%");
    expect(w.fmtMetric(1939, "count")).toBe("1,939");
  });
});
