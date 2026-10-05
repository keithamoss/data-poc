// REQ-DASH-097 - file-check results read as claims about the file, in a
// section of their own, never folded into a data check's status.
import { describe, it, expect } from "vitest";
import { loadDashboard } from "./support/loadDashboard.js";

function point(attempt, day, status, finding){
  return {run_id: "r" + attempt, run_date: day, receivedAt: day + "T09:00:00+08:00", status,
          finding: finding || "fine", filename: "carers.csv", delivery: "d", attempt};
}
function fileChecks(rows){
  return {key: "_file", name: "The file as delivered", scope: "file", checks: [
    {key: "encoding_file", name: "Text encoding", severity: "failure", history: rows.map(r => r[0])},
    {key: "fields_per_row_file", name: "Fields per row", severity: "failure", history: rows.map(r => r[1])},
    {key: "column_order_file", name: "Column order", severity: "warning", history: rows.map(r => r[2])},
  ]};
}
function withFileChecks(fc){
  const w = loadDashboard().window;
  w.rawRealDatasetById = () => ({id: "cp-carers", fileChecks: fc});
  return w;
}

describe("the file attempt on show", () => {
  const fc = fileChecks([
    [point(1, "2026-01-10", "green"), point(1, "2026-01-10", "red", "line 3 has 2 fields"), point(1, "2026-01-10", "green")],
    [point(2, "2026-02-10", "green"), point(2, "2026-02-10", "green"), point(2, "2026-02-10", "green")],
  ]);

  it("is the newest file received on or before the date on show", () => {
    const w = withFileChecks(fc);
    expect(w.fileAttemptInPlaceOn(fc, "2026-01-20").attempt).toBe(1);
    expect(w.fileAttemptInPlaceOn(fc, "2026-02-20").attempt).toBe(2);
    expect(w.fileAttemptInPlaceOn(fc, "2026-01-01")).toBe(null);
  });

  it("shows a refused file with the failed check open and named", () => {
    const w = withFileChecks(fc);
    const html = w.fileSectionHtml({id: "cp-carers"}, "2026-01-20");
    expect(html).toContain('data-file-outcome="refused"');
    expect(html).toContain("Line 3 has 2 fields.");
    expect(html).toContain("File check");
    expect(html).toContain("carers.csv");
  });

  it("collapses to one line when every check passed (criterion 5)", () => {
    const w = withFileChecks(fc);
    const html = w.fileSectionHtml({id: "cp-carers"}, "2026-02-20");
    expect(html).toContain('data-file-outcome="passed"');
    expect(html).toContain("All 3 file checks passed");
    expect(html).toMatch(/<details class="file-passed">/);
  });

  it("says a warning leaves the dataset's status unchanged (criterion 7)", () => {
    const warned = fileChecks([[point(1, "2026-01-10", "green"), point(1, "2026-01-10", "green"),
                                point(1, "2026-01-10", "amber", "the columns are not in the contract's order")]]);
    const w = withFileChecks(warned);
    const html = w.fileSectionHtml({id: "cp-carers"}, "2026-01-20");
    expect(html).toContain('data-file-outcome="warned"');
    expect(html).toContain("status is unchanged");
  });

  it("renders nothing for a dataset with no file checks recorded", () => {
    const w = withFileChecks(null);
    expect(w.fileSectionHtml({id: "cp-carers"}, "2026-01-20")).toBe("");
  });
});
