// REQ-PIPE-438's CORRECTNESS NFR, the page's half: which datasets COUNT.
//
// Every row comes from status-cases.json's `counted_cases`, which
// tests/test_counted_parity.py holds the Python implementations to - the
// recorded state, the cross-table sharing, dataset_status.py's rollup. Here
// the page's own inNoRollup, rollup, unagreedMarker and column status
// (buildRealDataset) answer the same rows.
import { readFileSync } from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";
import { afterEach, describe, expect, it } from "vitest";
import { loadDashboard } from "./support/loadDashboard.js";

const __dirname = path.dirname(fileURLToPath(import.meta.url));
const COUNTED = JSON.parse(
  readFileSync(path.join(__dirname, "..", "status-cases.json"), "utf8"),
).counted_cases;
const BY_ID = Object.fromEntries(COUNTED.datasets.map((d) => [d.id, d]));

let dashboard;
afterEach(() => {
  dashboard?.close();
  dashboard = undefined;
});
function load() {
  dashboard = loadDashboard();
  return dashboard.window;
}
function page(id, status) {
  const base = { id, name: id, ...BY_ID[id].page };
  if (status === "notyetchecked") return { ...base, notYetChecked: true, columns: [] };
  return { ...base, columns: [{ name: "a", status }] };
}
function check(status, extra) {
  return { name: status, current: status === "red" ? 9 : 0, warn: 0, fail: 0,
    current_status: status, retired: false, ...extra };
}

it("the table is not empty", () => {
  expect(COUNTED.datasets.length && COUNTED.cross_table.length && COUNTED.rollups.length)
    .toBeTruthy();
});

describe.each(COUNTED.datasets)("$id", (row) => {
  it("is left out of the rollup as the table says", () => {
    expect(load().inNoRollup(page(row.id, "red"))).toBe(!row.counted);
  });
  it("carries the no-schedule marker only where the table says", () => {
    expect(load().unagreedMarker(page(row.id, "red")) !== "").toBe(row.marker);
  });
});

describe.each(COUNTED.rollups)("rollup $id", (row) => {
  it("rolls up as the table says", () => {
    expect(load().rollup(row.datasets.map(([id, s]) => page(id, s)))).toBe(row.expect);
  });
});

describe.each(COUNTED.cross_table)("cross-table $id", (row) => {
  it("counts only where the table says, in the page's column status", () => {
    const w = load();
    for (const id of row.shown_on) {
      const marked = row.not_counted_on.includes(id);
      const column = { name: "(cross-table)", checks: [check("green"),
        check("red", marked ? { notCountedHere: true } : {})] };
      expect(w.columnStatus(column, page(id, "green"))).toBe(marked ? "green" : "red");
    }
  });
});
