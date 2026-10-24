// REQ-DASH-127 - every supply's outcome in its supply history, superseded
// among the others and distinct from rejected - and REQ-DASH-126 - a
// promoted supply turned red is labelled RED PROMOTED, on the dates it was.
import { describe, it, expect } from "vitest";
import { loadDashboard } from "./support/loadDashboard.js";

const RUNS = [{run_id: "r1", run_date: "2026-01-10"}, {run_id: "r2", run_date: "2026-02-10"}];

function withRaw(raw){
  const w = loadDashboard().window;
  w.rawRealDatasetById = () => raw;
  return w;
}

describe("a supply's outcome", () => {
  const raw = {id: "cp-carers", runs: RUNS, runStates: {
    r1: [{at: "2026-01-20T01:00:00+00:00", state: "promoted", action: "promote", by: "rule"},
         {at: "2026-02-12T01:00:00+00:00", state: "withdrawn", action: "supersede", by: "rule",
          supersededBy: "cp-carers@2", supersededByRun: "r2", setting: "green"}],
    r2: [{at: "2026-02-12T01:00:00+00:00", state: "promoted", action: "promote", by: "rule"}]}};

  it("is waiting before any decision, then each decision's outcome", () => {
    const w = withRaw(raw);
    expect(w.runOutcomeInPlaceOn("cp-carers", "r1", "2026-01-15").kind).toBe("waiting");
    expect(w.runOutcomeInPlaceOn("cp-carers", "r1", "2026-01-25").kind).toBe("promoted");
    expect(w.runOutcomeInPlaceOn("cp-carers", "r1", "2026-02-20").kind).toBe("superseded");
  });

  it("names the superseding supply, the rule and the setting, quietly", () => {
    const w = withRaw(raw);
    w.CURRENT_IN_PLACE_ON = "2026-02-20";
    const html = w.outcomeCell("cp-carers", "r1", {r2: RUNS[1]});
    expect(html).toContain('data-outcome="superseded"');
    expect(html).toContain("by the rule");
    expect(html).toContain("replacement setting 'green'");
    expect(html).not.toContain("pill");
  });

  it("names the superseding supply by its receipt instant, not its day (#123 A3)", () => {
    const w = withRaw(raw);
    w.CURRENT_IN_PLACE_ON = "2026-02-20";
    const newer = {...RUNS[1], arrivedAt: "2026-02-10T03:15:00+00:00"};
    const html = w.outcomeCell("cp-carers", "r1", {r2: newer});
    expect(html).toContain(w.fmtInstant(newer.arrivedAt));
  });

  it("is rejected, not superseded, for a reject", () => {
    const w = withRaw({id: "x", runs: RUNS, runStates: {
      r1: [{at: "2026-01-20T01:00:00+00:00", state: "withdrawn", action: "reject", by: "person"}]}});
    expect(w.runOutcomeInPlaceOn("x", "r1", "2026-02-01").kind).toBe("rejected");
  });
});

describe("red promoted", () => {
  const raw = {id: "cp-carers", runs: RUNS,
    runStates: {r1: [{at: "2026-01-20T01:00:00+00:00", state: "promoted", action: "promote"}]},
    promotedHealth: {r1: {promotedOn: "green", promotedAt: "2026-01-20T01:00:00+00:00",
      timeline: [{at: "2026-01-10T01:00:00+00:00", status: "green", cause: "the arrival of Carers"},
                 {at: "2026-03-01T01:00:00+00:00", status: "red",
                  cause: "the promote of Client Register"}]}}};

  it("is labelled from the date it turned, naming the cause and what it went in as", () => {
    const w = withRaw(raw);
    const html = w.redPromotedBadge("cp-carers", "r1", "2026-03-05");
    expect(html).toContain("data-red-promoted");
    expect(html).toContain("Went in green");
    expect(html).toContain("the promote of Client Register");
  });

  it("is a short red pill with its sentence beneath, not a sentence in a pill (#121 D1/D2)", () => {
    const w = withRaw(raw);
    const root = w.document.createElement("div");
    root.innerHTML = w.redPromotedBadge("cp-carers", "r1", "2026-03-05");
    const pill = root.querySelector(".pill.red");
    expect(pill && pill.textContent.trim()).toBe("Red promoted");
    const why = root.querySelector("[data-red-promoted-why]");
    expect(why.textContent).toContain("the promote of Client Register");
    expect(root.innerHTML).not.toContain("var(--red)");
  });

  it("is counted as a kind on the agency card (#123 A1)", () => {
    const w = withRaw(raw);
    w.eval("CURRENT_IN_PLACE_ON = '2026-03-05'");
    const ag = {id: "dcp", collections: [{id: "c", datasets: [
      {id: "cp-carers", name: "Carers", verdictOf: {inPlaceRunId: "r1"}},
      {id: "cp-clients", name: "Clients", verdictOf: {inPlaceRunId: null}}]}]};
    const html = w.redPromotedMarker(ag);
    expect(html).toContain("1 red promoted");
    expect(html).toContain("Carers");
    expect(w.redPromotedMarker({id: "x", collections: []})).toBe("");
  });

  it("before it turned, shows a note rather than red", () => {
    const w = withRaw(raw);
    const html = w.redPromotedBadge("cp-carers", "r1", "2026-02-01");
    expect(html).not.toContain("data-red-promoted");
    expect(html).toContain("data-turns-red-later");
  });

  it("nothing beside a promoted supply that is not red", () => {
    const w = withRaw({...raw, promotedHealth: {r1: {promotedOn: "green",
      promotedAt: "2026-01-20T01:00:00+00:00", timeline: [
        {at: "2026-01-10T01:00:00+00:00", status: "green", cause: "x"}]}}});
    expect(w.redPromotedBadge("cp-carers", "r1", "2026-03-05")).toBe("");
  });

  it("nothing for a supply that is not promoted on the date", () => {
    const w = withRaw(raw);
    expect(w.redPromotedBadge("cp-carers", "r1", "2026-01-15")).toBe("");
  });
});

