// What arrived versus what is promoted (REQ-DASH-056).
//
// The failure this guards is quiet in both directions. Show the split
// when the two AGREE and thirty datasets carry a section saying so,
// which is how people learn to skip a panel. Show only one of them when
// they differ and a reader takes the wrong supply for the live data -
// which is the whole distinction the requirement exists to draw.
import { afterEach, describe, expect, it } from "vitest";
import { loadDashboard } from "./support/loadDashboard.js";

let dashboard;

afterEach(() => {
  dashboard?.close();
  dashboard = undefined;
});

function load() {
  dashboard = loadDashboard();
  return dashboard.window;
}

const PROMOTED = { supply: "cp-carers@202605010100000000", period: "2026-Q2" };
const ARRIVED = { supply: "cp-carers@202608010100000000", period: "2026-Q3" };

function dataset(state) {
  return { id: "cp-carers", name: "Carer Register", promotionState: state };
}

describe("promotionSplit", () => {
  it("renders nothing at all when the latest arrival IS what is promoted", () => {
    const w = load();
    expect(w.promotionSplit(dataset({ differs: false, promoted: PROMOTED,
      arrived: PROMOTED }))).toBe("");
  });

  it("renders nothing for a dataset carrying no promotion state", () => {
    const w = load();
    expect(w.promotionSplit({ id: "cp-carers" })).toBe("");
    expect(w.promotionSplit(undefined)).toBe("");
  });

  it("shows BOTH supplies when they differ", () => {
    const w = load();
    const html = w.promotionSplit(dataset({ differs: true, promoted: PROMOTED,
      arrived: ARRIVED, explanation: "nobody has decided about it yet" }));
    expect(html).toContain(PROMOTED.supply);
    expect(html).toContain(ARRIVED.supply);
  });

  it("labels which is which, rather than leaving it to the order", () => {
    const w = load();
    const html = w.promotionSplit(dataset({ differs: true, promoted: PROMOTED,
      arrived: ARRIVED, explanation: "" }));
    expect(html).toContain("Promoted");
    expect(html).toContain("Latest arrival");
  });

  it("says why the arrival is not promoted", () => {
    const w = load();
    const html = w.promotionSplit(dataset({ differs: true, promoted: PROMOTED,
      arrived: ARRIVED, explanation: "a person rejected this supply" }));
    expect(html).toContain("a person rejected this supply");
  });

  it("says so plainly when nothing has ever been promoted", () => {
    const w = load();
    const html = w.promotionSplit(dataset({ differs: true, promoted: null,
      arrived: ARRIVED, explanation: "" }));
    expect(html).toContain("Nothing promoted yet");
  });

  it("copes with an arrival filed to no period at all", () => {
    const w = load();
    const html = w.promotionSplit(dataset({ differs: true, promoted: PROMOTED,
      arrived: { supply: "cp-carers@x", period: null }, explanation: "" }));
    expect(html).toContain("not filed to any period");
  });
});

describe("fmtPeriodName", () => {
  it("leaves a quarterly name alone - it is already how somebody says it", () => {
    const w = load();
    expect(w.fmtPeriodName("2026-Q2")).toBe("2026-Q2");
  });

  it("writes a DAILY period's name in words", () => {
    // A daily calendar names its periods by the day, so the name is a
    // bare ISO date - the one thing REQ-DASH-071 says a reader never
    // sees. This mirrors display_time.format_period() on the Python
    // side; the two are the same rule in two languages.
    const w = load();
    const got = w.fmtPeriodName("2026-09-22");
    expect(got).not.toBe("2026-09-22");
    expect(got).toMatch(/September/);
  });

  it("returns the empty string for nothing", () => {
    const w = load();
    expect(w.fmtPeriodName(null)).toBe("");
    expect(w.fmtPeriodName("")).toBe("");
  });

  it("leaves a name it does not recognise as it is", () => {
    const w = load();
    expect(w.fmtPeriodName("Nov-Jan window")).toBe("Nov-Jan window");
  });
});
