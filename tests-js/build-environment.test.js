// REQ-DASH-094 - the dashboard says which environment's QA it is showing.
//
// WHY THIS FILE IS SMALLER THAN THE REQUIREMENT. Four of the seven
// criteria were already met by REQ-PIPE-092, which built BUILD_PROVENANCE
// and renders it in the masthead: the page states its environment
// (criterion 1), in the masthead where nothing has to be opened or
// scrolled (2), from an embedded const a reader cannot change (5). What
// was missing is the part that makes a screenshot safe rather than merely
// labelled:
//
//   - criterion 3: a non-production build has to be visually DISTINCT as
//     well as labelled, and never by colour alone, because a screenshot
//     may be printed in greyscale.
//   - criterion 6: with NO environment recorded, the page has to say so
//     plainly rather than render as though it were production. Before
//     this change it rendered nothing at all, which is precisely the
//     failure that criterion names - an unlabelled page reads as the
//     real one.
//
// These assert on the real, observable DOM a reader would see, never on
// internals - same rule as every other file here.
import { afterEach, describe, expect, it } from "vitest";
import { loadDashboard, TEMPLATE_PATH } from "./support/loadDashboard.js";
import { readFileSync } from "node:fs";

let dashboard;

afterEach(() => {
  dashboard?.close();
  dashboard = undefined;
});

// The real build embeds BUILD_PROVENANCE by replacing the template's own
// `const BUILD_PROVENANCE = null;` - so do the same, rather than assigning
// to window afterwards, which a const in a non-module script would not
// allow anyway.
function withProvenance(provenance, { builtAt = "2026-09-28T04:00:00+08:00" } = {}) {
  const source = readFileSync(TEMPLATE_PATH, "utf-8")
    .replace("const BUILD_PROVENANCE = null;",
             `const BUILD_PROVENANCE = ${JSON.stringify(provenance)};`)
    .replace("const BUILT_AT = null;", `const BUILT_AT = ${JSON.stringify(builtAt)};`);
  return loadDashboard({ html: source });
}

const PUBLISHED = { environment: { id: "prod", label: "Production", publishes: true }, commit: "abc1234def" };
const SANDBOX = { environment: { id: "sandbox", label: "Claude Code sandbox", publishes: false }, commit: "abc1234def" };

describe("REQ-DASH-094 - a build says which environment it came from", () => {
  it("names the environment on the page, without anything being opened", () => {
    dashboard = withProvenance(SANDBOX);
    const el = dashboard.window.document.getElementById("clock-text");
    expect(el.textContent).toContain("Claude Code sandbox");
  });

  it("marks a NON-PUBLISHED build as distinct in the text itself, not by colour", () => {
    // Criterion 3. The distinction has to survive greyscale and a reader
    // who cannot perceive the colour, so it must be in the TEXT - a class
    // that only changes a colour would pass a DOM test and fail a person.
    dashboard = withProvenance(SANDBOX);
    const el = dashboard.window.document.getElementById("clock-text");
    const marked = el.closest(".live");
    expect(marked.classList.contains("non-production")).toBe(true);
    // And the words themselves say it, independently of any styling.
    expect(el.textContent.toLowerCase()).toContain("not production");
  });

  it("does NOT mark the published build as non-production", () => {
    dashboard = withProvenance(PUBLISHED);
    const el = dashboard.window.document.getElementById("clock-text");
    expect(el.closest(".live").classList.contains("non-production")).toBe(false);
    expect(el.textContent.toLowerCase()).not.toContain("not production");
    expect(el.textContent).toContain("Production");
  });

  it("says so plainly when the build recorded NO environment", () => {
    // Criterion 6, and the real regression this file exists for: before
    // this change the page rendered nothing at all in that case, so an
    // artifact with no environment was indistinguishable from the
    // published one.
    dashboard = withProvenance({ environment: null, commit: "abc1234def" });
    const el = dashboard.window.document.getElementById("clock-text");
    expect(el.textContent.toLowerCase()).toContain("environment unknown");
    expect(el.closest(".live").classList.contains("non-production")).toBe(true);
  });

  it("still says the commit when there is no environment", () => {
    // The two halves tolerate absence independently - one missing must
    // not suppress the other.
    dashboard = withProvenance({ environment: null, commit: "abc1234def" });
    expect(dashboard.window.document.getElementById("clock-text").textContent).toContain("abc1234");
  });

  it("renders with zero console errors in every one of those states", () => {
    // Criterion 7, held to the same bar as the rest of this suite.
    for (const provenance of [PUBLISHED, SANDBOX, { environment: null, commit: null }]) {
      const d = withProvenance(provenance);
      expect(d.errors, `provenance ${JSON.stringify(provenance)}`).toEqual([]);
      d.close();
    }
  });
});
