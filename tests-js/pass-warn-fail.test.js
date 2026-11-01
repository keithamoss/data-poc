// REQ-DASH-359 criterion 16: the badges, notes and sentences that print a
// STORED status read the new words - Pass / Warn / Fail, passing / warning /
// failing - and never the stored value itself. A relabel of STATUS_LABEL
// alone misses these: they used to print `promotedOn`, `verdict` and
// `status` raw ('went in red', 're-checked red after promotion').
//
// Seen failing first against the template before REQ-DASH-359.
import { afterEach, describe, expect, it } from "vitest";
import { loadDashboard } from "./support/loadDashboard.js";

let dashboard;
afterEach(() => { dashboard?.close(); dashboard = undefined; });

const RUNS = [{ run_id: "r1", run_date: "2026-01-10", supply_id: "s1" }];
const PROMOTED = { r1: [{ at: "2026-01-20T01:00:00+00:00", state: "promoted", action: "promote" }] };

function withRaw(raw) {
  dashboard = loadDashboard();
  dashboard.window.rawRealDatasetById = () => ({ id: "cp-carers", runs: RUNS, runStates: PROMOTED, ...raw });
  return dashboard.window;
}

function shown(w, html) {
  const root = w.document.createElement("div");
  root.innerHTML = html;
  return root.textContent.replace(/\s+/g, " ").trim();
}

// No stored value - green, amber, red - may be read as a status.
function noStoredValue(text) {
  expect(text).not.toMatch(/\b(green|amber|red)\b/i);
}

describe("a promoted supply turned failing", () => {
  it("reads 'Promoted, failing' and 'went in passing ... started failing'", () => {
    const w = withRaw({ promotedHealth: { r1: { promotedOn: "green", promotedAt: "2026-01-20T01:00:00+00:00",
      timeline: [{ at: "2026-01-10T01:00:00+00:00", status: "green", cause: "the arrival of Carers" },
                 { at: "2026-03-01T01:00:00+00:00", status: "red", cause: "the promote of Client Register" }] } } });
    const text = shown(w, w.redPromotedBadge("cp-carers", "r1", "2026-03-05"));
    expect(text).toContain("Promoted, failing");
    expect(text).toContain(`Went in passing, started failing ${w.fmtInstant("2026-03-01T01:00:00+00:00")}, after`);
    noStoredValue(text);
  });

  it("promoted while failing, from its stored promotedOn 'red'", () => {
    const w = withRaw({ promotedHealth: { r1: { promotedOn: "red", promotedAt: "2026-01-20T01:00:00+00:00",
      timeline: [{ at: "2026-01-25T01:00:00+00:00", status: "red", cause: "x" }] } } });
    const text = shown(w, w.redPromotedBadge("cp-carers", "r1", "2026-03-05"));
    expect(text).toContain("Promoted while failing");
    noStoredValue(text);
  });
});

describe("a promoted supply turned warning", () => {
  it("reads 'Promoted, warning' and 'Went in passing. Warning since ...'", () => {
    const w = withRaw({ promotedHealth: { r1: { promotedOn: "green", promotedAt: "2026-01-20T01:00:00+00:00",
      timeline: [{ at: "2026-01-10T01:00:00+00:00", status: "green", cause: "the arrival of Carers" },
                 { at: "2026-03-01T01:00:00+00:00", status: "amber", cause: "the arrival of Events" }] } } });
    const text = shown(w, w.amberPromotedTag("cp-carers", "r1", "2026-03-05"));
    expect(text).toContain("Promoted, warning");
    expect(text).toContain("Went in passing. Warning since the arrival of Events");
    noStoredValue(text);
  });
});

