// post-build-review #57's last open item, signed off 2026-09-25
// ("yep, fix it").
//
// THE ONLY RED PIXEL IN THE VIEWPORT SAT UNDER A PILL SAYING THERE IS
// NO DATA. Where history exists but none of it is current, the card
// still painted the full sparkline ending in a red endpoint dot - 130px
// under a "No data" pill. The line itself is right and Keith has said
// so before ("no red amber and greens... but I should still be able to
// see the historical graphs"); it is the ENDPOINT that asserts "and
// this is where it stands now", which is the one thing a quiet state
// means nobody can say.
//
// A SECOND BUG IN THE SAME FUNCTION, found writing these:
// statusColorVar() is a two-branch ternary falling through to
// var(--good), so EVERY status it does not recognise - nodata,
// exhausted, inactive, and anything added later - paints green. A
// colour function whose default is "healthy" is the same false-green
// shape this project keeps finding.
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

// Two columns whose history ends badly, which is what makes the
// endpoint red in the first place. `date` is a real Date because
// aggregateFailureSeries() keys on h.date.getTime() - the first draft
// of this fixture used run ids, which threw inside jsdom and took the
// rest of the file down with it (see this file's own note at the end).
const d = (iso) => new Date(iso + "T00:00:00Z");
const COLS = [
  { name: "a", checks: [{ history: [
      { date: d("2026-01-01"), status: "green" },
      { date: d("2026-01-02"), status: "green" },
      { date: d("2026-01-03"), status: "red" }] }] },
  { name: "b", checks: [{ history: [
      { date: d("2026-01-01"), status: "green" },
      { date: d("2026-01-02"), status: "red" },
      { date: d("2026-01-03"), status: "red" }] }] },
];

describe("statusColorVar", () => {
  it("does not paint an unrecognised status green", () => {
    const w = load();
    const good = w.statusColorVar("green");
    for (const quiet of ["nodata", "exhausted", "inactive"]) {
      expect(w.statusColorVar(quiet), `${quiet} paints as healthy`).not.toBe(good);
    }
  });

  it("still paints the three verdicts as it always did", () => {
    const w = load();
    expect(w.statusColorVar("red")).toBe("var(--bad)");
    expect(w.statusColorVar("amber")).toBe("var(--warn-fill)");
    expect(w.statusColorVar("green")).toBe("var(--good)");
  });
});

describe("the sparkline endpoint under a quiet state", () => {
  it("does not assert a red verdict when nothing is current", () => {
    const w = load();
    const svg = w.aggregateSparkline(COLS, "nodata");
    expect(svg).toContain("<circle");
    expect(svg).not.toContain("var(--bad)");
  });

  it("does not assert a healthy one either", () => {
    const w = load();
    const svg = w.aggregateSparkline(COLS, "nodata");
    expect(svg).not.toContain("var(--good)");
  });

  it("treats every quiet state the same way", () => {
    const w = load();
    for (const quiet of ["nodata", "exhausted", "inactive"]) {
      const svg = w.aggregateSparkline(COLS, quiet);
      expect(svg, quiet).not.toContain("var(--bad)");
      expect(svg, quiet).not.toContain("var(--good)");
    }
  });

  it("still draws the history itself - the line is not the problem", () => {
    // Keith, on the quiet states generally: "no red amber and greens...
    // but I should still be able to see the historical graphs and
    // comparison stuff."
    const w = load();
    const quiet = w.aggregateSparkline(COLS, "nodata");
    const normal = w.aggregateSparkline(COLS);
    const pathOf = (svg) => (svg.match(/ d="([^"]+)"/) || [])[1];
    expect(pathOf(quiet)).toBe(pathOf(normal));
    expect(pathOf(quiet)).toBeTruthy();
  });

  it("leaves an ordinary dataset's endpoint exactly as it was", () => {
    // The must-not-change half.
    const w = load();
    expect(w.aggregateSparkline(COLS)).toContain("var(--bad)");
  });
});
