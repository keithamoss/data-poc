// REQ-DASH-263 - a correction awaiting confirmation is a Needs action item on
// each dataset page it affects, counted once per correction at collection and
// agency level, listed only from its own date (Keith, 2026-10-19).
import { describe, it, expect } from "vitest";
import { loadDashboard } from "./support/loadDashboard.js";

const PENDING = {kind: "pending-correction", severity: "needs-action", blocking: false,
  headline: "Calendar correction REQ-GEN-205-WINDOW awaits the data asset's manager",
  detail: "Declared 2026-09-24 on calendar 'daily'.", dated: "2026-09-24",
  agencyId: null, collectionId: null, datasetId: null, observedAt: null,
  responses: ["see its moves: mothman supply corrections --reference REQ-GEN-205-WINDOW"],
  affects: [
    {agencyId: "a", collectionId: "c", datasetId: "d1", name: "One"},
    {agencyId: "a", collectionId: "c", datasetId: "d2", name: "Two"}]};
const SOURCE = {items: [PENDING]};

describe("on each dataset it affects (criterion 1)", () => {
  it("is listed on an affected dataset and not on another", () => {
    const w = loadDashboard().window;
    expect(w.outstandingItems("dataset", "d1", SOURCE)).toEqual([PENDING]);
    expect(w.outstandingItems("dataset", "d2", SOURCE)).toEqual([PENDING]);
    expect(w.outstandingItems("dataset", "elsewhere", SOURCE)).toEqual([]);
  });

  it("names its reference and gives the command to see it", () => {
    const html = loadDashboard().window.outstandingItemHtml(PENDING);
    expect(html).toContain("REQ-GEN-205-WINDOW");
    expect(html).toContain("mothman supply corrections --reference REQ-GEN-205-WINDOW");
  });

  it("writes its date in the page's own style, never raw", () => {
    const w = loadDashboard().window;
    const html = w.outstandingItemHtml({...PENDING, detail: "On calendar 'daily'."});
    expect(html).toContain(`Dated ${w.fmtDay("2026-09-24")}`);
    expect(html).not.toContain("2026-09-24");
  });
});

describe("counted once per correction (criterion 2)", () => {
  it("is one item for its collection and its agency, however many datasets it affects", () => {
    const w = loadDashboard().window;
    expect(w.outstandingItems("collection", "c", SOURCE)).toHaveLength(1);
    expect(w.outstandingItems("agency", "a", SOURCE)).toHaveLength(1);
    expect(w.outstandingMarker("collection", "c", SOURCE)).toContain("1 thing waiting");
  });
});

describe("only from its own date (criterion 3)", () => {
  const data = {agencies: [{id: "a", collections: [{id: "c", datasets: [{id: "d1", name: "One"}]}]}]};

  it("is left out before the correction's date and listed from it", () => {
    const w = loadDashboard().window;
    w.blockersFor = () => [];
    w.eval("CURRENT_IN_PLACE_ON = '2026-09-23'");
    expect(w.inPlaceOnQueueItems([PENDING], data)).toEqual([]);
    w.eval("CURRENT_IN_PLACE_ON = '2026-09-24'");
    expect(w.inPlaceOnQueueItems([PENDING], data)).toEqual([PENDING]);
  });
});
