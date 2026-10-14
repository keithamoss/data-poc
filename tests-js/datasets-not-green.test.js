// REQ-DASH-226 criterion 11: an agency card and a collection heading count
// how many of their datasets are not green - judged by each dataset's own
// full status - and draw a weekly red/amber trend from the same per-date
// statuses. Written first.
import { afterEach, describe, expect, it } from "vitest";
import { loadDashboard } from "./support/loadDashboard.js";

let dashboard;
afterEach(() => {
  dashboard?.close();
  dashboard = undefined;
});
const load = () => (dashboard = loadDashboard()).window;
const text = (w, html) => {
  const el = w.document.createElement("div");
  el.innerHTML = html;
  return el.textContent.replace(/\s+/g, " ").trim();
};

// One red, one amber, one green, and one with no schedule agreed, which the
// rollup leaves out.
const FOUR = [
  { id: "a", status: "red" },
  { id: "b", status: "amber" },
  { id: "c", status: "green" },
  { id: "d", status: "green", scheduleNotAgreed: true },
];

describe("the datasets-not-green line", () => {
  it("counts only what the rollup counts, and says so", () => {
    const w = load();
    const t = text(w, w.datasetsNotGreenLine(FOUR, "red"));
    expect(t).toContain("2 of 3 counted datasets not green");
    expect(t).toContain("1 red, 1 amber");
  });

  it("drops 'counted' when the rollup leaves nothing out, and never shows a bare 0", () => {
    const w = load();
    expect(text(w, w.datasetsNotGreenLine(FOUR.slice(0, 3), "red"))).toContain("2 of 3 datasets not green");
    expect(text(w, w.datasetsNotGreenLine([FOUR[2]], "green"))).toBe("All 1 datasets green");
    expect(text(w, w.datasetsNotGreenLine([FOUR[2], FOUR[3]], "green"))).toBe("All 1 counted datasets green");
  });

  it("shows nothing for a group whose status is Not counted", () => {
    const w = load();
    expect(w.datasetsNotGreenLine([FOUR[3]], "notcounted")).toBe("");
  });
});

describe("the weekly trend", () => {
  const on = (dateStr) => new Map([
    ["a", { status: dateStr >= "2026-03-01" ? "red" : "green", inRollup: true }],
    ["b", { status: "amber", inRollup: true }],
    ["c", { status: "green", inRollup: true }],
    ["d", { status: "green", inRollup: false }],
  ]);

  it("steps back a week at a time from the date on show to the first week with a QA run", () => {
    const w = load();
    const series = w.groupWeeklySeries(["a", "b", "c", "d"], "2026-02-10", "2026-03-10", on);
    expect(series.map((p) => p.dateStr)).toEqual(["2026-02-10", "2026-02-17", "2026-02-24", "2026-03-03", "2026-03-10"]);
    const last = series[series.length - 1];
    expect([last.counted, last.red, last.amber]).toEqual([3, 1, 1]);
    expect([series[0].red, series[0].amber]).toEqual([0, 1]);
  });

  it("gives a collection heading the same points as a card over the same datasets", () => {
    const w = load();
    const card = w.groupWeeklySeries(["a", "b", "c", "d"], "2026-02-10", "2026-03-10", on);
    const heading = w.groupWeeklySeries(["d", "c", "b", "a"], "2026-02-10", "2026-03-10", on);
    expect(heading.map((p) => [p.dateStr, p.counted, p.red, p.amber]))
      .toEqual(card.map((p) => [p.dateStr, p.counted, p.red, p.amber]));
  });

  it("is labelled in words, by week", () => {
    const w = load();
    const series = w.groupWeeklySeries(["a", "b", "c", "d"], "2026-02-10", "2026-03-10", on);
    const html = w.datasetsTrendHtml(series);
    expect(text(w, html)).toContain("Datasets red and amber, each week");
    expect(html).toContain('aria-label="Datasets red and amber each week, 5 weeks from 10 Feb 2026 to 10 Mar 2026; latest 1 red and 1 amber of 3"');
  });
});
