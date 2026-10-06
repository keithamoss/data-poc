// post-build-review #129 (Keith 2026-10-07, "note that in the fine print"):
// under the example failing rows, which rows they are - and, past the number
// a tool returns, that the tool chose them rather than us.
import { describe, it, expect } from "vitest";
import { loadDashboard } from "./support/loadDashboard.js";

const load = () => loadDashboard().window;

describe("the fine print under the example failing rows", () => {
  it("says nothing when every failing row is shown", () => {
    expect(load().sampleFinePrint("dbt:not_null", 3, 3)).toBe("");
  });

  it("says dbt's are the lowest keys of all the failing rows", () => {
    expect(load().sampleFinePrint("dbt:not_null", 5, 4000)).toContain("same data always shows the same rows");
  });

  it("says the same for Soda up to the number it is asked for", () => {
    const w = load();
    expect(w.sampleFinePrint("soda:missing_count", 5, 100)).toContain("always shows the same rows");
  });

  it("says Soda chose them past that", () => {
    const w = load();
    const fp = w.sampleFinePrint("soda:missing_count", 5, 101);
    expect(fp).toContain("Soda chooses which 100");
    expect(fp).toContain("can show different rows");
  });

  it("says datacontract-cli chose them past five", () => {
    const fp = load().sampleFinePrint("datacontract:nullValues", 5, 6);
    expect(fp).toContain("datacontract-cli returned");
    expect(fp).toContain("can show different rows");
  });
});
