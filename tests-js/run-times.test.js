// Run times, tries, and a supply that could not be checked, on the page
// (REQ-DASH-413 criterion 11, REQ-DASH-414 criterion 8, REQ-DASH-415
// criterion 10) - each through the template's own functions, handed the
// shape the build emits (pipeline/build_dashboard_data's runTimes and
// outstanding.py's could-not-check blocker).
import { afterEach, describe, expect, it } from "vitest";
import { loadDashboard } from "./support/loadDashboard.js";

let dashboard;
afterEach(() => { dashboard?.close(); dashboard = undefined; });
const load = () => { dashboard = loadDashboard(); return dashboard.window; };

const DS = "cp-clients";
const at = d => `2026-03-${String(d).padStart(2, "0")}T02:00:00+00:00`;
function run(n, ms, extra = {}){
  return {run_id: `r${n}`, rank: n, scope: "arrival", cause: `arrival:r${n}`,
          supply_id: `${DS}@k${n}`, run_time_ms: ms, ended_at: at(n), not_checked: false,
          attempts: null, slow: null, too_few: false, ...extra};
}
const tries = (...list) => ({count: list.length, left_out: 0, tries: list.map((t, i)=> ({
  number: i + 1, began_at: at(t.began || 1), ended_at: t.ended === null ? null : at(t.ended || 2),
  outcome: t.outcome, run_time_ms: t.ms === undefined ? 2_700_000 : t.ms, tool: t.tool || null,
  error_type: t.type || null}))});

describe("the run-time trend (413)", () => {
  it("orders its points by rank alone, whatever their dates", () => {
    const w = load();
    const runs = [run(2, 1000, {ended_at: at(1)}), run(1, 2000, {ended_at: at(9)}), run(3, 3000)];
    const series = w.runTimeSeries(DS, null, runs);
    expect(series.map(p=> p.run.run_id)).toEqual(["r1", "r2", "r3"]);
  });

  it("draws a failed try as a hollow marker labelled in words, not on the line", () => {
    const w = load();
    const retried = run(2, 192_000, {attempts: tries(
      {outcome: "TIMED-OUT", ms: 2_700_000}, {outcome: "COMPLETED", ms: 192_000})});
    const html = w.runTimeTrend(DS, null, [run(1, 100_000), retried]);
    expect(html).toContain("data-failed-try");
    expect(html).toContain("timed out after 45m");
    expect((html.match(/data-run-point=/g) || []).length).toBe(2);
  });

  it("rings a slow run and labels it in words, never in a status colour", () => {
    const w = load();
    const html = w.runTimeTrend(DS, null, [run(1, 1000), run(2, 1000), run(3, 1000),
      run(4, 9000, {slow: true, median_ms: 1000, judged_against: 3})]);
    expect(html).toContain("data-slow-ring");
    expect(html).toContain(">slow</text>");
    expect(html).not.toMatch(/var\(--(bad|warn|good)\)/);
  });

  it("lists every run newest first in its table, with the slow and too-few words", () => {
    const w = load();
    const html = w.runTimeTrend(DS, null, [run(1, 1000, {too_few: true}), run(2, 1000, {too_few: true}),
      run(3, 1000, {too_few: true}), run(4, 9000, {slow: true, median_ms: 1000, judged_against: 3})]);
    const table = html.slice(html.indexOf("data-run-time-table"));
    expect(table.indexOf('data-run="r4"')).toBeLessThan(table.indexOf('data-run="r1"'));
    expect(table).toContain("Slow - median 1s over 3 runs");
    expect(table).toContain("too few earlier runs to judge");
  });

  it("says too little history in one sentence, under two runs with a run time", () => {
    const w = load();
    const html = w.runTimeTrend(DS, null, [run(1, 1000), run(2, null)]);
    expect(html).toContain("data-run-time-too-little");
    expect(html).not.toContain("<svg");
  });

  it("is drawn as at the date on show: nothing that had not ended by then", () => {
    const w = load();
    const runs = [run(1, 1000), run(2, 2000), run(20, 3000)];
    const on = "2026-03-05";
    expect(w.runTimeSeries(DS, on, runs).map(p=> p.run.run_id)).toEqual(["r1", "r2"]);
  });

  it("labels its axis in whole durations, never 'under 1s' (post-build-review #493 M5)", () => {
    const w = load();
    const html = w.runTimeTrend(DS, null, [run(1, 700), run(2, 1_200)]);
    const ticks = [...html.matchAll(/font-family="IBM Plex Mono, monospace">([^<]*)</g)].map(m=> m[1]);
    expect(ticks).toEqual(["0s", "1s", "2s"]);
  });

  it("scales to the runs that finished, marking a longer failed try off the scale (#493 H2)", () => {
    // Keith, 2026-11-21: one 45-minute try had flattened every 2-4s run onto zero.
    const w = load();
    const retried = run(3, 3_000, {attempts: tries(
      {outcome: "TIMED-OUT", ms: 2_700_000}, {outcome: "COMPLETED", ms: 3_000})});
    const html = w.runTimeTrend(DS, null, [run(1, 2_000), run(2, 4_000), retried]);
    const ticks = [...html.matchAll(/font-family="IBM Plex Mono, monospace">([^<]*)</g)].map(m=> m[1]);
    expect(ticks).toEqual(["0s", "2s", "4s"]);
    expect(html).toContain("data-off-scale");
    expect(html).toContain("timed out after 45m - off the scale");
    expect(html).toContain("above the top are tries longer than the scale");
  });

  it("says whether its table is open, for a screen reader (#493 nit)", () => {
    const w = load();
    const html = w.runTimeTrend(DS, null, [run(1, 1000), run(2, 2000)]);
    expect(html).toMatch(/data-toggle-unit-table="[^"]+" aria-expanded="false" aria-controls="[^"]+-table"/);
    const host = w.document.createElement("div");
    host.innerHTML = html;
    w.document.body.appendChild(host);
    const btn = host.querySelector("[data-toggle-unit-table]");
    btn.click();
    expect(btn.getAttribute("aria-expanded")).toBe("true");
    btn.click();
    expect(btn.getAttribute("aria-expanded")).toBe("false");
  });

  it("is nowhere for a dataset with no runTimes - never made up", () => {
    const w = load();
    expect(w.runTimeTrend(DS, null, [])).toBe("");
  });
});

