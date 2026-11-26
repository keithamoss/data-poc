// post-build-review #490 F1 (Keith, 2026-11-21): under a chosen period, a
// status counts only that period's gaps and blocked supplies; each section
// card rolls up only its own collections (REQ-DASH-356 criterion 5); and the
// agencies list says a period had not opened (REQ-DASH-355 criterion 9).
import { afterEach, describe, expect, it } from "vitest";
import { MINIMAL_HIERARCHY, loadDashboard } from "./support/loadDashboard.js";

let page;
afterEach(()=> page && page.close());

const SLOTS = [
  {period: "2024-Q3", date: "2024-08-01", opens: "2024-05-01T09:00:00+08:00", due: "2024-08-01T09:00:00+08:00"},
  {period: "2024-Q4", date: "2024-11-01", opens: "2024-08-01T09:00:00+08:00", due: "2024-11-01T09:00:00+08:00"},
  {period: "2025-Q1", date: "2025-02-01", opens: "2024-11-01T09:00:00+08:00", due: "2025-02-01T09:00:00+08:00"},
];

// The queue is passed in rather than assigned: OUTSTANDING is a top-level
// const (see outstanding.test.js).
function load(){
  page = loadDashboard({hierarchy: MINIMAL_HIERARCHY});
  const w = page.window;
  w.rawRealDatasetById = id => ({id, periodSlots: {slots: SLOTS}});
  return w;
}
const src = blockers => ({items: [], blockers});

describe("a blocked supply belongs to the period its receipt was claimable for", () => {
  const held = {kind: "held", datasetId: "d", openedAt: "2024-09-10T10:00:00+08:00", resolvedAt: null};

  it("names the period whose claim window its receipt fell in", () => {
    const w = load();
    expect(w.blockerPeriod(held)).toBe("2024-Q4");
  });

  it("counts it under that period, and not under another", () => {
    const w = load();
    const all = src([held]);
    expect(w.blockerOpenInPlaceOn("d", "2025-03-01", w.periodBlockerSource("2024-Q4", all))).not.toBeNull();
    expect(w.blockerOpenInPlaceOn("d", "2025-03-01", w.periodBlockerSource("2025-Q1", all))).toBeNull();
    // With no period chosen it counts, as before.
    expect(w.blockerOpenInPlaceOn("d", "2025-03-01", all)).not.toBeNull();
  });

  it("judges a re-check by its supply's own receipt, not when its red opened", () => {
    const recheck = {kind: "could-not-check", datasetId: "d", openedAt: "2025-01-20T10:00:00+08:00",
                     receivedAt: "2024-06-01T10:00:00+08:00", resolvedAt: null};
    const w = load();
    expect(w.blockerPeriod(recheck)).toBe("2024-Q3");
  });
});

describe("several collections at once (REQ-DASH-356 criterion 5)", () => {
  it("lists an item in any of the collections, and none outside them", () => {
    const w = load();
    const items = [{collectionId: "a", kind: "x"}, {collectionId: "b", kind: "x"}, {collectionId: "c", kind: "x"}];
    const got = w.outstandingItems("collections", ["a", "b"], {items});
    expect(got.map(i=> i.collectionId)).toEqual(["a", "b"]);
  });
});
