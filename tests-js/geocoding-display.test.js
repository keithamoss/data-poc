// REQ-DASH-299: a check's examples are headed by what it measures, a
// set-member check's sample reads as a record and a year, and a several-column
// key drops its trailing empty parts. These are the branches criterion 16
// proves here because no generated page reaches them (and the template's own
// functions, which the built page calls, for the ones it does).
import { afterEach, describe, expect, it } from "vitest";
import { loadDashboard } from "./support/loadDashboard.js";

let dashboard;
afterEach(() => { dashboard?.close(); dashboard = undefined; });
const load = () => { dashboard = loadDashboard(); return dashboard.window; };
const text = (w, html) => { const d = w.document.createElement("div"); d.innerHTML = html; return d.textContent.replace(/\s+/g, " ").trim(); };

const GEO = "data-asset-1.department-of-health.linkage-products.geo-cp-clients.census_year";
const yearCheck = (kind, measures) => ({ check_id: `${GEO}.${kind}_dbt`, tool_ref: `dbt:${kind}`, measures });
const COLS = ["id_1", "census_year"];

describe("a check's examples are headed by what it measures (criteria 3 and 4)", () => {
  it("names the phrase, key only, with today's count suffix", () => {
    const w = load();
    const html = w.sampleBlockHtml({ tool_ref: "dbt:unique", measures: "Duplicate values" },
      { failing_sample_keys: ["K-1", "K-2"], row_count_invalid: 9 }, null);
    expect(text(w, html)).toContain("Examples: Duplicate values (key only) — 2 of 9");
    const d = w.document.createElement("div"); d.innerHTML = html;
    expect(d.querySelector(".sample-heading").textContent).not.toMatch(/failing rows|primary key/i);
  });

  it("labels its counts with the phrase, and the compare block as examples", () => {
    const w = load();
    const ck = { measures: "Missing census years" };
    expect(w.flaggedLabel(ck, "this run")).toBe("Missing census years, this run");
    expect(w.flaggedLabel(ck, "compared run")).toBe("Missing census years, compared run");
    expect(w.eval("SAMPLE_COMPARE_HEADING")).toBe("Examples vs. the compared run");
  });

  it("with no phrase, is neutral: 'Examples (key only)' and 'Flagged, this run'", () => {
    const w = load();
    const ck = { tool_ref: "soda:brand_new", measures: null };
    expect(w.sampleHeading(ck)).toBe("Examples (key only)");
    expect(w.flaggedLabel(ck, "this run")).toBe("Flagged, this run");
    expect(w.flaggedLabel(ck, "compared run")).toBe("Flagged, compared run");
    expect(text(w, w.sampleBlockHtml(ck, { failing_sample_keys: ["a"], row_count_invalid: 1 }, null)))
      .toContain("Examples (key only)");
  });

  it("escapes the phrase", () => {
    const w = load();
    expect(w.sampleHeading({ measures: "<b>x</b>" })).not.toContain("<b>");
  });
});

describe("a result with no examples (criterion 5)", () => {
  it("says none were recorded where it records violations", () => {
    const w = load();
    const html = w.sampleBlockHtml({ measures: "Duplicate values" },
      { failing_sample_keys: [], row_count_invalid: 4 }, null);
    expect(text(w, html)).toBe("No examples were recorded for this result.");
    expect(html).not.toContain("plans/qa-pipeline.md");
  });

  it("shows neither heading nor sentence for a percentage-only result", () => {
    const w = load();
    expect(w.sampleBlockHtml({ measures: "Rows not geocoded" },
      { failing_sample_keys: [], row_count_invalid: null, value: 3.2 }, null)).toBe("");
  });
});

