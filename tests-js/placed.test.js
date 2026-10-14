// REQ-DASH-175: a supply a person placed into a period says so - who, when,
// why - in the cell that says how its row came to be in its cycle, from the
// placement's own instant, never in the timing cell beside an excuse.
import { afterEach, describe, expect, it } from "vitest";
import { loadDashboard } from "./support/loadDashboard.js";

let dashboard;
afterEach(() => { dashboard?.close(); dashboard = undefined; });
const load = () => (dashboard = loadDashboard()).window;

const PLACED = { period: "2026-Q1", at: "2026-03-10T02:00:00+00:00", actor: "Keith Moss",
                 reason: "the supplier's Q1 file", when: "closed", runId: "r1" };
const raw = (extra = {}) => ({ id: "cp-clients", placements: { "cp-clients@a": PLACED }, ...extra });

describe("the placement tag (criteria 1, 2 and 5)", () => {
  it("names the period, the person, the date and the reason as text", () => {
    const w = load();
    const html = w.placedTag(raw(), "r1", "2026-03-11");
    const el = w.document.createElement("div");
    el.innerHTML = html;
    const text = el.textContent.replace(/\s+/g, " ");
    expect(text).toContain("Placed in");
    expect(text).toContain("Keith Moss");
    expect(text).toContain(w.fmtDay("2026-03-10"));
    expect(text).toContain("the supplier's Q1 file");
    expect(text).toContain("closed when it arrived");
  });

  it("says 'not yet open' where it was, and nothing where it was open", () => {
    const w = load();
    const early = raw({ placements: { "cp-clients@a": { ...PLACED, when: "not-yet-open" } } });
    expect(w.placedTag(early, "r1", "2026-03-11")).toContain("not yet open when it arrived");
    const open = raw({ placements: { "cp-clients@a": { ...PLACED, when: null } } });
    expect(w.placedTag(open, "r1", "2026-03-11")).not.toContain("when it arrived");
  });

  it("is shown only from the placement's own instant", () => {
    const w = load();
    expect(w.placedTag(raw(), "r1", "2026-03-09")).toBe("");
  });

  it("renders the reason as text", () => {
    const w = load();
    const bad = raw({ placements: { "cp-clients@a": { ...PLACED, reason: "<b>x</b>" } } });
    expect(w.placedTag(bad, "r1", "2026-03-11")).toContain("&lt;b&gt;x&lt;/b&gt;");
  });
});

describe("a hold resolved by placing (criteria 3 and 10)", () => {
  it("says where it went, who and when", () => {
    const w = load();
    const note = w.placedHoldNote(raw(), "cp-clients@a", "2026-03-11");
    expect(note).toContain("placed in");
    expect(note).toContain("Keith Moss");
    expect(note).toContain("the supplier's Q1 file");
    expect(w.placedHoldNote(raw(), "cp-clients@a", "2026-03-09")).toBe("");
    expect(w.placedHoldNote(raw(), "cp-clients@other", "2026-03-11")).toBe("");
  });
});

describe("a past decision in words (criterion 7)", () => {
  it("says 'placed in <period>' for a placement, never 're-filed'", () => {
    const w = load();
    const said = w.decisionWords({ action: "refile", placedIn: "2026-Q1" });
    expect(said).toBe(`placed in ${w.fmtPeriodOrDay("2026-Q1")}`);
    expect(w.decisionWords({ action: "refile" })).toBe("re-filed");
    expect(w.decisionWords({ action: "re-check" })).toBe("re-checked");
  });
});

describe("a placed turned-off hold stays in its quiet section (decision, with REQ-DASH-180 c14)", () => {
  it("is still listed once placed, saying where it went", () => {
    const w = load();
    const b = { kind: "held", datasetId: "cp-clients", supply: "cp-clients@a", openedAt: "2026-02-02T01:00:00+00:00",
                resolvedAt: "2026-03-10T02:00:00+00:00", turnedOff: { reason: "r" } };
    w.rawRealDatasetById = () => raw();
    const html = w.receivedWhileOffSection("cp-clients", "2026-03-11", { blockers: [b] });
    expect(html).toContain("cp-clients@a");
    expect(html).toContain("placed in");
  });
});
