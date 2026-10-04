// REQ-DASH-133: a period that closed with no supply is red and says so in
// words; one a person accepted is quiet and names the reason; both are
// judged as at the date on show, grouped into runs, and counted on the
// agency card in one line broken out by kind.
import { describe, it, expect } from "vitest";
import { loadDashboard } from "./support/loadDashboard.js";

const load = () => loadDashboard().window;

const slot = (period, index, extra) => ({period, index,
  closesAt: `${period}T16:00:00+00:00`, filledAt: null, filedAt: null,
  markedAt: null, mark: null, ...extra});
const DAYS = ["2026-03-01", "2026-03-02", "2026-03-03"].map((d, i) => slot(d, 10 + i));
const LATER_DAY = slot("2026-03-09", 18);

describe("what a closed slot reads as, as at the date on show", () => {
  it("is not a gap before it closes", () => {
    const w = load();
    expect(w.closedGapsAsOf([DAYS[0]], "2026-02-28").open).toHaveLength(0);
    expect(w.closedGapsAsOf([DAYS[0]], "2026-03-02").open).toHaveLength(1);
  });

  it("stops being a gap once something is filed or filled into it", () => {
    const w = load();
    const late = {...DAYS[0], filedAt: "2026-03-05T02:00:00+00:00"};
    expect(w.closedGapsAsOf([late], "2026-03-04").open).toHaveLength(1);
    expect(w.closedGapsAsOf([late], "2026-03-05").open).toHaveLength(0);
  });

  it("is accepted, not open, from the day a person marks it", () => {
    const w = load();
    const marked = {...DAYS[0], markedAt: "2026-03-07T02:00:00+00:00",
                    mark: {at: "2026-03-07T02:00:00+00:00", actor: "k@x", reason: "supplier outage"}};
    expect(w.closedGapsAsOf([marked], "2026-03-06").open).toHaveLength(1);
    const after = w.closedGapsAsOf([marked], "2026-03-08");
    expect(after.open).toHaveLength(0);
    expect(after.accepted).toHaveLength(1);
  });
});

describe("consecutive gaps are one item", () => {
  it("groups by schedule position and breaks on anything between", () => {
    const w = load();
    const groups = w.groupGaps([...DAYS, LATER_DAY]);
    expect(groups.map(g => g.periods)).toEqual([
      ["2026-03-01", "2026-03-02", "2026-03-03"], ["2026-03-09"]]);
    expect(w.gapText(groups[0])).toMatch(/^3 days with no supply, /);
    expect(w.gapText(w.groupGaps([slot("2024-Q2", 3)])[0])).toBe("1 period with no supply, 2024-Q2");
  });
});

describe("a dataset with an unmarked gap is red, an accepted one is not", () => {
  const dataset = (extra) => ({columns: [{status: "green", checks: []}], ...extra});

  it("rolls an unmarked gap up as red", () => {
    const w = load();
    expect(w.rollup([dataset({noSupply: [{periods: ["x"]}]}), dataset({})])).toBe("red");
    expect(w.rollup([dataset({noSupply: [{periods: ["x"]}], noDataAsOf: true, columns: []})])).toBe("red");
  });

  it("keeps an accepted gap out of the red", () => {
    const w = load();
    expect(w.rollup([dataset({acceptedGaps: [{periods: ["x"]}]})])).toBe("green");
  });
});

describe("the agency card says it in one line, broken out by kind", () => {
  const HELD = {kind: "held-supply", severity: "needs-action", blocking: true,
                agencyId: "dcp", collectionId: "child-protection", datasetId: "cp-clients"};
  const GAP_ITEM = {...HELD, kind: "closed-unfilled-slot", blocking: false};
  const source = {items: [HELD, GAP_ITEM], blockers: []};

  it("counts gaps as at the date on show in place of the queue's own", () => {
    const w = load();
    const html = w.outstandingMarker("agency", "dcp", source, 2);
    expect(html).toContain("3 things waiting for a person: 2 no supply, 1 held supply");
  });

  it("is silent with nothing waiting", () => {
    const w = load();
    expect(w.outstandingMarker("agency", "dcp", {items: [], blockers: []}, 0)).toBe("");
  });

  it("shows accepted gaps quietly, in words", () => {
    const w = load();
    expect(w.acceptedGapsMarker(2)).toContain("2 datasets with a period accepted as not supplied");
    expect(w.acceptedGapsMarker(0)).toBe("");
  });
});

describe("a period whose supply was rejected (REQ-PIPE-153 criterion 9)", () => {
  const REJECTED = slot("2025-Q2", 5, {closesAt: "2025-08-15T16:00:00+00:00",
    rejected: {supply: "cp-clients@k", receivedAt: "2025-05-02T02:00:00+00:00",
               at: "2025-09-01T02:00:00+00:00", actor: "Keith Moss",
               reason: "supplier is resending", failedLoad: true}});

  it("was waiting, not a gap, until the rejection", () => {
    const w = load();
    expect(w.closedGapsAsOf([REJECTED], "2025-08-20").open).toHaveLength(0);
    expect(w.closedGapsAsOf([REJECTED], "2025-09-01").open).toHaveLength(1);
  });

  it("says what happened to the supply, naming who and why", () => {
    const w = load();
    const [group] = w.groupGaps([REJECTED, slot("2025-Q3", 6)]);
    expect(group.periods).toEqual(["2025-Q2"]);
    const text = w.gapText(group);
    expect(text).toContain("a supply arrived, could not be loaded and was rejected by Keith Moss");
    expect(text).toContain("supplier is resending");
  });
});
