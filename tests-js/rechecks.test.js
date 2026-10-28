// REQ-DASH-221 criterion 12: a promoted supply re-checked worse is listed in the
// outstanding queue under the terminal's own heading, 'Promoted, then
// re-checked <verdict>', and counted in every outstanding marker - and
// criteria 1 and 2's words for a single and a bulk re-check.
import { afterEach, describe, expect, it } from "vitest";
import { loadDashboard } from "./support/loadDashboard.js";

let dashboard;
afterEach(() => { dashboard?.close(); dashboard = undefined; });

const ITEM = {
  kind: "promoted-then-rechecked", severity: "needs-action", blocking: false,
  headline: "Notifications, 2024-Q3", verdict: "red",
  detail: "The supply received 10:00am Thursday, 25 July 2024 was promoted into 2024-Q3 green; " +
    "a re-check 10:30am Friday, 9 August 2024 came back red.",
  agencyId: "child-protection-family-support", collectionId: "child-protection",
  datasetId: "cp-notifications", observedAt: "2024-08-09T02:30:00+00:00", responses: [],
  affects: [],
};

describe("a promoted supply re-checked worse in the outstanding queue", () => {
  it("is headed 'Promoted, then re-checked <verdict>'", () => {
    dashboard = loadDashboard();
    const html = dashboard.window.outstandingItemHtml(ITEM);
    const div = dashboard.window.document.createElement("div");
    div.innerHTML = html;
    expect(div.querySelector(".queue-head b").textContent).toBe("Promoted, then re-checked red");
    expect(div.textContent).toContain("Notifications, 2024-Q3");
  });

  it("names amber where the re-check came back amber", () => {
    dashboard = loadDashboard();
    expect(dashboard.window.outstandingKindLabel("promoted-then-rechecked",
      { ...ITEM, verdict: "amber" })).toBe("Promoted, then re-checked amber");
  });
});

describe("a re-check in words", () => {
  it("says who, when and why for a single re-check", () => {
    dashboard = loadDashboard();
    expect(dashboard.window.recheckWords({
      at: "2024-08-07T02:30:00+00:00", person: "Keith Moss", reason: "our check was <wrong>",
      before: "red", after: "green" })).toBe(
      "re-checked Wednesday, 7 August 2024 by Keith Moss - our check was &lt;wrong&gt;");
  });

  it("names the check we corrected, and 'and other checks' where others moved", () => {
    dashboard = loadDashboard();
    const words = dashboard.window.recheckWords({
      at: "2024-08-08T02:30:00+00:00", person: "Keith Moss", reason: "fixed",
      before: "red", after: "green",
      bulk: { checkId: "not-on-this-page", changelogDate: "2024-08-01", others: true } }, true);
    expect(words).toBe("re-checked after we corrected not-on-this-page (Thursday, 1 August 2024)"
      + " and other checks");
  });
});

describe("a past re-check in the page's decision wording", () => {
  it("reads 're-checked', never the raw operation name (criterion 7)", () => {
    dashboard = loadDashboard();
    expect(dashboard.window.decisionWords({ action: "re-check" })).toBe("re-checked");
  });
});