describe("a promoted supply re-checked worse", () => {
  const item = { kind: "promoted-then-rechecked", verdict: "red" };

  it("is headed 'Promoted, then failing on re-check' and counted in the count form", () => {
    const w = withRaw({});
    expect(w.outstandingKindLabel(item.kind, item)).toBe("Promoted, then failing on re-check");
    expect(w.outstandingKindLabel(item.kind, { ...item, verdict: "amber" })).toBe("Promoted, then warning on re-check");
    expect(w.markerKindLabel(item)).toBe("failing on re-check after promotion");
    expect(w.markerKindLabel({ ...item, verdict: "amber" })).toBe("warning on re-check after promotion");
    expect(w.markerKindLabel({ kind: item.kind })).toBe("worse on re-check after promotion");
  });

  it("refuses a verdict it has no word for, rather than printing it", () => {
    const w = withRaw({});
    expect(() => w.markerKindLabel({ ...item, verdict: "purple" })).toThrow(/unrecognised status/);
  });

  it("the warning tag reads 'Promoted, then warning on re-check'", () => {
    const at = "2026-02-09T02:30:00+00:00";
    const w = withRaw({ promotedHealth: { r1: { promotedOn: "green", timeline: [{ at, status: "amber" }] } },
      rechecks: { supplies: { s1: [{ at, person: "K", reason: "why", before: "green", after: "amber" }] } } });
    const text = shown(w, w.recheckedAmberTag("cp-carers", "r1", "2026-02-15"));
    expect(text).toBe("Promoted, then warning on re-check - awaiting acknowledgement");
    noStoredValue(text);
  });
});

describe("a supply-history row", () => {
  it("'Arrived <X>' says the verb form of the stored status", () => {
    const w = withRaw({ promotedHealth: { r1: { promotedOn: "green", promotedAt: "2026-01-20T01:00:00+00:00",
      timeline: [{ at: "2026-01-10T01:00:00+00:00", status: "green", cause: "the arrival of Carers" },
                 { at: "2026-03-01T01:00:00+00:00", status: "red", cause: "the promote of Client Register" }] } } });
    const root = w.document.createElement("div");
    root.innerHTML = w.supplyRowStatus("cp-carers", { run_id: "r1", status: "green" }, "2026-03-05");
    const arrived = root.querySelector("[data-arrived-as]").textContent;
    expect(arrived).toBe("Arrived passing");
    noStoredValue(arrived);
  });

  it("'Re-checked <t>: became <X>' says the label of the stored status", () => {
    const w = withRaw({});
    const e = { at: "2026-02-09T02:30:00+00:00", person: "K", reason: "our check", before: "green", after: "red" };
    const text = shown(w, w.recheckedLaterTag(e));
    expect(text).toBe(`Re-checked ${w.fmtInstant(e.at)}: became Fail - our check`);
    noStoredValue(text);
  });
});

describe("a replacement setting's value (criterion 12)", () => {
  it("is said in words, never as the raw green or green-or-amber", () => {
    const w = withRaw({});
    expect(w.replacementWords("never")).toBe("never");
    expect(w.replacementWords("green")).toBe("when passing");
    expect(w.replacementWords("green-or-amber")).toBe("when passing or warning");
    expect(() => w.replacementWords("amber")).toThrow(/unknown replacement setting/);
  });
});

// REQ-DASH-359 criterion 14: text recorded at the time is shown as recorded,
// inside an element marked for REQ-TEST-361's guard to pass over.
describe("recorded text is marked as recorded", () => {
  it("an acknowledgement's reason, as text and as a title", () => {
    dashboard = loadDashboard();
    const w = dashboard.window;
    w.rawRealDatasetById = () => ({ id: "x", acknowledgements: { r1: {
      promotedAt: "2024-07-26T01:00:00+00:00",
      acks: [{ at: "2024-07-27T01:00:00+00:00", actor: "Ana", reason: "read red, fine", withdrawn: null }] } } });
    const root = w.document.createElement("div");
    root.innerHTML = w.acknowledgementBadge("x", "r1", "2024-08-01");
    expect(root.querySelector("[data-acknowledged]").hasAttribute("data-recorded-title")).toBe(true);
    expect(root.querySelector("[data-acknowledgement-reason]").hasAttribute("data-recorded-text")).toBe(true);
  });

  it("a re-check's reason, inside the sentence that names it", () => {
    dashboard = loadDashboard();
    const root = dashboard.window.document.createElement("div");
    root.innerHTML = dashboard.window.recheckWords({ at: "2024-08-07T02:30:00+00:00", person: "K",
      reason: "it read amber" });
    expect(root.querySelector("[data-recorded-text]").textContent).toBe("it read amber");
  });

  it("an excuse's reason", () => {
    dashboard = loadDashboard();
    const root = dashboard.window.document.createElement("div");
    root.innerHTML = dashboard.window.recordedText("went red on Monday");
    expect(root.querySelector("[data-recorded-text]").textContent).toBe("went red on Monday");
  });
});
