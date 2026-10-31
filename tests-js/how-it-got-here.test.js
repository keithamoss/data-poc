// REQ-DASH-230 - the supply-history row's last column is headed 'How it got
// here' and holds how a supply came to be in its cycle; the Timing cell keeps
// punctuality only. Each note is found by its column's HEADING TEXT, never by
// position (criterion 10), and asserted absent from the other cell.
import { describe, it, expect } from "vitest";
import { loadDashboard } from "./support/loadDashboard.js";

const MOVED = {original: "late", new: "on_time", reference: "CAB-1", approver: "Keith",
               appliedAt: "2026-10-11T09:00:00+08:00", movedFrom: "2023-Q3", movedTo: "2023-Q2"};
const REJUDGED = {original: "late", new: "on_time", reference: "CAB-2", approver: "Keith",
                  appliedAt: "2026-10-11T09:00:00+08:00"};
const KEPT = {reference: "CAB-3", reason: "genuinely Q3 data", period: "2023-Q3",
              actor: "Keith", at: "2026-10-11T01:00:00+00:00"};
const EXCUSED = {at: "2026-03-05T01:00:00+00:00", actor: "Keith", reason: "the supplier's outage",
                 slot: "2026-Q1", withdrawn: null, lapsed: null, lapsedAt: null};

function page(entry, raw, {notes = true} = {}){
  const w = loadDashboard().window;
  w.rawRealDatasetById = () => raw;
  w.CURRENT_IN_PLACE_ON = "2026-12-31";
  // The three notes whose inputs are whole subsystems of their own, each with
  // its own tests, stand in here by their real markers.
  if(notes){
    w.settledNote = () => `<div data-settled-from>From two files for one table, settled by Keith</div>`;
    w.stillOwedNote = () => `<div data-still-owed>2023-Q3 was still owed after the turn-off</div>`;
    w.placedTag = () => `<span data-placed>Placed in 2023-Q3</span>`;
  }
  const html = `<table><thead>${w.eval("SUPPLY_CYCLE_HEAD")}</thead><tbody>${
    w.renderSupplyCycleRows([entry], "cp-clients", "2023-07-01")}</tbody></table>`;
  const doc = new w.DOMParser().parseFromString(html, "text/html");
  const heads = [...doc.querySelectorAll("thead th")].map(th => th.textContent.trim());
  const cell = name => doc.querySelectorAll("tbody td")[heads.indexOf(name)];
  return {heads, timing: cell("Timing"), how: cell("How it got here")};
}

const FIRST = {run_id: "r1", run_date: "2023-08-01", status: "green", arrivalStatus: "late",
               arrivedAt: "2023-08-01T04:00:00+00:00",
               filedBy: {kind: "person", route: "folder", who: "Keith Moss"},
               statedOriginal: "2023-07-20T10:00:00+08:00"};
const RAW = {runs: [], excuses: {r1: [EXCUSED]},
             corrections: {rejudged: {r1: [MOVED, REJUDGED]}, kept: {r1: [KEPT]}, awaiting: []}};

describe("the heading (criteria 1 and 2)", () => {
  it("is 'How it got here', the last of six headed columns", () => {
    const {heads} = page(FIRST, RAW);
    expect(heads).toEqual(["Arrived", "Status", "Timing", "Rows", "Outcome", "How it got here"]);
  });
});

describe("each note in its own cell (criteria 3, 4, 5 and 6)", () => {
  const HOW = ["[data-placed]", "[data-settled-from]", "[data-still-owed]", "[data-corrected-move]",
               "[data-kept]", ".filed-note"];
  const TIMING = ["[data-excuse]", "[data-rejudged]", "[data-stated-original]"];

  it("puts how it got here under 'How it got here' and nowhere in Timing", () => {
    const {timing, how} = page(FIRST, RAW);
    for(const sel of HOW){
      expect(how.querySelector(sel), sel).not.toBeNull();
      expect(timing.querySelector(sel), sel).toBeNull();
    }
  });

  it("keeps punctuality in Timing and nowhere under 'How it got here'", () => {
    const {timing, how} = page(FIRST, RAW);
    for(const sel of TIMING){
      expect(timing.querySelector(sel), sel).not.toBeNull();
      expect(how.querySelector(sel), sel).toBeNull();
    }
    expect(timing.textContent).toContain("Late at the time");
    expect(how.textContent).not.toContain("Late at the time");
  });

  it("splits a hand filing: who in 'How it got here', the stated original beside the receipt", () => {
    const {timing, how} = page(FIRST, RAW);
    expect(how.textContent).toContain("Keith Moss");
    expect(how.textContent).not.toContain("(stated)");
    expect(timing.textContent).toContain("(stated)");
  });

  it("splits a correction's move: the move in 'How it got here', 'Late at the time' in Timing", () => {
    const {timing, how} = page(FIRST, RAW);
    const move = how.querySelector("[data-corrected-move]").textContent;
    expect(move).toContain("moved to");
    expect(move).toContain("by correction CAB-1, approved by Keith");
    expect(timing.textContent).not.toContain("moved to");
  });

  it("carries the resupply badge in 'How it got here'", () => {
    const {timing, how} = page({...FIRST, isResupply: true, attemptNumber: 2, daysSincePrevious: 3}, RAW);
    expect(how.textContent).toContain("Resupply, attempt 2");
    expect(timing.textContent).not.toContain("Resupply, attempt");
    expect(timing.textContent).toContain("3 days since previous");
    // Its stated original, beside it (post-build-review #201 F5).
    expect(timing.querySelector("[data-stated-original]")).not.toBeNull();
    expect(how.textContent).toContain("Keith Moss");
  });
});

describe("an automated first arrival (criterion 7)", () => {
  it("leaves 'How it got here' empty, with no placeholder", () => {
    const w = loadDashboard().window;
    const {how} = page({run_id: "r9", run_date: "2023-08-01", status: "green",
                        arrivalStatus: "on_time", arrivedAt: "2023-08-01T04:00:00+00:00",
                        filedBy: {kind: "automated"}},
                       {runs: [], corrections: {rejudged: {}, kept: {}, awaiting: []}},
                       {notes: false});
    expect(how.textContent.trim()).toBe("");
    expect(w).toBeTruthy();
  });
});
