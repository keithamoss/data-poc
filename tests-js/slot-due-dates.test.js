// REQ-PIPE-167 criterion 5: wherever a slot's due date is shown - the
// supply-history cycle heading included - it is the slot's own due date,
// not its period's date, where the two differ. A following-period dataset
// is due weeks before its period's date; heading it with the period's date
// tells a reader the wrong day to expect the supply.
import { describe, expect, it } from "vitest";
import { loadDashboard } from "./support/loadDashboard.js";

describe("a following-period dataset's cycle heading", () => {
  it("shows the slot's own due date where it differs from the period's date", () => {
    const { window } = loadDashboard({
      slotDueDates: { "cp-early": { "2026-02-01": "2026-01-04" } },
    });
    const label = window.cycleLabel({ type: "quarterly" }, "2026-02-01", "cp-early");
    expect(label).toContain(window.fmtDay("2026-01-04"));
    expect(label).not.toContain(`Cycle starting ${window.fmtDay("2026-02-01")}`);
  });

  it("is unchanged for a dataset due on its period's own date", () => {
    const { window } = loadDashboard({ slotDueDates: {} });
    expect(window.cycleLabel({ type: "quarterly" }, "2026-02-01", "cp-clients"))
      .toBe(`Cycle starting ${window.fmtDay("2026-02-01")}`);
  });
});

// delivery-critic on REQ-PIPE-167, finding 1 (post-build-review #142): the
// heading was keyed on the period the ARRIVAL DATE falls in, not the slot
// the supply is filed to. A following-period supply arrives - on time -
// before its period's date, so it was headed with the PREVIOUS period's due
// date, reading three months late.
describe("the supply history's cycle heading for a following-period dataset", () => {
  it("is the FILED slot's, with that slot's due date", () => {
    const { window } = loadDashboard({
      slotDueDates: { "cp-clients": { "2025-08-01": "2025-06-02", "2025-11-01": "2025-09-02" } },
    });
    const d = {
      id: "cp-clients",
      sla: { cadence: { type: "quarterly" } },
      runs: [{ run_id: "r1", run_date: "2025-09-01" }],
      arrivalByRun: { r1: { slot: "2025-Q4" } },
      columns: [{ checks: [{ warn: 1, fail: 2, history: [{ run_id: "r1", run_date: "2025-09-01", value: 0 }] }] }],
    };
    const [chain] = window.buildSupplyHistory(d);
    expect(chain.cycleStart).toBe("2025-11-01");
    const label = window.cycleLabel(d.sla.cadence, chain.cycleStart, d.id);
    expect(label).toContain(window.fmtDay("2025-09-02"));
    expect(label).not.toContain(window.fmtDay("2025-06-02"));
  });
});