describe("a supply whose dataset checks never ran (post-build-review #493 H3)", () => {
  // Keith, 2026-11-21: one that could not be loaded and a contested pair's
  // file waiting for a choice alike say 'Not checked' and stay off the trend.
  const blockers = {blockers: [
    {kind: "refused", datasetId: DS, supply: `${DS}@k2`},
    {kind: "contested", datasetId: DS, supply: `${DS}@k3`}]};
  const runs = () => [run(1, 2_000), run(2, 74), run(3, 52), run(4, 2_500)];

  it("is left off the run-time trend", () => {
    const w = load();
    expect(w.runTimeSeries(DS, null, runs(), blockers).map(p=> p.run.run_id)).toEqual(["r1", "r4"]);
  });

  it("says Not checked, and why, in its Status cell rather than a run time", () => {
    const w = load();
    const refused = w.runTimeNotes(DS, {run_id: "r2"}, null, runs(), blockers);
    expect(refused).toContain("Not checked - its file could not be loaded");
    expect(refused).not.toContain("Checked in");
    const contested = w.runTimeNotes(DS, {run_id: "r3"}, null, runs(), blockers);
    expect(contested).toContain("Not checked - two files arrived for it and one had to be chosen");
    expect(w.runTimeNotes(DS, {run_id: "r1"}, null, runs(), blockers)).toContain("Checked in 2s");
  });
});

describe("a row's own run time (413 criterion 2)", () => {
  it("sits in the Status cell as 'Checked in 3m 12s', ' · slow' in bold where slow", () => {
    const w = load();
    const said = w.runTimeNotes(DS, {run_id: "r1"}, null, [run(1, 192_000)]);
    expect(said).toContain("Checked in 3m 12s");
    const slow = w.runTimeNotes(DS, {run_id: "r1"}, null, [run(1, 7_500_000, {slow: true})]);
    expect(slow).toContain("Checked in 2h 05m · <b data-slow");
  });

  it("puts a re-check's run time in its re-check words", () => {
    const w = load();
    const runs = [run(1, 192_000), run(2, 7_500_000, {scope: "full", supply_id: `${DS}@k1`})];
    expect(w.runTimeNotes(DS, {run_id: "r1"}, null, runs)).toContain("re-checked");
    expect(w.runTimeNotes(DS, {run_id: "r1"}, null, runs)).toContain("in 2h 05m");
  });

  it("keeps the arrival's own time in the Status cell when the row carries a re-check's run", () => {
    // post-build-review #493 H1: a correction leaves the row keyed on the run
    // in place, the full re-check `<run>__r1`, and its 8s read as the 793ms
    // arrival's own 'Checked in'.
    const w = load();
    const runs = [run(1, 793, {run_id: "a", supply_id: `${DS}@k`}),
                  run(9, 8_372, {run_id: "a__r1", scope: "full", supply_id: `${DS}@k`})];
    const said = w.runTimeNotes(DS, {run_id: "a__r1"}, null, runs);
    expect(said).toMatch(/data-run-time [^>]*>Checked in under 1s</);
    expect(said).toMatch(/data-recheck-run-time[^>]*>· re-checked [^<]* in 8s</);
  });

  it("says nothing where a run has no run time", () => {
    const w = load();
    expect(w.runTimeNotes(DS, {run_id: "r1"}, null, [run(1, null)])).toBe("");
  });
});