describe("a set-member check's sample (criteria 6 and 7)", () => {
  const withSource = (w, linked) => {
    w.rawRealDatasetById = (id) => (id === "geo-cp-clients" ? { id, linkedSource: linked } : null);
    return w;
  };

  it("reads a missing year as a constructed line, never a row", () => {
    const w = withSource(load(), { datasetId: "cp-clients", relation: "Geocodes" });
    const point = { failing_sample_keys: [["4821", "2021"]], failing_sample_key_columns: COLS, row_count_invalid: 1 };
    const html = w.sampleBlockHtml(yearCheck("missing_set_members", "Missing census years"), point, "geo-cp-clients");
    expect(text(w, html)).toContain("Examples: Missing census years (key only)");
    expect(text(w, html)).toContain("source record 4821 · 2021: no row");
  });

  it("words a duplicate and an unexpected year from the kind alone, with no row count", () => {
    const w = withSource(load(), { datasetId: "cp-clients" });
    const point = { failing_sample_keys: [["4821", "2026"]], failing_sample_key_columns: COLS, row_count_invalid: 1 };
    expect(w.setMemberSampleLine(yearCheck("duplicated_set_members"), point, ["4821", "2016"], "geo-cp-clients"))
      .toBe("source record 4821 · 2016: more than one row");
    const unexpected = w.setMemberSampleLine(yearCheck("unexpected_set_members"), point, ["4821", "2026"], "geo-cp-clients");
    expect(unexpected).toBe("source record 4821 · 2026: not expected for this period");
    expect(unexpected).not.toMatch(/in force|\d+ rows?/);
  });

  it("says 'record' where the dataset is not a single code-less linked one", () => {
    const w = withSource(load(), null);
    expect(w.setMemberSampleLine(yearCheck("missing_set_members"),
      { failing_sample_key_columns: COLS }, ["7", "2011"], "geo-cp-clients")).toBe("record 7 · 2011: no row");
  });

  it("drops a trailing empty identifier part, never ending in '/ —'", () => {
    const w = withSource(load(), { datasetId: "cp-clients" });
    const line = w.setMemberSampleLine(yearCheck("missing_set_members"),
      { failing_sample_key_columns: ["id_1", "id_2", "census_year"] }, ["4821", null, "2016"], "geo-cp-clients");
    expect(line).toBe("source record 4821 · 2016: no row");
  });

  it("escapes every part", () => {
    const w = withSource(load(), null);
    const line = w.setMemberSampleLine(yearCheck("missing_set_members"),
      { failing_sample_key_columns: COLS }, ["<i>x</i>", "<b>"], "geo-cp-clients");
    expect(line).not.toMatch(/<i>|<b>/);
  });

  it("leaves any other check's sample as its pill", () => {
    const w = load();
    expect(w.setMemberSampleLine({ check_id: "a.b.c.d.id_1.unique_dbt", tool_ref: "dbt:unique" },
      { failing_sample_key_columns: COLS }, ["1", "2"], null)).toBe(null);
  });
});

describe("a several-column key on the page (criterion 8)", () => {
  it("drops the trailing empty part and shows a middle one as '—'", () => {
    const w = load();
    expect(text(w, w.samplePill(["CP", "C-1", null], "transparent"))).toBe("CP / C-1");
    expect(text(w, w.samplePill(["CP", "", "x"], "transparent"))).toBe("CP / — / x");
    expect(text(w, w.samplePill(["CP", "C-1", ""], "transparent"))).toBe("CP / C-1");
  });

  it("keeps a null middle part as '(no value)', as REQ-PIPE-341 built it", () => {
    const w = load();
    expect(text(w, w.samplePill(["CP", null, "x"], "transparent"))).toBe("CP / (no value) / x");
  });

  it("compares across a change of recorded key columns by saying it cannot", () => {
    const w = load();
    expect(w.compareSampleKeys({ failing_sample_keys: [["1", "2011"]], failing_sample_key_columns: COLS },
      { failing_sample_keys: [["1", "", "2011"]], failing_sample_key_columns: ["id_1", "id_2", "census_year"] })
      .comparable).toBe(false);
  });
});
