// REQ-PIPE-341 criteria 4 and 9: a failing-row sample may be several columns,
// recorded as an ordered list per row. The compare block diffs a run's samples
// with the compared run's BY VALUE (a Set of arrays compares by reference, so
// every several-column sample read 'new'), says so where the two runs named
// their rows by different columns, and every pill is escaped - a one-column
// key included, which was interpolated raw.
import { describe, it, expect } from "vitest";
import { loadDashboard } from "./support/loadDashboard.js";

const load = () => loadDashboard().window;
const COLS = ["dataset", "id_1", "id_2"];

describe("comparing failing-row samples between two runs", () => {
  it("matches several-column samples by value, not by reference", () => {
    const got = load().compareSampleKeys(
      { failing_sample_keys: [["CP", "C-1", null], ["ED", "P-2", null]], failing_sample_key_columns: COLS },
      { failing_sample_keys: [["CP", "C-1", null], ["CP", "C-3", null]], failing_sample_key_columns: COLS });
    expect(got.comparable).toBe(true);
    expect(got.stillFailing).toEqual([["CP", "C-1", null]]);
    expect(got.newSinceCompare).toEqual([["ED", "P-2", null]]);
    expect(got.noLongerSampled).toEqual([["CP", "C-3", null]]);
  });

  it("tells a null part from an empty string", () => {
    const got = load().compareSampleKeys(
      { failing_sample_keys: [["CP", null]], failing_sample_key_columns: ["dataset", "id_1"] },
      { failing_sample_keys: [["CP", ""]], failing_sample_key_columns: ["dataset", "id_1"] });
    expect(got.stillFailing).toEqual([]);
  });

  it("compares one-column samples exactly as before", () => {
    const got = load().compareSampleKeys(
      { failing_sample_keys: ["K-1", "K-2"] }, { failing_sample_keys: ["K-2", "K-3"] });
    expect(got.comparable).toBe(true);
    expect(got.stillFailing).toEqual(["K-2"]);
    expect(got.newSinceCompare).toEqual(["K-1"]);
    expect(got.noLongerSampled).toEqual(["K-3"]);
  });

  it("refuses to compare runs that named their rows by different columns", () => {
    const w = load();
    const got = w.compareSampleKeys(
      { failing_sample_keys: [["CP", "C-1", null]], failing_sample_key_columns: COLS },
      { failing_sample_keys: ["k"] });
    expect(got.comparable).toBe(false);
    expect(w.eval("SAMPLE_KEYS_INCOMPARABLE")).toBe(
      "These examples cannot be compared: the compared run named its rows by different columns.");
  });
});

describe("a failing-row sample pill", () => {
  it("escapes a one-column key", () => {
    const html = load().samplePill("<img src=x onerror=alert(1)>", "transparent");
    expect(html).not.toContain("<img");
    expect(html).toContain("&lt;img");
  });

  it("escapes every part of a several-column key", () => {
    const html = load().samplePill(["<b>CP</b>", "C&1", null], "transparent");
    expect(html).not.toContain("<b>");
    expect(html).toContain("&lt;b&gt;CP&lt;/b&gt;");
    expect(html).toContain("C&amp;1");
  });

  it("never prints a null key as the text null", () => {
    const w = load();
    expect(w.samplePill(null, "transparent")).not.toContain("null");
    expect(w.samplePill(["CP", null], "transparent")).not.toContain("null");
  });

  // A null PART followed by a present one reads '—' since REQ-DASH-299
  // decision 36 was changed by Keith 2026-11-02 (morning report B11).
  it("shows a null key as (no value), and a null middle part as '—'", () => {
    const w = load();
    expect(w.samplePill(null, "transparent")).toContain(">(no value)</span>");
    expect(w.samplePill(["CP", null, "x"], "transparent")).toContain("CP / — / x");
  });
});
