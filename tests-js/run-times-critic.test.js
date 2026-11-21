// The post-build critic's findings on the run-time and could-not-be-checked
// page work (post-build-review #401, #404, #405, #408), each written first.
import { afterEach, describe, expect, it } from "vitest";
import { loadDashboard } from "./support/loadDashboard.js";

let dashboard;
afterEach(() => { dashboard?.close(); dashboard = undefined; });
const load = () => { dashboard = loadDashboard(); return dashboard.window; };

const DS = "cp-clients";
const CNC = (extra = {}) => ({kind: "could-not-check", datasetId: DS, supply: `${DS}@old`,
  openedAt: "2026-06-01T02:00:00+00:00", receivedAt: "2026-02-01T02:00:00+00:00",
  resolvedAt: null, reason: "x", files: [], loadFailures: [],
  tries: {runId: "r", outcome: "CRASHED", tool: null, errorType: "RuntimeError",
          beganAt: "2026-06-01T03:00:00+00:00", endedAt: "2026-06-03T03:00:00+00:00",
          failed: 3, failedEndedAt: ["2026-05-30T04:00:00+00:00", "2026-05-31T04:00:00+00:00",
                                     "2026-06-03T03:00:00+00:00"]}, ...extra});
const ds = latest => ({id: DS, lastArrival: latest ? {arrivedAt: latest} : null});

describe("#401: a crashed re-check of an OLDER supply", () => {
  it("does not blank the newer supply received since", () => {
    const w = load();
    // The older supply's re-check opened 1 June; a newer supply arrived in May.
    const got = w.blockerWithoutARunOfItsOwn(ds("2026-05-01T02:00:00+00:00"), "2026-06-10",
                                             {items: [], blockers: [CNC()]});
    expect(got).toBeNull();
  });

  it("still blanks where the crashed supply IS the newest one received", () => {
    const w = load();
    const newest = CNC({receivedAt: "2026-05-01T02:00:00+00:00"});
    // The latest CHECKED supply is the April one; the crashed one came after.
    expect(w.blockerWithoutARunOfItsOwn(ds("2026-04-01T02:00:00+00:00"), "2026-06-10",
                                        {items: [], blockers: [newest]})).not.toBeNull();
  });

  it("an arrival nobody could check, received after a passing supply, blanks it - no earlier verdict as current", () => {
    const w = load();
    const arrival = CNC({openedAt: "2026-06-01T02:00:00+00:00", receivedAt: "2026-06-01T02:00:00+00:00"});
    expect(w.blockerWithoutARunOfItsOwn(ds("2026-05-01T02:00:00+00:00"), "2026-06-10",
                                        {items: [], blockers: [arrival]})).not.toBeNull();
    expect(w.checkStatus({current_status: "green", blockedThisPeriod: true})).toBe("nodata");
  });

  it("has a banner of its own whose first line says it is ours, not the supplier's (#493 M2)", () => {
    // Keith, 2026-11-21: keep the red Fail, and lead with whose failure it is.
    const w = load();
    const lead = w.blockedBannerLead({...CNC(), count: 1});
    expect(lead).toContain("Could not be checked");
    expect(lead).toContain("our pipeline could not check this supply");
    expect(lead).toContain("this is not a problem with the supplier's data");
    expect(lead).not.toContain("until a person resolves it");
    expect(lead).not.toContain("Received");
  });

  it("says each thing once under the banner, the next step in its body (#493 M1)", () => {
    const w = load();
    const lead = w.blockedBannerLead({...CNC(), count: 1});
    const body = w.couldNotCheckWords(CNC(), "2026-06-10", {underBanner: true});
    expect(lead).not.toContain("retries it");
    expect(body).toContain("The next processing pass retries it");
    expect(body).not.toContain("Could not be checked");
    expect(body).toMatch(/^Its newest try /);
  });

  it("says a try ended AT a time, never 'on 9:09am' (#493 M1)", () => {
    const w = load();
    const said = w.couldNotCheckWords(CNC(), "2026-06-10");
    expect(said).toMatch(/its newest try [a-z -]+ at /);
    expect(said).not.toMatch(/its newest try [a-z -]+ on \d/);
  });
});

describe("#404: no 'another try' unless the try before failed", () => {
  it("says nothing for a run completed, reopened and completed again", () => {
    const w = load();
    const r = {run_id: "r1", attempts: {count: 2, left_out: 0, tries: [
      {number: 1, began_at: "2026-03-01T02:00:00+00:00", ended_at: "2026-03-01T03:00:00+00:00", outcome: "COMPLETED", run_time_ms: 1000},
      {number: 2, began_at: "2026-03-05T02:00:00+00:00", ended_at: "2026-03-05T03:00:00+00:00", outcome: "COMPLETED", run_time_ms: 1000}]}};
    expect(w.triesNote(r, null)).toBe("");
  });
});

describe("#405: the try count is as at the date on show", () => {
  it("counts only the failed tries that had ended by the date", () => {
    const w = load();
    expect(w.couldNotCheckWords(CNC(), "2026-05-30")).toContain("1 earlier try did not finish");
    const two = w.couldNotCheckWords(CNC(), "2026-06-02");
    expect(two).toContain("2 earlier tries did not finish");
    expect(two).not.toMatch(/checked on \d+ tries/);
    expect(w.couldNotCheckWords(CNC(), "2026-06-10")).toContain("on 3 tries");
  });
});

describe("#408: the cycle row of a supply that could not be checked", () => {
  it("reads the grey No data, never its earlier verdict", () => {
    const w = load();
    w.rawRealDatasetById = id => ({id, runs: [{run_id: "r1", supply_id: `${DS}@old`}]});
    w.blockersOpenInPlaceOn = () => [CNC()];
    const html = w.supplyRowStatus(DS, {run_id: "r1", status: "green"}, "2026-06-10");
    expect(html).toContain("data-could-not-check-row");
    expect(html).toContain('pill nodata');
    expect(html).not.toContain('pill green');
  });
});
