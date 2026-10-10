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
