// A period standing in on an earlier one (REQ-DASH-085, REQ-DASH-100).
//
// The failure is a GREEN THAT MEANS SOMETHING ELSE. A period whose
// table is a view onto an earlier supply passes every check that supply
// passed - correctly, because it IS that data - so it reads as an
// ordinary healthy period and the one thing a reader needs to know
// about it is invisible.
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

function ds(standingIn) {
  return { id: "cp-carers", status: "green", promotionState: { standingIn } };
}

const SUBSTITUTED = {
  kind: "substituted", level: "warning", period: "2026-Q3", standsOn: "2026-Q2",
  supply: "cp-carers@202605010100000000", decidedBy: "Keith", byAPerson: true,
  reason: "the supplier confirmed no extract will be sent for this quarter",
};

const INHERITED = {
  kind: "inherited", level: "information", period: "2026-Q3", standsOn: "2026-Q1",
  supply: "cp-carers@202602010100000000", decidedBy: null, byAPerson: false,
  reason: "carers are supplied annually, so no quarterly file is due",
};

describe("standingInMarker", () => {
  it("renders nothing for a period holding its own supply", () => {
    const w = load();
    expect(w.standingInMarker(ds(null))).toBe("");
    expect(w.standingInMarker({ id: "x" })).toBe("");
  });

  it("uses the word substituted, distinctly from inherited", () => {
    const w = load();
    const html = w.standingInMarker(ds(SUBSTITUTED));
    expect(html).toContain("Substituted");
    expect(html).not.toContain("Inherited");
  });

  it("uses the word inherited, distinctly from substituted", () => {
    const w = load();
    const html = w.standingInMarker(ds(INHERITED));
    expect(html).toContain("Inherited");
    expect(html).not.toContain("Substituted");
  });

  it("names the period the data came from in the LABEL, not only on hover", () => {
    // Hover is not available to every reader or every device, and
    // "where did this data come from" is the question the qualifier
    // exists to answer.
    const w = load();
    expect(w.standingInMarker(ds(SUBSTITUTED))).toContain("2026-Q2");
    expect(w.standingInMarker(ds(INHERITED))).toContain("2026-Q1");
  });

  it("names who decided a substitution in the tooltip", () => {
    const w = load();
    expect(w.standingInMarker(ds(SUBSTITUTED))).toContain("decided by Keith");
  });

  it("says an inheritance was automatic, naming nobody", () => {
    // Naming the rule as though it were a person would put a decision
    // on somebody who never made one.
    const w = load();
    const html = w.standingInMarker(ds(INHERITED));
    expect(html).toContain("no person decided it");
    expect(html).not.toContain("decided by");
  });

  it("carries the two apart by CLASS as well as by word", () => {
    const w = load();
    expect(w.standingInMarker(ds(SUBSTITUTED))).toContain("standing-in substituted");
    expect(w.standingInMarker(ds(INHERITED))).toContain("standing-in inherited");
  });

  it("introduces no new status value", () => {
    // The verdict is whatever the checks found; this sits BESIDE it.
    const w = load();
    for (const st of [SUBSTITUTED, INHERITED]) {
      expect(w.STATUS_ORDER ? Object.keys(w.STATUS_ORDER) : []).not.toContain(st.kind);
    }
  });
});

describe("standingInDetail", () => {
  it("renders nothing for a period holding its own supply", () => {
    const w = load();
    expect(w.standingInDetail(ds(null))).toBe("");
  });

  it("names the period being viewed and the one the data came from", () => {
    const w = load();
    const html = w.standingInDetail(ds(SUBSTITUTED));
    expect(html).toContain("2026-Q3");
    expect(html).toContain("2026-Q2");
  });

  it("shows the reason AS WRITTEN, not summarised", () => {
    // The reason is the only part a person actually authored, and a
    // generic phrase in its place is the page claiming somebody
    // explained themselves when nobody did.
    const w = load();
    expect(w.standingInDetail(ds(SUBSTITUTED))).toContain(SUBSTITUTED.reason);
    expect(w.standingInDetail(ds(INHERITED))).toContain(INHERITED.reason);
  });

  it("names who decided a substitution", () => {
    const w = load();
    expect(w.standingInDetail(ds(SUBSTITUTED))).toContain("Decided by Keith");
  });

  it("says an inheritance had no decider", () => {
    const w = load();
    const html = w.standingInDetail(ds(INHERITED));
    expect(html).toContain("no person decided it");
  });

  it("escapes a reason somebody typed, rather than trusting it", () => {
    const w = load();
    const html = w.standingInDetail(ds({ ...SUBSTITUTED,
      reason: 'they said <b>"do it"</b>' }));
    expect(html).toContain("&lt;b&gt;");
    expect(html).not.toContain("<b>");
  });

  it("escapes a quote inside the marker's tooltip", () => {
    const w = load();
    const html = w.standingInMarker(ds({ ...SUBSTITUTED, decidedBy: 'a "person"' }));
    expect(html).toContain("&quot;");
  });
});
