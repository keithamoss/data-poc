// REQ-PIPE-194 criteria 10, 12, 13, 15 and 16: a settled pair on the page -
// one Settled row with each file's outcome, a re-filed file a real link
// framed as a re-file, each settled supply's note, the pair's own run
// dropped, and the decision worded in the past-date notice.
import { describe, it, expect } from "vitest";
import { loadDashboard } from "./support/loadDashboard.js";

const load = () => loadDashboard().window;

const SETTLED = {
  kind: "contested", datasetId: "cp-case-workers", supply: "cp-case-workers@k#1",
  openedAt: "2026-03-10T02:00:00+00:00", resolvedAt: "2026-03-12T02:00:00+00:00",
  reason: "Two files claim this dataset's table", files: ["a.csv", "b.csv"],
  loadFailures: [], supersededBy: null,
  settlement: {actor: "Keith Moss", at: "2026-03-12T02:00:00+00:00",
               reason: "the supplier sent next quarter's early",
               arrivalRunId: "cp_case_workers__k",
               files: [
                 {filename: "a.csv", receivedAt: "2026-03-10T02:00:00+00:00",
                  outcome: "supply", toPeriod: null, supplyId: "cp-case-workers@k#1",
                  runId: "cp_case_workers__k__1"},
                 {filename: "b.csv", receivedAt: "2026-03-10T02:05:00+00:00",
                  outcome: "refiled", toPeriod: "2026-Q3", supplyId: "cp-case-workers@k#2",
                  runId: "cp_case_workers__k__2"}]}};
const SOURCE = b => ({items: [], blockers: [b]});

describe("the settled row", () => {
  it("is one row with a Settled pill, who, why and each file's outcome", () => {
    const w = load();
    const html = w.blockerHistoryRows("cp-case-workers", "2026-04-01", SOURCE(SETTLED));
    expect((html.match(/data-blocker=/g) || []).length).toBe(1);
    expect(html).toContain(">Settled<");
    expect(html).toContain("settled by Keith Moss");
    expect(html).toContain("the supplier sent next quarter's early");
    expect(html).toContain("this period's supply");
    expect(html.indexOf("a.csv")).toBeLessThan(html.indexOf("b.csv"));
    expect(html).not.toContain('pill nodata');
  });

  it("is still open before the settlement's day", () => {
    const w = load();
    const html = w.blockerHistoryRows("cp-case-workers", "2026-03-11", SOURCE(SETTLED));
    expect(html).not.toContain(">Settled<");
    expect(html).toContain("Waiting for a person");
  });

  it("reads 'neither' the same way, both rejected", () => {
    const w = load();
    const neither = {...SETTLED, settlement: {...SETTLED.settlement, files:
      SETTLED.settlement.files.map(f=> ({...f, outcome: "rejected", toPeriod: null}))}};
    const html = w.blockerHistoryRows("cp-case-workers", "2026-04-01", SOURCE(neither));
    expect((html.match(/data-settled-file="rejected"/g) || []).length).toBe(2);
  });

  it("a contest a later arrival ended keeps the resolved style and says so", () => {
    const w = load();
    const ended = {...SETTLED, settlement: null,
                   supersededBy: {supply: "x", receivedAt: "2026-03-11T02:00:00+00:00"}};
    const html = w.blockerHistoryRows("cp-case-workers", "2026-04-01", SOURCE(ended));
    expect(html).toContain("superseded by the supply received");
    expect(html).toContain("pill nodata");
  });
});

describe("a re-filed file is a real link, framed as a re-file", () => {
  it("carries in-place-on, from, from-on and via=refile", () => {
    const w = load();
    w.periodDateFor = () => "2026-07-01";
    const link = w.refiledFileLink("cp-case-workers", "2026-Q3", "2026-Q1", "2026-04-01");
    expect(link).toContain('data-via="refile"');
    const href = /href="([^"]+)"/.exec(link)[1].replace(/&amp;/g, "&");
    const q = new URLSearchParams(href.split("?")[1].split("#")[0]);
    expect(q.get("from")).toBe("2026-Q1");
    expect(q.get("from-on")).toBe("2026-04-01");
    expect(q.get("via")).toBe("refile");
  });
});

describe("each settled supply's own row", () => {
  it("carries one note, and a re-filed one says where it was received for", () => {
    const w = load();
    w.blockersFor = () => [SETTLED];
    w.settledPairPeriod = () => "2026-Q1";
    expect(w.settledNote("cp-case-workers", "cp_case_workers__k__1__r1"))
      .toContain("From two files for one table, settled by Keith Moss");
    const moved = w.settledNote("cp-case-workers", "cp_case_workers__k__2__r1");
    expect(moved).toContain("moved to");
    expect(w.settledNote("cp-case-workers", "cp_case_workers__other")).toBe("");
  });
});

describe("the wording", () => {
  it("labels an open contest 'Two files for one table'", () => {
    const w = load();
    expect(w.outstandingKindLabel("contested-table")).toBe("Two files for one table");
  });

  it("says a settlement as 'settled' in the past-date notice", () => {
    expect(load().eval('DECISION_DONE["choose-file"]')).toBe("settled");
  });
});
