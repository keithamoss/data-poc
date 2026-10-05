// REQ-DASH-133: a period that closed with no supply is red and says so in
// words; one a person accepted is quiet and names the reason; both are
// judged as at the date on show, grouped into runs, and counted on the
// agency card in one line broken out by kind.
import { describe, it, expect } from "vitest";
import { loadDashboard } from "./support/loadDashboard.js";

const load = () => loadDashboard().window;

const slot = (period, index, extra) => ({period, index,
  closesAt: `${period}T16:00:00+00:00`, changes: [], filedAt: null,
  marks: [], rejected: null, ...extra});
const DAYS = ["2026-03-01", "2026-03-02", "2026-03-03"].map((d, i) => slot(d, 10 + i));
const LATER_DAY = slot("2026-03-09", 18);

describe("what a closed slot reads as, as at the date on show", () => {
  it("is not a gap before it closes", () => {
    const w = load();
    expect(w.closedGapsInPlaceOn([DAYS[0]], "2026-02-28").open).toHaveLength(0);
    expect(w.closedGapsInPlaceOn([DAYS[0]], "2026-03-02").open).toHaveLength(1);
  });

  it("stops being a gap once something is filed or filled into it", () => {
    const w = load();
    const late = {...DAYS[0], filedAt: "2026-03-05T02:00:00+00:00"};
    expect(w.closedGapsInPlaceOn([late], "2026-03-04").open).toHaveLength(1);
    expect(w.closedGapsInPlaceOn([late], "2026-03-05").open).toHaveLength(0);
  });

  it("is a gap again once the slot is emptied after being filled (#105)", () => {
    const w = load();
    const refilled = {...DAYS[0], changes: [
      {at: "2026-03-04T02:00:00+00:00", held: true},
      {at: "2026-03-08T02:00:00+00:00", held: false}]};
    expect(w.closedGapsInPlaceOn([refilled], "2026-03-05").open).toHaveLength(0);
    expect(w.closedGapsInPlaceOn([refilled], "2026-03-09").open).toHaveLength(1);
  });

  it("drops a mark once the slot has changed after it", () => {
    const w = load();
    const s = {...DAYS[0],
      marks: [{at: "2026-03-05T02:00:00+00:00", actor: "k", reason: "r"}],
      changes: [{at: "2026-03-06T02:00:00+00:00", held: true},
                {at: "2026-03-07T02:00:00+00:00", held: false}]};
    const got = w.closedGapsInPlaceOn([s], "2026-03-08");
    expect(got.accepted).toHaveLength(0);
    expect(got.open).toHaveLength(1);
  });

  it("is accepted, not open, from the day a person marks it", () => {
    const w = load();
    const marked = {...DAYS[0],
                    marks: [{at: "2026-03-07T02:00:00+00:00", actor: "k@x", reason: "supplier outage"}]};
    expect(w.closedGapsInPlaceOn([marked], "2026-03-06").open).toHaveLength(1);
    const after = w.closedGapsInPlaceOn([marked], "2026-03-08");
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
    expect(w.rollup([dataset({noSupply: [{periods: ["x"]}], noDataInPlaceOn: true, columns: []})])).toBe("red");
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
    expect(w.closedGapsInPlaceOn([REJECTED], "2025-08-20").open).toHaveLength(0);
    expect(w.closedGapsInPlaceOn([REJECTED], "2025-09-01").open).toHaveLength(1);
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

describe("the queue is read as at the date on show (UX critic, 2026-10-05)", () => {
  const BUILD_GAP = {kind: "closed-unfilled-slot", datasetId: "d", headline: "build's own"};
  const LATER = {kind: "held-supply", datasetId: "d", observedAt: "2030-01-01T02:00:00+00:00"};
  const EARLIER = {kind: "held-supply", datasetId: "d", observedAt: "2020-01-01T02:00:00+00:00"};
  const data = {agencies: [{id: "a", collections: [{id: "c", datasets: [
    {id: "d", name: "Dataset D", noSupply: [{periods: ["2025-Q2", "2025-Q3"], lastIndex: 6, marks: []}]},
    {id: "e", name: "Dataset E", noSupply: null}]}]}]};

  it("replaces the build's closed periods with the page's own, as at the date", () => {
    const w = load();
    const items = w.inPlaceOnQueueItems([BUILD_GAP], data);
    expect(items.map(i => i.headline)).toEqual(["Dataset D: 2 periods with no supply, 2025-Q2 to 2025-Q3"]);
    expect(items[0].redsDataset).toBe(true);
  });

  it("leaves out what was observed after the date on show", () => {
    const w = load();
    w.eval("CURRENT_IN_PLACE_ON = '2026-01-01'");
    const kinds = w.inPlaceOnQueueItems([LATER, EARLIER], data).map(i => i.observedAt || "gap");
    expect(kinds).toContain(EARLIER.observedAt);
    expect(kinds).not.toContain(LATER.observedAt);
  });
});

// REQ-DASH-133, Keith 2026-10-05 (#104): a daily feed's row names today's
// late-but-open file beside an old gap.
describe("a slot late but still open", () => {
  const DS = {lateSlots: [{period: "2026-10-04", lateAt: "2026-10-04T02:00:00+00:00",
                           filedAt: null, closesAt: "2026-10-05T00:00:00+00:00"}]};
  it("is named on the day it is late and gone once it closes", () => {
    const w = load();
    expect(w.lateOpenInPlaceOn(DS, "2026-10-04").period).toBe("2026-10-04");
    expect(w.lateOpenInPlaceOn(DS, "2026-10-03")).toBeNull();
    expect(w.lateOpenInPlaceOn(DS, "2026-10-05")).toBeNull();
  });
  it("is gone once a file arrives", () => {
    const w = load();
    const filed = {lateSlots: [{...DS.lateSlots[0], filedAt: "2026-10-04T05:00:00+00:00",
                                closesAt: null}]};
    expect(w.lateOpenInPlaceOn(filed, "2026-10-04")).toBeNull();
  });
});

// Keith 2026-10-05 (UX critic #110 M2): on the build's own day the late
// slot is judged at the build instant, so yesterday's slot - closing at
// 10am today - still reads late and open at 8:52am.
describe("a late slot on the build's own day", () => {
  const SLOT = {period: "2026-10-04", lateAt: "2026-10-04T07:00:00+00:00", filedAt: null,
                closesAt: "2026-10-05T02:00:00+00:00"};
  it("is open before it closes and gone after", () => {
    const w = load();
    expect(w.lateOpenInPlaceOn({lateSlots: [SLOT]}, "2026-10-05", "2026-10-05T00:52:00+00:00").period)
      .toBe("2026-10-04");
    expect(w.lateOpenInPlaceOn({lateSlots: [SLOT]}, "2026-10-05", "2026-10-05T03:00:00+00:00")).toBeNull();
  });
});
