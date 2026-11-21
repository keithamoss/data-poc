// The browser half of the shared run-time format (REQ-TEST-416 criterion 4).
//
// Every case comes from duration-cases.json at the repo root, which neither
// this suite nor tests/test_duration_cases.py owns - as display-time-cases
// and status-cases are held.
import { readFileSync } from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";
import { afterAll, beforeAll, describe, expect, it } from "vitest";
import { loadDashboard } from "./support/loadDashboard.js";

const __dirname = path.dirname(fileURLToPath(import.meta.url));
const CASES = JSON.parse(
  readFileSync(path.join(__dirname, "..", "duration-cases.json"), "utf8"),
).cases;

let dashboard;
beforeAll(() => { dashboard = loadDashboard(); });
afterAll(() => dashboard?.close());

describe("every run-time case", () => {
  it("the table is not empty", () => {
    expect(CASES.length).toBeGreaterThanOrEqual(10);
  });
  for (const c of CASES) {
    it(`${c.id} reads the way the table says`, () => {
      expect(dashboard.window.fmtElapsed(c.seconds)).toBe(c.expect);
    });
  }
});
