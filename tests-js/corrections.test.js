// REQ-DASH-172 - the corrected verdict is the page's; the original, the
// correction and its approver are one step away on the history row; a kept
// supply says so; a correction awaiting the asset manager is said on its
// dataset; a past date's note groups a correction's changes; the activity
// panel lists each correction once.
import { describe, it, expect } from "vitest";
import { loadDashboard } from "./support/loadDashboard.js";

function withRaw(raw){
  const w = loadDashboard().window;
  w.rawRealDatasetById = () => raw;
  return w;
}

const REJUDGED = {original: "late", new: "on_time", reference: "CAB-1", approver: "Keith Moss",
                  appliedAt: "2026-10-11T01:00:00+00:00", confirmedBy: "Keith Moss"};
const KEPT = {reference: "CAB-1", reason: "genuinely Q3 data, sent early", period: "2023-Q3",
              keptOutOf: null, actor: "Keith Moss", at: "2026-10-11T01:00:00+00:00"};

describe("a supply a correction re-judged (criteria 2 and 7)", () => {
  it("reads in the existing 'changed after' shape, naming the correction and approver", () => {
    const w = withRaw({corrections: {rejudged: {r1: [REJUDGED]}, kept: {}, awaiting: []}});
    const note = w.correctionNote("cp-clients", "r1");
    expect(note).toContain("Late at the time");
    expect(note).toContain("by correction CAB-1, approved by Keith Moss");
    expect(note).toContain("changed-by");
  });

  it("says nothing on a row no correction touched", () => {
    const w = withRaw({corrections: {rejudged: {r1: [REJUDGED]}, kept: {}, awaiting: []}});
    expect(w.correctionNote("cp-clients", "r2")).toBe("");
  });
});

describe("a supply kept against a correction (criterion 5)", () => {
  it("says it was kept, where, against which correction, and why", () => {
    const w = withRaw({corrections: {rejudged: {}, kept: {r1: [KEPT]}, awaiting: []}});
    // Under 'How it got here' since REQ-DASH-230.
    const note = w.correctionMoveNote("cp-clients", "r1");
    expect(w.correctionNote("cp-clients", "r1")).toBe("");
    expect(note).toContain("Kept in");
    expect(note).toContain("against correction CAB-1");
    expect(note).toContain("genuinely Q3 data, sent early");
  });
});

describe("a correction awaiting the asset manager (criterion 4)", () => {
  it("is said on the affected dataset, naming it", () => {
    const w = withRaw({corrections: {rejudged: {}, kept: {},
                                     awaiting: [{reference: "CAB-2", date: "2026-10-11", reason: "r"}]}});
    const line = w.awaitingCorrectionLine("cp-clients");
    expect(line).toContain("CAB-2");
    expect(line).toContain("awaiting the data");
  });

  it("is absent when nothing awaits", () => {
    const w = withRaw({corrections: {rejudged: {}, kept: {}, awaiting: []}});
    expect(w.awaitingCorrectionLine("cp-clients")).toBe("");
  });
});

describe("the wording table (criterion 10)", () => {
  it("has a completed-action word for every action the batch added", () => {
    const w = loadDashboard().window;
    for(const action of ["keep", "excuse-lateness", "withdraw-excuse", "acknowledge"]){
      expect(w.eval("DECISION_DONE")[action]).toBeTruthy();
    }
  });
});

describe("a past date's note (criteria 3 and 9)", () => {
  it("groups a correction's re-judgements into one item per correction per dataset", () => {
    const w = loadDashboard().window;
    const raw = {id: "cp-clients", name: "Clients", runs: [
                   {run_id: "r1", received_at: "2023-08-01T04:00:00+00:00"},
                   {run_id: "r2", received_at: "2023-08-02T04:00:00+00:00"}],
                 runStates: {},
                 corrections: {rejudged: {r1: [REJUDGED], r2: [REJUDGED]}, kept: {}, awaiting: []}};
    w.rawRealDatasets = () => [raw];
    const found = w.decisionsChangingDate("2024-01-01", null);
    expect(found.length).toBe(1);
    expect(found[0].correction).toBe("CAB-1");
    expect(found[0].count).toBe(2);
  });
});

