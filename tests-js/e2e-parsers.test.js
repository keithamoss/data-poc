// The parsers tests/test_dashboard_e2e.py reads the built page with - the
// count cells, the agency card's line and the trends' accessible names -
// held here against what the template actually emits (post-build-review:
// the Pass / Warn / Fail critic found them still expecting the old words).
// The e2e module needs a bootstrapped history to run; these do not, so each
// regex is proved on the real strings first. Keep them identical to the e2e
// module's own (Python `re` and JS RegExp agree on these patterns).
import { afterEach, describe, expect, it } from "vitest";
import { loadDashboard } from "./support/loadDashboard.js";

let dashboard;
afterEach(() => { dashboard?.close(); dashboard = undefined; });
const load = () => (dashboard = loadDashboard()).window;

const CELL = /^(\d+) of (\d+) (\d+) failing, (\d+) warning/;             // e2e :5141, :5226
const CELL_ALL = /^All (\d+) passing/;                                    // e2e :5146
const CELL_FILTER = /\d+ failing, \d+ warning/;                           // e2e :5222
const CARD = /^(\d+) of (\d+) (?:counted )?datasets? not passing (\d+) failing, (\d+) warning/; // e2e :5270
const CARD_ALL = /^All (\d+) (?:counted )?datasets? passing/;             // e2e :5275
const LATEST = /latest (\d+) failing and (\d+) warning of (\d+)/;         // e2e :5185, :5282

const d = (iso) => new Date(iso + "T00:00:00Z");
const DATES = { r1: "2026-01-01", r2: "2026-02-01" };
const unit = (name, byRun) => ({ name,
  checks: [{ history: Object.entries(byRun).map(([run_id, status]) => ({ run_id, date: d(DATES[run_id]), status })) }] });
// As the browser's innerText reads it, which the e2e module uses: a block
// element starts a new line (jsdom implements no innerText, so a div's
// boundary is put back as a space before collapsing).
const text = (w, html) => {
  const el = w.document.createElement("div");
  el.innerHTML = html.replace(/<div/g, " <div");
  return el.textContent.replace(/\s+/g, " ").trim();
};

describe("the e2e parsers read what the template emits", () => {
  it("a dataset row's count cell, and its filter", () => {
    const w = load();
    const units = [unit("a", { r1: "green", r2: "red" }), unit("b", { r1: "green", r2: "amber" }),
                   unit("c", { r1: "green", r2: "green" })];
    const t = text(w, w.columnsNotGreenCell(units));
    expect(t.match(CELL).slice(1).map(Number)).toEqual([2, 3, 1, 1]);
    expect(CELL_FILTER.test(t)).toBe(true);
    const all = text(w, w.columnsNotGreenCell([unit("a", { r1: "green", r2: "green" })]));
    expect(all.match(CELL_ALL)[1]).toBe("1");
  });

  it("an agency card's line", () => {
    const w = load();
    const ds = (id, status) => ({ id, status, inRollup: true });
    const t = text(w, w.datasetsNotGreenLine([ds("a", "red"), ds("b", "amber"), ds("c", "green")], "red"));
    expect(t.match(CARD).slice(1).map(Number)).toEqual([2, 3, 1, 1]);
    const all = text(w, w.datasetsNotGreenLine([ds("c", "green")], "green"));
    expect(all.match(CARD_ALL)[1]).toBe("1");
  });

  it("a trend's accessible name", () => {
    const w = load();
    const series = [{ runId: "r1", date: d("2026-01-01"), counted: 3, red: 0, amber: 1, sectionNames: [] },
                    { runId: "r2", date: d("2026-02-01"), counted: 3, red: 2, amber: 1, sectionNames: [] }];
    const svg = w.twoLineSparkline(series, { w: 120, h: 28 });
    const label = svg.match(/aria-label="([^"]+)"/)[1];
    expect(label.match(LATEST).slice(1).map(Number)).toEqual([2, 1, 3]);
    const big = w.unitTrendBlock(series, { kind: "dataset", title: "t", yTitle: "y", unitWord: "Columns", noun: "column" });
    expect(big.match(/aria-label="([^"]+)"/)[1].match(LATEST).slice(1).map(Number)).toEqual([2, 1, 3]);
  });
});