// post-build-review #116 D3: a supply promoted while already red got no
// label, because every point before the promotion was skipped.
describe("a supply promoted while red", () => {
  it("is red promoted from the start", () => {
    const w = withRaw({id: "x", runs: RUNS,
      runStates: {r1: [{at: "2026-01-20T01:00:00+00:00", state: "promoted", action: "promote"}]},
      promotedHealth: {r1: {promotedOn: "red", promotedAt: "2026-01-20T01:00:00+00:00",
        timeline: [{at: "2026-01-10T01:00:00+00:00", status: "red", cause: "the arrival of X"}]}}});
    const html = w.redPromotedBadge("x", "r1", "2026-02-01");
    expect(html).toContain("data-red-promoted");
    // Keith, 2026-10-24 (post-build-review #266 Q6 = A): already red before
    // its promotion reads "Went in red", naming when and after what.
    expect(html).toContain(`Went in red. Red since the arrival of X, ${w.fmtInstant("2026-01-10T01:00:00+00:00")}; promoted ${w.fmtInstant("2026-01-20T01:00:00+00:00")}.`);
  });
});

// post-build-review #266, Keith Q6 = A: Child Protection's Notifications,
// received 11 Feb 2014 and promoted 16 Feb on the gate's reading (its two
// Evidently checks red only for want of a reference, which by REQ-QAC-108
// criteria 9 and 15 neither pass nor block), read "Went in green, turned red
// 11 February after the arrival of Notifications" - a date before it went in.
describe("a supply already red before its promotion", () => {
  const raw = {id: "cp-notifications", runs: [{run_id: "n", run_date: "2014-02-11"}],
    runStates: {n: [{at: "2014-02-16T04:52:10+00:00", state: "promoted", action: "promote"}]},
    promotedHealth: {n: {promotedOn: "green", promotedAt: "2014-02-16T04:52:10+00:00",
      timeline: [{at: "2014-02-11T01:00:00.000002+00:00", status: "green", cause: "the arrival of Case Workers"},
                 {at: "2014-02-11T01:00:00.000003+00:00", status: "red", cause: "the arrival of Notifications"}]}}};

  it("went in red, red since its own arrival, then promoted", () => {
    const w = withRaw(raw);
    const root = w.document.createElement("div");
    root.innerHTML = w.redPromotedBadge("cp-notifications", "n", "2014-02-20");
    const why = root.querySelector("[data-red-promoted-why]").textContent;
    expect(why).toBe(`Went in red. Red since the arrival of Notifications, ${w.fmtInstant("2014-02-11T01:00:00.000003+00:00")}; promoted ${w.fmtInstant("2014-02-16T04:52:10+00:00")}.`);
    expect(why).not.toContain("turned red");
  });

  it("a red that came after the promotion still went in green and turned", () => {
    const w = withRaw({...raw, promotedHealth: {n: {...raw.promotedHealth.n, timeline: [
      {at: "2014-02-11T01:00:00.000003+00:00", status: "green", cause: "the arrival of Notifications"},
      {at: "2014-02-25T01:00:00+00:00", status: "red", cause: "the promote of Case Workers"}]}}});
    const root = w.document.createElement("div");
    root.innerHTML = w.redPromotedBadge("cp-notifications", "n", "2014-03-01");
    const why = root.querySelector("[data-red-promoted-why]").textContent;
    expect(why).toBe(`Went in green, turned red ${w.fmtInstant("2014-02-25T01:00:00+00:00")} after the promote of Case Workers.`);
  });
});

