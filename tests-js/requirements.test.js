// Requirements panel helpers - item 75 (plans/qa-pipeline.md,
// 2026-09-18): moscowLabel()/moscowPill() and requirementStatusLabel()/
// requirementStatusPill(), the small display-mapping helpers
// renderRequirementsPanel() itself relies on, kept separately testable
// rather than only exercised indirectly through the full panel render.
// renderRequirementsPanel() itself reads the top-level `const
// REQUIREMENTS` directly (same pattern as renderChangelogPanel()/
// RELEASE_NOTES, which this mirrors) rather than taking it as a
// parameter - a top-level `const` in a classic script never becomes a
// `window` property the way a `function` declaration does, so it can't
// be swapped in from outside like buildSupplyHistory()'s own `d`
// argument can. Full real-content rendering is instead verified by the
// real-browser e2e test (tests/test_dashboard_e2e.py), against the
// real built dashboard with real requirements.yaml data embedded - the
// same division of coverage RELEASE_NOTES/renderChangelogPanel()
// already has.
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

describe("moscowLabel / moscowPill", () => {
  it.each([
    ["must", "Must"],
    ["should", "Should"],
    ["could", "Could"],
    ["wont", "Won't"],
  ])("labels %s as %s", (moscow, label) => {
    const w = load();
    expect(w.moscowLabel(moscow)).toBe(label);
  });

  it("falls back to the raw value for an unrecognized moscow", () => {
    const w = load();
    expect(w.moscowLabel("urgent")).toBe("urgent");
  });

  it("renders a real pill whose class is NOT a data-status class", () => {
    // Changed 2026-09-25 (post-build-review #56). This asserted
    // `pill red` for `must` - which was the defect, not the contract:
    // a requirement's PRIORITY was drawn in exactly the pill a failing
    // dataset uses, so one viewport carried red "Red" agency pills on
    // the left and red "Must" requirement pills on the right. Same
    // palette, two unrelated meanings, and REQ-QAC-047 owns the status
    // vocabulary.
    const w = load();
    const html = w.moscowPill("must");
    expect(html).toContain("Must");
    for (const status of ["red", "amber", "green", "nodata", "exhausted", "inactive"]) {
      expect(html).not.toContain(`pill ${status}`);
    }
  });

  it("gives each priority its own distinct class", () => {
    const w = load();
    const classes = ["must", "should", "could", "wont"].map((m) => {
      const match = w.moscowPill(m).match(/class="pill ([^ "]+)/);
      return match && match[1];
    });
    expect(new Set(classes).size).toBe(4);
    expect(classes.every(Boolean)).toBe(true);
  });
});

describe("requirementStatusLabel / requirementStatusPill", () => {
  it.each([
    ["built", "Built"],
    ["in_progress", "In progress"],
    ["not_started", "Not started"],
  ])("labels %s as %s", (status, label) => {
    const w = load();
    expect(w.requirementStatusLabel(status)).toBe(label);
  });

  it("renders a real pill with the right label and status class", () => {
    const w = load();
    const html = w.requirementStatusPill("built");
    expect(html).toContain("Built");
    expect(html).toContain("pill green");
  });
});

describe("renderRequirementsPanel (raw template, illustrative-fallback state)", () => {
  it("shows the real empty-state message against the raw template's own null-placeholder REQUIREMENTS", () => {
    const w = load();
    w.renderRequirementsPanel();
    const body = w.document.getElementById("requirements-panel-body");
    expect(body.innerHTML).toContain("No requirements yet");
  });
});
