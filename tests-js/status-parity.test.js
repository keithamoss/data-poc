// REQ-QAC-047 - the browser half of the shared status table.
//
// Every case comes from status-cases.json at the repo root, which
// neither this suite nor tests/test_status_parity.py owns. That is the
// point: a table either side could edit is a table either side can
// quietly bend to whatever it already does.
//
// The two implementations drifted once already (plans/qa-pipeline.md
// item 74) and the drift rendered a check with 14 real violations GREEN.
import { readFileSync } from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";
import { afterEach, describe, expect, it } from "vitest";
import { loadDashboard } from "./support/loadDashboard.js";

const __dirname = path.dirname(fileURLToPath(import.meta.url));
const CASES = JSON.parse(
  readFileSync(path.join(__dirname, "..", "status-cases.json"), "utf8"),
);

let dashboard;
afterEach(() => {
  dashboard?.close();
  dashboard = undefined;
});

function load() {
  dashboard = loadDashboard();
  return dashboard.window;
}

// STATUS_ORDER and its siblings are top-level `const` declarations in a
// classic script, so they are not window properties and cannot be read
// from here. statusVocabulary() is the page's own accessor for them -
// reading it is reading the real values, not a copy this suite keeps.
function vocab() {
  return load().statusVocabulary();
}

const withoutUnderscores = (o) =>
  Object.fromEntries(Object.entries(o).filter(([k]) => !k.startsWith("_")));

describe("the vocabulary is the one both sides agreed", () => {
  it("orders statuses exactly as the table does", () => {
    expect(vocab().ordered).toEqual(withoutUnderscores(CASES.vocabulary.ordered));
  });

  it("holds the same unorderable statuses as the table", () => {
    expect([...vocab().unordered].sort()).toEqual(
      Object.keys(withoutUnderscores(CASES.vocabulary.unordered)).sort(),
    );
  });

  it("lets a check carry exactly what the table says it may", () => {
    expect([...vocab().check].sort()).toEqual(
      [...CASES.vocabulary.by_level.check].sort(),
    );
  });

  it("lets a dataset carry exactly what the table says it may", () => {
    expect([...vocab().dataset].sort()).toEqual(
      [...CASES.vocabulary.by_level.dataset].sort(),
    );
  });

  it("lets a check carry strictly less than a dataset", () => {
    // The scoping is only worth having if it is real. If the two levels
    // ever accept the same set, the distinction has quietly collapsed
    // and a dataset-level status on a check renders again.
    const v = vocab();
    expect(v.check.length).toBeLessThan(v.dataset.length);
    for (const s of v.check) expect(v.dataset).toContain(s);
  });

  it("gives every status the table names a label to render", () => {
    // A status with no label renders "undefined" in a pill, which is a
    // different way of saying nothing went wrong.
    const labels = vocab().labels;
    for (const s of CASES.vocabulary.by_level.dataset) {
      expect(labels[s], `no label for "${s}"`).toBeTruthy();
    }
  });
});

describe("every check case", () => {
  for (const c of CASES.check_cases.filter((x) => !x.expect_error)) {
    it(`${c.id} returns what the table says`, () => {
      const w = load();
      expect(w.checkStatus(c.check), c.why).toBe(c.expect);
    });
  }

  for (const c of CASES.check_cases.filter((x) => x.expect_error)) {
    it(`${c.id} fails loudly rather than guessing`, () => {
      const w = load();
      expect(() => w.checkStatus(c.check), c.why).toThrow();
    });
  }
});

describe("every rollup case", () => {
  for (const c of CASES.rollup_cases.filter((x) => !x.expect_error)) {
    it(`${c.id} returns what the table says`, () => {
      const w = load();
      expect(w.worstOf(c.statuses), c.why).toBe(c.expect);
    });
  }

  for (const c of CASES.rollup_cases.filter((x) => x.expect_error)) {
    it(`${c.id} refuses rather than returning green`, () => {
      const w = load();
      expect(() => w.worstOf(c.statuses), c.why).toThrow();
    });
  }
});

describe("every retired case", () => {
  for (const c of CASES.retired_cases) {
    it(`${c.id} matches the table's filtering rule`, () => {
      const w = load();
      expect(w.isRetired(c.check), c.why).toBe(c.expect_retired);
    });
  }
});

describe("the error says enough to act on", () => {
  // A failure that does not name the value or where it was read from
  // replaces a silent wrong answer with a loud useless one. The whole
  // change here is from silently-wrong to noisily-broken, and that is
  // only worth it if the noise is diagnostic.
  it("names the status it did not recognise", () => {
    const w = load();
    expect(() =>
      w.checkStatus({ current: 0, warn: 5, fail: 10, current_status: "definitely-not-a-status" }),
    ).toThrow(/definitely-not-a-status/);
  });

  it("names where the status was read from", () => {
    const w = load();
    expect(() =>
      w.checkStatus({ current: 0, warn: 5, fail: 10, current_status: "definitely-not-a-status" }),
    ).toThrow(/current_status/);
  });

  it("says a dataset-level status on a check is the bug, not the value", () => {
    const w = load();
    expect(() =>
      w.checkStatus({ current: 0, warn: 5, fail: 10, current_status: "exhausted" }),
    ).toThrow(/dataset-level status onto a check/);
  });

  it("names the status a rollup could not order", () => {
    const w = load();
    expect(() => w.worstOf(["green", "exhausted"])).toThrow(/exhausted/);
  });
});

describe("a history entry is held to the same vocabulary", () => {
  // checkStatus and historyStatus are the same rule applied to two
  // differently-shaped records, and they are the pair that item 74's
  // fix left half-done. Guarding only one of them is how that happened.
  it("prefers its own recorded verdict", () => {
    const w = load();
    expect(w.historyStatus({ value: 0, status: "red" }, { warn: 5, fail: 10 })).toBe("red");
  });

  it("falls back to thresholds when none was recorded", () => {
    const w = load();
    expect(w.historyStatus({ value: 11 }, { warn: 5, fail: 10 })).toBe("red");
  });

  it("refuses an unrecognised one rather than passing it on", () => {
    const w = load();
    expect(() =>
      w.historyStatus({ value: 0, status: "definitely-not-a-status" }, { warn: 5, fail: 10 }),
    ).toThrow(/definitely-not-a-status/);
  });
});
