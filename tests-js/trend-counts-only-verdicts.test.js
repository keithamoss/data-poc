// post-build-review #181 (found by delivery-scoper scoping road-testing
// sprint 1, 2026-10-14; Keith: "fix now, test-first").
//
// THE TREND COUNTED CHECKS NOBODY JUDGED AS FAILING. aggregateFailureSeries()
// treated every status other than green as a failure, so a check with no
// rule for the period (inactive) or not run for it (nodata) pushed the line
// up. On the real Child Protection data every dataset's latest point plotted
// a failing share - cp-notifications 2 of 45 - with no amber or red result at
// all, and a line scaled to its own maximum drew that near the top of its
// box under a green dot.
//
// Only a verdict that something is wrong - amber or red - is "not green";
// a check that was not judged is in neither the count nor the total.
import { afterEach, describe, expect, it } from "vitest";
import { loadDashboard } from "./support/loadDashboard.js";

let dashboard;
afterEach(() => {
  dashboard?.close();
  dashboard = undefined;
});

const d = (iso) => new Date(iso + "T00:00:00Z");
const col = (...statuses) => ({
  name: "c",
  checks: statuses.map((s) => ({ history: [{ date: d("2026-01-01"), status: s }] })),
});

describe("aggregateFailureSeries", () => {
  it("does not count an inactive or unjudged check as failing", () => {
    const w = (dashboard = loadDashboard()).window;
    const [point] = w.aggregateFailureSeries([col("green", "green", "inactive", "nodata")]);
    expect(point.rate).toBe(0);
  });

  it("counts amber and red over the checks that were judged", () => {
    const w = (dashboard = loadDashboard()).window;
    const [point] = w.aggregateFailureSeries([col("green", "amber", "red", "green", "nodata", "inactive")]);
    expect(point.rate).toBe(2 / 4);
  });

  it("reads a date on which nothing was judged as nothing failing", () => {
    const w = (dashboard = loadDashboard()).window;
    const [point] = w.aggregateFailureSeries([col("nodata", "inactive")]);
    expect(point.rate).toBe(0);
  });
});
