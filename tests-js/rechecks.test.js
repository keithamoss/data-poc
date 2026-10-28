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

// post-build-review #283 (L2 wave-2 critic, 1): the red-promoted badge looked
// for an acknowledgement after the re-check that TURNED the supply red; the
// outstanding queue (rechecking.worse_than_promoted) and the amber tag look
// after the NEWEST re-check that has run. A supply re-checked red,
// acknowledged, then re-checked red again is outstanding again - and the
// badge said "acknowledged".
describe("the red-promoted badge's acknowledgement follows the newest re-check", () => {
  const RC1 = "2024-08-09T02:30:00+00:00", ACK = "2024-08-12T02:00:00+00:00";
  const RC2 = "2024-08-20T02:30:00+00:00";
  const raw = {
    id: "cp-notifications", runs: [{ run_id: "r1", run_date: "2024-07-25", supply_id: "s1" }],
    runStates: { r1: [{ at: "2024-07-26T01:00:00+00:00", state: "promoted", action: "promote" }] },
    promotedHealth: { r1: { promotedOn: "green", promotedAt: "2024-07-26T01:00:00+00:00",
      timeline: [{ at: "2024-07-25T02:00:00+00:00", status: "green", cause: "its arrival" },
                 { at: RC1, status: "red", cause: "a re-check" },
                 { at: RC2, status: "red", cause: "a re-check" }] } },
    rechecks: {
      supplies: { s1: [
        { at: RC1, person: "Keith Moss", reason: "first", before: "green", after: "red" },
        { at: RC2, person: "Keith Moss", reason: "second", before: "red", after: "red" }] },
      acks: { s1: [{ at: ACK, actor: "Ana Lee", reason: "known" }] } } };

  function withRaw(){
    dashboard = loadDashboard();
    dashboard.window.rawRealDatasetById = () => raw;
    return dashboard.window;
  }

  it("says acknowledged between the acknowledgement and the next re-check", () => {
    const w = withRaw();
    const html = w.redPromotedBadge("cp-notifications", "r1", "2024-08-15");
    expect(html).toContain("data-red-promoted-recheck");
    expect(html).toContain("acknowledged by Ana Lee");
  });

  it("no longer says acknowledged once a newer re-check has run", () => {
    const w = withRaw();
    const html = w.redPromotedBadge("cp-notifications", "r1", "2024-08-25");
    expect(html).toContain("data-red-promoted");
    expect(html).not.toContain("acknowledged by");
  });
});

// post-build-review #283 (L2 wave-2 critic, 8): a reason a person typed goes
// into a title attribute through escAttr, which also escapes its quotes.
describe("an acknowledgement's reason in a title attribute", () => {
  const REASON = 'said "fine" <ok>';

  it("is escaped, quotes included, on the acknowledgement badge", () => {
    dashboard = loadDashboard();
    const w = dashboard.window;
    w.rawRealDatasetById = () => ({ id: "x", acknowledgements: { r1: {
      promotedAt: "2024-07-26T01:00:00+00:00",
      acks: [{ at: "2024-07-27T01:00:00+00:00", actor: "Ana", reason: REASON, withdrawn: null }] } } });
    const div = w.document.createElement("div");
    div.innerHTML = w.acknowledgementBadge("x", "r1", "2024-08-01");
    expect(div.querySelector("[data-acknowledged]").getAttribute("title")).toBe(REASON);
  });

  it("is escaped, quotes included, on the re-checked amber tag", () => {
    dashboard = loadDashboard();
    const w = dashboard.window;
    const at = "2024-08-09T02:30:00+00:00";
    w.rawRealDatasetById = () => ({ id: "x", runs: [{ run_id: "r1", supply_id: "s1" }],
      runStates: { r1: [{ at: "2024-07-26T01:00:00+00:00", state: "promoted", action: "promote" }] },
      promotedHealth: { r1: { promotedOn: "green", timeline: [{ at, status: "amber" }] } },
      rechecks: { supplies: { s1: [{ at, person: "K", reason: "r", before: "green", after: "amber" }] },
        acks: { s1: [{ at: "2024-08-10T02:30:00+00:00", actor: "Ana", reason: REASON }] } } });
    const div = w.document.createElement("div");
    div.innerHTML = w.recheckedAmberTag("x", "r1", "2024-08-15");
    expect(div.querySelector('[data-rechecked-amber="acknowledged"]').getAttribute("title"))
      .toBe(REASON);
  });
});

// post-build-review #283 (L2 wave-2 critic, 6): the outstanding marker on a
// card names the kind as the queue heading does - "re-checked red" - rather
// than the item-less "re-checked worse".
describe("the outstanding marker names a re-checked-worse supply as the queue does", () => {
  it("counts it under 'promoted, then re-checked <verdict>'", () => {
    dashboard = loadDashboard();
    const other = { kind: "awaiting-decision", severity: "needs-action", blocking: false,
      agencyId: ITEM.agencyId, collectionId: ITEM.collectionId, datasetId: "cp-carers" };
    const amber = { ...ITEM, datasetId: "cp-clients", verdict: "amber" };
    const div = dashboard.window.document.createElement("div");
    div.innerHTML = dashboard.window.outstandingMarker("agency", ITEM.agencyId,
      { items: [ITEM, amber, other], blockers: [] });
    expect(div.textContent).toContain("1 promoted, then re-checked red");
    expect(div.textContent).toContain("1 promoted, then re-checked amber");
    expect(div.textContent).not.toContain("re-checked worse");
  });
});