describe("the verdict line", () => {
  // #123 A5: "the results below" over tiles that all read No data. #110 H3
  // suppressed it for a blocked page; a stale date on show blanks them too.
  const ds = {id: "x", verdictOf: {state: "awaiting"}, lastArrival: {arrivedAt: "2026-09-01T01:00:00+00:00"}};

  it("speaks where there are results below", () => {
    expect(loadDashboard().window.verdictLine(ds)).toContain("data-verdict-of");
  });

  it("is absent where the date on show blanks every result", () => {
    expect(loadDashboard().window.verdictLine({...ds, noDataInPlaceOn: true})).toBe("");
  });
});

// REQ-DASH-126 criterion 3 / post-build-review #116 D2 (Keith, 2026-10-06):
// a PROMOTED supply's pill in its history is its newest result on the date
// on show, so the pill and the red-promoted label can never disagree; the
// verdict it arrived with stays beside it when they differ.
describe("a promoted supply's pill", () => {
  const raw = {id: "cp-carers", runs: RUNS,
    runStates: {r1: [{at: "2026-01-20T01:00:00+00:00", state: "promoted", action: "promote"}]},
    promotedHealth: {r1: {promotedOn: "green", promotedAt: "2026-01-20T01:00:00+00:00",
      timeline: [{at: "2026-01-10T01:00:00+00:00", status: "green", cause: "the arrival of Carers"},
                 {at: "2026-03-01T01:00:00+00:00", status: "red",
                  cause: "the promote of Client Register"}]}}};
  const pillOf = (w, html) => {
    const root = w.document.createElement("div");
    root.innerHTML = html;
    return {pill: root.querySelector(".pill").className, arrived: root.querySelector("[data-arrived-as]")};
  };

  it("reads red once its newest result is red, saying what it arrived as", () => {
    const w = withRaw(raw);
    const got = pillOf(w, w.supplyRowStatus("cp-carers", {run_id: "r1", status: "green"}, "2026-03-05"));
    expect(got.pill).toContain("red");
    expect(got.arrived.textContent).toBe("Arrived Green");
  });

  it("reads as it arrived before anything changed it", () => {
    const w = withRaw(raw);
    const got = pillOf(w, w.supplyRowStatus("cp-carers", {run_id: "r1", status: "green"}, "2026-02-01"));
    expect(got.pill).toContain("green");
    expect(got.arrived).toBeNull();
  });

  it("reads green when a supply that arrived red has since gone green", () => {
    const w = withRaw({...raw, promotedHealth: {r1: {promotedOn: "red",
      promotedAt: "2026-01-20T01:00:00+00:00", timeline: [
        {at: "2026-01-10T01:00:00+00:00", status: "red", cause: "x"},
        {at: "2026-02-15T01:00:00+00:00", status: "green", cause: "y"}]}}});
    const got = pillOf(w, w.supplyRowStatus("cp-carers", {run_id: "r1", status: "red"}, "2026-03-05"));
    expect(got.pill).toContain("green");
    expect(got.arrived.textContent).toBe("Arrived Red");
  });

  it("never reads greener than the page at the arrival itself (post-build-review #132 A1)", () => {
    // The arrival's own reading came from the gate, which reads a gap red as
    // its measurement - so it said green where the page says red.
    const w = withRaw({...raw, promotedHealth: {r1: {promotedOn: "green",
      promotedAt: "2026-01-20T01:00:00+00:00", timeline: [
        {at: "2026-01-10T01:00:00+00:00", status: "green", cause: "the arrival of Carers"}]}}});
    const got = pillOf(w, w.supplyRowStatus("cp-carers", {run_id: "r1", status: "red"}, "2026-03-05"));
    expect(got.pill).toContain("red");
    expect(got.arrived).toBeNull();
  });

  it("names what changed it (Keith, 2026-10-07)", () => {
    const w = withRaw(raw);
    const html = w.supplyRowStatus("cp-carers", {run_id: "r1", status: "green"}, "2026-03-05");
    expect(html).toContain("the promote of Client Register");
  });

  it("a supply not promoted on the date keeps its own verdict", () => {
    const w = withRaw(raw);
    const got = pillOf(w, w.supplyRowStatus("cp-carers", {run_id: "r1", status: "amber"}, "2026-01-15"));
    expect(got.pill).toContain("amber");
    expect(got.arrived).toBeNull();
  });
});
