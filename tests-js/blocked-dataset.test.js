// REQ-PIPE-115 criteria 10 to 12, 25 and 26: a held supply or a table two
// files claim makes its dataset RED, said once with its reason, judged as
// at the date on show, rolled up like any other red - and none of its own
// checks reads as passing for that period.
import { describe, it, expect } from "vitest";
import { loadDashboard } from "./support/loadDashboard.js";

const load = () => loadDashboard().window;

const HELD = {kind: "held", datasetId: "cp-case-workers", supply: "cp-case-workers@k",
              openedAt: "2026-03-10T02:00:00+00:00", resolvedAt: null,
              reason: "cp-case-workers@k could not be placed", files: [], loadFailures: []};
const RESOLVED = {...HELD, resolvedAt: "2026-03-20T02:00:00+00:00"};
const SOURCE = b => ({items: [], blockers: [b]});

describe("whether a hold or contest is open, as at the date on show", () => {
  it("is open from the supply's receipt, not before", () => {
    const w = load();
    expect(w.blockerOpenAsOf("cp-case-workers", "2026-03-09", SOURCE(HELD))).toBeNull();
    expect(w.blockerOpenAsOf("cp-case-workers", "2026-03-10", SOURCE(HELD))).not.toBeNull();
    expect(w.blockerOpenAsOf("cp-case-workers", "2027-01-01", SOURCE(HELD))).not.toBeNull();
  });

  it("closes on the day the decision that ended it took effect", () => {
    const w = load();
    expect(w.blockerOpenAsOf("cp-case-workers", "2026-03-19", SOURCE(RESOLVED))).not.toBeNull();
    expect(w.blockerOpenAsOf("cp-case-workers", "2026-03-20", SOURCE(RESOLVED))).toBeNull();
  });

  it("belongs to its own dataset only", () => {
    const w = load();
    expect(w.blockerOpenAsOf("cp-clients", "2026-03-15", SOURCE(HELD))).toBeNull();
  });

  it("says why in words, never by colour alone", () => {
    const w = load();
    expect(w.blockerReasonText(HELD)).toContain("Held");
    expect(w.blockerReasonText({...HELD, kind: "contested"})).toContain("Two files, choose one");
  });
});

describe("a blocked dataset is one red that rolls up", () => {
  const dataset = (extra) => ({columns: [{status: "green", checks: []}], ...extra});

  it("counts as red in its collection even with every column green", () => {
    const w = load();
    expect(w.rollup([dataset({blocked: HELD}), dataset({})])).toBe("red");
  });

  it("counts as red even where its runs alone would be quiet", () => {
    const w = load();
    expect(w.rollup([dataset({blocked: HELD, noDataAsOf: true, columns: []})])).toBe("red");
  });

  it("its own checks read not run, never the last verdict carried forward", () => {
    const w = load();
    expect(w.checkStatus({current_status: "green", blockedThisPeriod: true})).toBe("nodata");
    expect(w.checkStatus({current_status: "green"})).not.toBe("nodata");
  });
});

describe("supply history names every held supply and contested pair", () => {
  it("lists each received by the date on show, with its label and a dash for rows", () => {
    const w = load();
    const contested = {...HELD, kind: "contested", openedAt: "2026-03-12T02:00:00+00:00"};
    const html = w.blockerHistoryRows("cp-case-workers", "2026-04-01",
                                      {items: [], blockers: [HELD, contested]});
    expect(html).toContain("Held");
    expect(html).toContain("Two files, choose one");
    expect((html.match(/data-blocker=/g) || []).length).toBe(2);
  });

  it("leaves out one received after the date on show", () => {
    const w = load();
    expect(w.blockerHistoryRows("cp-case-workers", "2026-03-01", SOURCE(HELD))).toBe("");
  });
});

// REQ-QAC-108 criteria 8 and 14: the measured verdict apart from the red.
describe("a drift check compared across a gap", () => {
  it("says what it was compared with and keeps the measurement's own verdict apart", () => {
    const w = load();
    const html = w.referenceNoteHtml({status: "red", reference: {
      reason: "compared with 2026-Q1, not 2026-Q2: 2026-Q2 has no accepted supply",
      period: "2026-Q1", measuredStatus: "green"}});
    expect(html).toContain("Compared with 2026-Q1");
    expect(html).toContain("has no accepted supply");
    expect(html).toContain("not because anything drifted");
  });

  it("does not excuse a measurement that crossed its band itself", () => {
    const w = load();
    const html = w.referenceNoteHtml({status: "red", reference: {
      reason: "compared with 2026-Q1, not 2026-Q2: 2026-Q2 has no accepted supply",
      period: "2026-Q1", measuredStatus: "red"}});
    expect(html).not.toContain("not because anything drifted");
  });

  it("adds nothing for a check the rule did not touch", () => {
    expect(load().referenceNoteHtml({status: "green"})).toBe("");
  });
});