describe("a run that needed another try (414)", () => {
  const second = (first) => run(1, 192_000, {attempts: tries(first, {outcome: "COMPLETED", ms: 192_000, began: 3, ended: 4})});

  it.each([
    [{outcome: "TIMED-OUT", ms: 2_700_000}, "the first timed out after 45m"],
    [{outcome: "CRASHED", ms: 64_000}, "the first crashed after 1m 04s"],
    [{outcome: "TOOL-ERROR", ms: 64_000, tool: "dbt-core"}, "the first failed in dbt-core after 1m 04s"],
    [{outcome: "INTERRUPTED", ms: 130_000}, "the first was stopped after 2m 10s"],
    [{outcome: "INTERRUPTED", ms: null, ended: null}, "the first did not finish"],
  ])("says how the earlier try ended: %j", (first, words) => {
    const w = load();
    const html = w.triesNote(second(first), null);
    expect(html).toContain(`Checked on the second try - ${words}`);
    expect(html).not.toContain("attempt");
    expect(html).toContain("<details");
    expect(html).not.toContain("<details open");
  });

  it("lists the first, the newest five and 'and <n> more', naming mothman supply failures", () => {
    const w = load();
    const a = tries(...Array.from({length: 6}, ()=> ({outcome: "CRASHED", ms: 1000})),
                    {outcome: "COMPLETED", ms: 1000});
    a.count = 9; a.left_out = 3;
    a.tries = a.tries.map((t, i)=> ({...t, number: [1, 5, 6, 7, 8, 9, 9][i]})).slice(0, 6);
    a.tries[5] = {...a.tries[5], outcome: "COMPLETED"};
    const html = w.triesNote(run(1, 1000, {attempts: a}), null);
    expect(html).toContain("Checked on the ninth try");
    expect(html).toContain("and 3 more");
    expect(html).toContain("mothman supply failures");
    expect((html.match(/<li value="/g) || []).length).toBe(6);
    // EACH LINE KEEPS ITS OWN TRY'S NUMBER where some are left out (#493 M6).
    expect([...html.matchAll(/<li value="(\d+)"/g)].map(m=> m[1])).toEqual(["1", "5", "6", "7", "8", "9"]);
  });

  it("names every failed try before the success, oldest first (#493 M6, wording approved by Keith)", () => {
    const w = load();
    const three = run(1, 3_000, {attempts: tries({outcome: "TIMED-OUT", ms: 2_700_000},
      {outcome: "CRASHED", ms: 3_000}, {outcome: "COMPLETED", ms: 3_000})});
    expect(w.triesNote(three, null)).toContain(
      "Checked on the third try - the first timed out after 45m, the second crashed after 3s");
    const five = run(1, 3_000, {attempts: tries({outcome: "CRASHED", ms: 3_000},
      {outcome: "TIMED-OUT", ms: 2_700_000}, {outcome: "CRASHED", ms: 2_000},
      {outcome: "CRASHED", ms: 1_000}, {outcome: "COMPLETED", ms: 3_000})});
    expect(w.triesNote(five, null)).toContain(
      "Checked on the fifth try - 4 tries before it failed, the longest timed out after 45m");
  });

  it("gives each line its number once and its date once where it began and ended that day (#493 M6)", () => {
    const w = load();
    const line = w.tryLine({number: 1, began_at: "2026-03-01T01:09:00+00:00",
      ended_at: "2026-03-01T01:54:00+00:00", outcome: "TIMED-OUT", run_time_ms: 2_700_000});
    expect(line).not.toMatch(/^Try /);
    const days = line.match(/\d{1,2} [A-Z][a-z]+ \d{4}/g) || [];
    expect(days.length).toBe(1);
    expect(line).toMatch(/ended \d{1,2}:\d{2}[ap]m - timed out after 45m/);
  });

  it("judges each try as at the date on show: begun and not ended reads not finished", () => {
    const w = load();
    const list = w.triesAsAt(tries({outcome: "CRASHED", began: 2, ended: 6}), "2026-03-04");
    expect(list[0].unfinished).toBe(true);
    expect(w.tryLine(list[0])).toContain("not finished");
    expect(w.tryLine(list[0])).not.toContain("crashed");
    expect(w.triesAsAt(tries({outcome: "CRASHED", began: 9, ended: 10}), "2026-03-04")).toEqual([]);
  });

  // ITS STATUS IS THE COMPLETED TRY'S: held at the build, where the verdicts
  // are made (tests/test_attempts_in_the_build.py::TestAFailedTryNeverRaisesAStatus,
  // post-build-review #408) - the page reads no try when judging a status.
  it("is not shown for a run with one try that completed", () => {
    const w = load();
    expect(w.triesNote(run(1, 1000, {attempts: null}), null)).toBe("");
  });

  it("uses the shared duration format", () => {
    const w = load();
    const html = w.triesNote(second({outcome: "TIMED-OUT", ms: 59_600}), null);
    expect(html).toContain(`after ${w.fmtElapsed(59.6)}`);
    expect(w.fmtElapsed(59.6)).toBe("1m 00s");
  });
});

describe("a supply that could not be checked (415)", () => {
  const B = {kind: "could-not-check", datasetId: DS, supply: `${DS}@k9`,
             openedAt: "2026-03-10T02:00:00+00:00", resolvedAt: null, reason: "x",
             files: [], loadFailures: [],
             tries: {runId: "r9", outcome: "TOOL-ERROR", tool: "dbt-core", errorType: "ValueError",
                     beganAt: "2026-03-10T03:00:00+00:00", endedAt: "2026-03-12T03:00:00+00:00",
                     failed: 3}};
  const SOURCE = {items: [], blockers: [B]};

  it("reads 'Could not be checked' everywhere it is labelled, never 'Not checked'", () => {
    const w = load();
    expect(w.blockerLabel(B)).toBe("Could not be checked");
    expect(w.outstandingKindLabel("could-not-check")).toBe("Could not be checked");
    expect(w.blockerReasonText(B)).toContain("our check of it did not finish");
    expect(w.blockerReasonText(B)).not.toContain("Not checked");
  });

  it("says each ending, the tool, how many tries, and the next step", () => {
    const w = load();
    const said = w.couldNotCheckWords(B, "2026-03-20");
    expect(said).toContain("its newest try failed in dbt-core at");
    expect(said).toContain("could not be checked on 3 tries");
    expect(said).toContain("Nothing is yet known about this supply's data");
    expect(said).toContain("The next processing pass retries it");
    expect(said).toContain("a person can reject the supply");
    expect(said).not.toContain("ValueError");
    for(const [outcome, words] of [["TIMED-OUT", "timed out"], ["CRASHED", "crashed"]])
      expect(w.couldNotCheckWords({...B, tries: {...B.tries, outcome}}, null)).toContain(words);
  });

  it("before its newest try ended, says a check began and has not finished", () => {
    const w = load();
    expect(w.couldNotCheckWords(B, "2026-03-11")).toContain("a check began");
    expect(w.couldNotCheckWords(B, "2026-03-11")).toContain("has not finished");
    expect(w.couldNotCheckWords({...B, tries: {...B.tries, endedAt: null, outcome: null}}, null))
      .toContain("has not finished");
  });

  it("is open from its receipt - or from its decision, for a re-check", () => {
    const w = load();
    expect(w.blockerOpenInPlaceOn(DS, "2026-03-09", SOURCE)).toBeNull();
    expect(w.blockerOpenInPlaceOn(DS, "2026-03-10", SOURCE)).not.toBeNull();
    const recheck = {...B, openedAt: "2026-03-15T02:00:00+00:00"};
    expect(w.blockerOpenInPlaceOn(DS, "2026-03-14", {items: [], blockers: [recheck]})).toBeNull();
    expect(w.blockerOpenInPlaceOn(DS, "2026-03-15", {items: [], blockers: [recheck]})).not.toBeNull();
  });

  it("every one of its checks reads the grey No data, no earlier verdict shown as current", () => {
    const w = load();
    expect(w.checkStatus({current_status: "green", blockedThisPeriod: true})).toBe("nodata");
  });

  it("is in the blocker table under its subtitle, its reason judged as at the date", () => {
    const w = load();
    const html = w.blockerHistoryRows(DS, "2026-03-11", SOURCE);
    expect(html).toContain("or a supply that could not be checked");
    expect(html).toContain('data-blocker="could-not-check"');
    expect(html).toContain("has not finished");
  });
});