describe("delivery-critic on 172 (post-build-review #149)", () => {
  it("5: one supply's past-date item is grammatical", () => {
    const w = loadDashboard().window;
    const raw = {id: "cp-clients", name: "Clients", runs: [{run_id: "r1", received_at: "2023-08-01T04:00:00+00:00"}],
                 runStates: {}, corrections: {rejudged: {r1: [REJUDGED]}, kept: {}, awaiting: []}};
    w.rawRealDatasets = () => [raw];
    w.datasetIdsInView = () => null;
    const note = w.changedSinceNote("2024-01-01");
    expect(note).not.toContain("supply'");
    expect(note).toContain("1 supply");
  });

  it("9: the row reads 're-judged <date> by correction <ref>', the date straight after", () => {
    const w = withRaw({corrections: {rejudged: {r1: [REJUDGED]}, kept: {}, awaiting: []}});
    const note = w.correctionNote("cp-clients", "r1");
    expect(note).toMatch(/re-judged [^<]*\d{4} by correction CAB-1/);
    expect(note).not.toContain("re-judged on time");
  });

  it("2: a supply kept held is said on its dataset", () => {
    const w = withRaw({corrections: {rejudged: {}, kept: {}, awaiting: [],
      keptHeld: [{supply: "cp-clients@kh1", reference: "CAB-1", reason: "not sure", keptOutOf: "2023-Q3",
                  actor: "Keith Moss", at: "2026-10-11T01:00:00+00:00"}]}});
    const line = w.keptHeldLine("cp-clients");
    expect(line).toContain("CAB-1");
    expect(line).toContain("not sure");
    expect(line).toContain("held");
  });

  it("10: several awaiting corrections read in the plural", () => {
    const w = withRaw({corrections: {rejudged: {}, kept: {}, awaiting: [
      {reference: "CAB-3", date: "2026-10-11", reason: "r"}, {reference: "CAB-4", date: "2026-10-11", reason: "r"}]}});
    const line = w.awaitingCorrectionLine("cp-clients");
    expect(line).toContain("corrections");
    expect(line).toContain("are awaiting");
  });

  it("6: an awaiting state that could not be worked out is said, never an all-clear", () => {
    const w = withRaw({corrections: {rejudged: {}, kept: {}, awaiting: [], awaitingUnknown: true}});
    expect(w.awaitingCorrectionLine("cp-clients")).toContain("could not be worked out");
  });

  it("a parked correction move has a kind label of its own (Keith, 2026-10-11, (p))", () => {
    const w = loadDashboard().window;
    expect(w.outstandingKindLabel("parked-correction-move")).toBe("Correction move waiting");
  });

  it("3: an outstanding item that affects datasets links each", () => {
    const w = loadDashboard().window;
    const html = w.outstandingItemHtml({kind: "pending-correction", severity: "needs-action", blocking: false,
      headline: "h", detail: "d", affects: [{agencyId: "a", collectionId: "c", datasetId: "cp-clients", name: "Clients"}]});
    expect(html).toContain("dataset-link");
    expect(html).toContain("Clients");
  });
});

describe("a supply a correction moved (Keith, 2026-10-11, (r))", () => {
  it("carries the same note, naming where it was and where it went", () => {
    const w = loadDashboard().window;
    w.rawRealDatasetById = () => ({corrections: {rejudged: {"run-1": [{
      original: "late", new: "on_time", reference: "CAB-1", approver: "Keith",
      appliedAt: "2026-10-11T09:00:00+08:00", movedFrom: "2023-Q3", movedTo: "2023-Q2"}]}}});
    // SPLIT (REQ-DASH-230, Keith 2026-10-15): punctuality in Timing, the move
    // under 'How it got here'.
    const timing = w.correctionNote("cp-clients", "run-1");
    const move = w.correctionMoveNote("cp-clients", "run-1");
    expect(timing).toContain("Late at the time");
    expect(timing).not.toContain("moved to");
    expect(move).toContain("In ");
    expect(move).toContain("moved to");
    expect(move).toContain("by correction CAB-1, approved by Keith");
  });
});
