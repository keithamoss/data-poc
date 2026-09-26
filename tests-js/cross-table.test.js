// Cross-table checks in their own section (REQ-QAC-037 criteria 6, 7).
//
// The requirement's own NFR is CLAUDE.md's standing lesson from item
// 74: this changes the shape of a stored result, so assert at the last
// transform before the user rather than at the first one after the
// source. These cover the template's own logic; the built page is
// driven in a real browser in tests/test_dashboard_e2e.py.
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

function check(id, value) {
  return { check_id: id, key: id, name: id, label: id, warn: 1, fail: 2,
           current: value, history: [{ run_id: "r1", value }] };
}

// One collection, two datasets, both carrying THE SAME cross-table
// check - which is the real shape: the record is shared, not copied.
function collection(checksPerDataset) {
  return {
    id: "child-protection", name: "Casework Management System",
    datasets: Object.entries(checksPerDataset).map(([id, checks]) => ({
      id, name: id,
      columns: [
        { name: "a_column", checks: [check("ordinary", 0)] },
        { name: "Cross-table checks", scope: "cross-table", checks },
      ],
    })),
  };
}

describe("the section is the pattern REQ-DASH-033 established", () => {
  it("cross-table is a recognised column scope", () => {
    const w = load();
    const ds = { columns: [{ scope: "cross-table", checks: [] }, { name: "x", checks: [] }] };
    expect(w.scopedColumns(ds, "cross-table")).toHaveLength(1);
  });

  it("a scoped column is kept out of the real column grid", () => {
    // Otherwise a cp_client_id column appears on cp_carers, which has
    // no such column - the reason these are sections at all.
    const w = load();
    const ds = { columns: [{ scope: "cross-table", checks: [] }, { name: "x", checks: [] }] };
    expect(w.realColumns(ds).map((c) => c.name)).toEqual(["x"]);
  });
});

describe("the collection gathers them once", () => {
  it("dedupes a check that several datasets carry", () => {
    // Every participating dataset carries the SAME record. Listing it
    // once per table reads as several problems where there is one.
    const w = load();
    const col = collection({
      "cp-placements": [check("carer-ref", 3)],
      "cp-carers": [check("carer-ref", 3)],
    });
    const gathered = w.collectionCrossTableChecks(col);
    expect(gathered).toHaveLength(1);
    expect(gathered[0].check.check_id).toBe("carer-ref");
  });

  it("keeps genuinely different checks apart", () => {
    const w = load();
    const col = collection({
      "cp-placements": [check("carer-ref", 3)],
      "cp-notifications": [check("client-ref", 0)],
    });
    expect(w.collectionCrossTableChecks(col)).toHaveLength(2);
  });

  it("omits a retired check", () => {
    const w = load();
    const retired = { ...check("gone", 3), retired: true };
    const col = collection({ "cp-placements": [retired] });
    expect(w.collectionCrossTableChecks(col)).toHaveLength(0);
  });

  it("renders nothing at all where a collection has none", () => {
    const w = load();
    const col = { id: "civil-registration", datasets: [{ id: "birth-registrations", columns: [] }] };
    expect(w.collectionCrossTableSection({ id: "a" }, col)).toBe("");
  });

  it("the section takes the worst status among its checks", () => {
    const w = load();
    const col = collection({
      "cp-placements": [check("ok", 0), check("bad", 3)],
    });
    const html = w.collectionCrossTableSection({ id: "a" }, col);
    expect(html).toContain('data-scope="cross-table"');
    expect(html).toContain("pill red");
  });

  it("each row navigates to a dataset the check actually reads", () => {
    const w = load();
    const col = collection({ "cp-carers": [check("carer-ref", 3)] });
    const html = w.collectionCrossTableSection({ id: "child-protection-family-support" }, col);
    expect(html).toContain('"datasetId":"cp-carers"');
    expect(html).toContain('"tier":"dataset"');
  });
});

describe("the verdict folds into every participating dataset", () => {
  it("a dataset whose only failing check is a cross-table one reads red", () => {
    // Criterion 7, and the cost Keith took knowingly: cp-carers
    // declares none of these checks and goes red for one anyway.
    const w = load();
    const carers = collection({ "cp-carers": [check("carer-ref", 3)] }).datasets[0];
    const byRun = w.datasetStatusByRun(carers);
    expect(byRun.get("r1")).toBe("red");
  });

  it("a dataset with a passing cross-table check is unaffected", () => {
    // GREEN IS ABSENCE in this map - datasetStatusByRun only records a
    // run whose status is worse than green, and every consumer reads a
    // missing entry as green. Asserting `.get() === "green"` would be
    // asserting an implementation this page does not have.
    const w = load();
    const carers = collection({ "cp-carers": [check("carer-ref", 0)] }).datasets[0];
    expect(w.datasetStatusByRun(carers).has("r1")).toBe(false);
  });

  it("folding is not a special case - it works because the section is a column", () => {
    // Asserted so nobody later "tidies" the pseudo-column out of
    // `columns` into a field of its own and silently unfolds it: drop
    // the scoped column and the same dataset stops being red.
    const w = load();
    const carers = collection({ "cp-carers": [check("carer-ref", 3)] }).datasets[0];
    expect(carers.columns.filter((c) => c.scope === "cross-table")).toHaveLength(1);
    expect(w.datasetStatusByRun(carers).get("r1")).toBe("red");

    const withoutTheSection = { columns: carers.columns.filter((c) => !c.scope) };
    expect(w.datasetStatusByRun(withoutTheSection).has("r1")).toBe(false);
  });
});
