// REQ-DASH-180: a turned-off dataset reads as turned off - its real verdict,
// a marker worded for where it is in the turn-off, out of its group's rollup
// only once it owes nothing more, and its group 'Turned off' or 'Not counted'
// rather than green.
import { afterEach, describe, expect, it } from "vitest";
import { loadDashboard } from "./support/loadDashboard.js";

let dashboard;
afterEach(() => { dashboard?.close(); dashboard = undefined; });
const load = () => (dashboard = loadDashboard()).window;

const LAST = { period: "2025-Q1", dueAt: "2025-02-01T01:00:00+00:00",
               closesAt: "2025-04-20T16:00:00+00:00" };
const TURN = { effectiveTo: "2025-03-31", until: "2026-01-01", reason: "supplier paused",
               level: "dataset", versionFrom: "2023-01-01", authoredOn: "2025-02-15",
               authoredBy: "changelog", collection: "Child Protection", lastOwed: LAST };
const ds = (turn = TURN, extra = {}) => ({ id: "cp-clients", name: "Client Register",
  turnOffs: [turn], runs: [], arrivalByRun: {}, ...extra });

describe("the marker, as at the date on show (criteria 1, 4, 25, 27 and 28)", () => {
  it("says nothing before the turn-off was authored", () => {
    expect(load().turnOffOn(ds(), "2025-02-10")).toBeNull();
  });

  it("announces it from when it was authored until the effective_to", () => {
    const w = load();
    expect(w.turnOffOn(ds(), "2025-03-01").text).toBe(`Turning off after ${w.fmtDay("2025-03-31")}`);
    const coll = ds({ ...TURN, level: "collection" });
    expect(w.turnOffOn(coll, "2025-03-01").text)
      .toBe(`Turning off with Child Protection after ${w.fmtDay("2025-03-31")}`);
    expect(w.turnOffOn(ds(), "2025-03-01").leftOut).toBe(false);
  });

  it("is never announced when authored after its effective_to (criterion 28)", () => {
    const w = load();
    const late = ds({ ...TURN, authoredOn: "2025-04-10" });
    expect(w.turnOffOn(late, "2025-03-01")).toBeNull();
    expect(w.turnOffOn(late, "2025-04-12").text).toContain("supply still owed");
  });

  it("says the last owed period is still owed while its slot is open", () => {
    const w = load();
    const got = w.turnOffOn(ds(), "2025-04-05");
    expect(got.text).toBe(`Turning off - 2025-Q1 supply still owed, open until ${w.fmtInstant(LAST.closesAt)}`);
    expect(got.leftOut).toBe(false);
  });

  it("and open for resupply once it has a supply", () => {
    const w = load();
    const filed = ds(TURN, { runs: [{ run_id: "r1", run_date: "2025-02-03" }],
                            arrivalByRun: { r1: { slot: "2025-Q1" } } });
    expect(w.turnOffOn(filed, "2025-04-05").text).toBe(
      `Turned off since ${w.fmtDay("2025-04-01")} - 2025-Q1 open for resupply until ${w.fmtInstant(LAST.closesAt)}`);
  });

  it("reads turned off, left out of the rollup, once the last slot has closed", () => {
    const w = load();
    const got = w.turnOffOn(ds(), "2025-05-01");
    expect(got.text).toBe(`Turned off since ${w.fmtDay("2025-04-01")}`);
    expect(got.leftOut).toBe(true);
    expect(w.turnOffOn(ds({ ...TURN, level: "collection" }), "2025-05-01").text)
      .toBe(`Turned off with Child Protection since ${w.fmtDay("2025-04-01")}`);
  });

  it("says nothing more is owed when the last slot closes before the effective_to (criterion 25)", () => {
    const w = load();
    const later = ds({ ...TURN, effectiveTo: "2025-06-30" });
    const got = w.turnOffOn(later, "2025-05-10");
    expect(got.text).toBe(`Turning off after ${w.fmtDay("2025-06-30")} - nothing more owed`);
    expect(got.leftOut).toBe(true);
  });

  it("waits for the turn-off to be authored before 'nothing more owed' (criterion 25 as amended, Q21)", () => {
    // Keith, 2026-10-15: before the date it was authored, the page shows what
    // was known then - still owing, still in the rollup.
    const w = load();
    const later = ds({ ...TURN, effectiveTo: "2025-06-30", authoredOn: "2025-05-20" });
    expect(w.turnOffOn(later, "2025-05-10")).toBeNull();
    const got = w.turnOffOn(later, "2025-05-25");
    expect(got.phase).toBe("nothing-more-owed");
    expect(got.leftOut).toBe(true);
  });

  it("is gone once the dataset is back on (criterion 18)", () => {
    expect(load().turnOffOn(ds(), "2026-02-01")).toBeNull();
  });

  it("renders the reason as text in the marker's title (criteria 2 and 21)", () => {
    const w = load();
    const html = w.turnOffMarker(ds({ ...TURN, reason: "<b>x</b>" }), "2025-05-01");
    expect(html).toContain('title="&lt;b&gt;x&lt;/b&gt;"');
    expect(html).toContain("turnoff-marker");
  });
});

describe("the rollup (criteria 6 to 11)", () => {
  const green = { id: "g", status: "green", columns: [{ status: "green" }] };
  const off = { id: "o", status: "red", columns: [{ status: "red" }], turnedOffOutOfRollup: true };
  const unagreed = { id: "u", status: "green", columns: [{ status: "green" }], scheduleNotAgreed: true };

  it("leaves a turned-off dataset out, red verdict and all", () => {
    expect(load().rollup([green, off])).toBe("green");
  });

  it("reads 'Turned off' where every dataset is out by turn-off, never green", () => {
    const w = load();
    expect(w.rollup([off, { ...off, id: "o2" }])).toBe("turnedoff");
    expect(w.eval("STATUS_LABEL").turnedoff).toBe("Turned off");
  });

  it("reads 'Not counted' where all are out but not all by turn-off", () => {
    expect(load().rollup([off, unagreed])).toBe("notcounted");
  });

  it("places turnedoff last among the quiet states", () => {
    const w = load();
    expect(w.rollupStatuses(["turnedoff"])).toBe("turnedoff");
    expect(w.rollupStatuses(["turnedoff", "notcounted"])).toBe("notcounted");
    expect(w.rollupStatuses(["turnedoff", "amber"])).toBe("amber");
  });

  it("names turned-off datasets among the reasons, by count", () => {
    const w = load();
    expect(w.notCountedReasons([off, unagreed])).toEqual({ "turned off": 1, "no schedule agreed yet": 1 });
  });

  it("says in one line when some datasets are left out (criterion 10)", () => {
    const w = load();
    const el = w.document.createElement("div");
    el.innerHTML = w.notCountedMarker("green", [green, off]);
    expect(el.textContent.replace(/\s+/g, " ").trim())
      .toBe("1 dataset not counted in this status: 1 turned off");
    expect(w.notCountedMarker("turnedoff", [off])).toBe("");
  });
});

describe("the SLA tile while turned off (criterion 16)", () => {
  const sla = { cadence: { type: "quarterly", anchor_months: [2, 5, 8, 11], day_of_month: 1,
                           expected_time: "09:00" }, owesFrom: "2023-01-01",
                versions: [{ from: "2023-01-01", reason: null,
                             cadence: { type: "quarterly", anchor_months: [2, 5, 8, 11],
                                        day_of_month: 1, expected_time: "09:00" } }] };
  it("reads 'Turned off — nothing due' once nothing owed is open", () => {
    const w = load();
    const html = w.slaTileHtml(ds(TURN, { sla }), "2025-05-01");
    expect(html).toContain("Turned off — nothing due");
    expect(html).not.toContain("by 09:00");
  });

  it("gives the still-owed period's due time, labelled with the period", () => {
    const w = load();
    const html = w.slaTileHtml(ds(TURN, { sla }), "2025-04-05");
    expect(html).toContain(`2025-Q1 due ${w.fmtInstant(LAST.dueAt)}`);
  });

  it("is the ordinary tile before the turn-off", () => {
    expect(load().slaTileHtml(ds(TURN, { sla }), "2025-03-01")).toContain("Quarterly (Feb, May, Aug, Nov, day 1), by 09:00");
  });
});

describe("a supply received while turned off (criterion 14)", () => {
  const held = (at, extra = {}) => ({ kind: "held", datasetId: "cp-clients", supply: `cp-clients@${at}`,
    openedAt: at, resolvedAt: null, turnedOff: { effective_to: "2025-03-31", reason: "supplier paused" }, ...extra });
  const source = { blockers: [held("2025-06-02T01:00:00+00:00"), held("2025-07-02T01:00:00+00:00"),
    held("2025-09-02T01:00:00+00:00")] };

  it("is counted as at the date on show, in one quiet line", () => {
    const w = load();
    const el = w.document.createElement("div");
    el.innerHTML = w.receivedWhileOffLine("cp-clients", "2025-08-01", source);
    expect(el.textContent.replace(/\s+/g, " ").trim())
      .toBe(`2 received while turned off, earliest ${w.fmtDay("2025-06-02")} · 2 still held`);
    expect(el.querySelector(".accepted-gaps-note")).not.toBeNull();
    expect(w.receivedWhileOffLine("cp-clients", "2025-05-01", source)).toBe("");
  });

  it("has its own quiet section in supply history, never red", () => {
    const w = load();
    const html = w.receivedWhileOffSection("cp-clients", "2025-08-01", source);
    expect(html).toContain("Received while turned off");
    expect(html).toContain("cp-clients@2025-07-02T01:00:00+00:00");
    expect(html).not.toContain("pill red");
    expect(html).not.toContain("Waiting for a person");
  });
});

// REQ-DASH-180 criterion 14 AS AMENDED 2026-10-15 (Keith; post-build-review
// #196 F2): every supply held while off is listed, each resolved one saying
// how it ended, and the line says how many are still held.
describe("criterion 14 as amended: how each one ended", () => {
  const held = (at, extra = {}) => ({ kind: "held", datasetId: "cp-clients", supply: `cp-clients@${at}`,
    openedAt: at, resolvedAt: null, turnedOff: { reason: "supplier paused" }, ...extra });
  const ended = (at, e) => ({ resolvedAt: at, ended: { at, reason: "", actor: null, toPeriod: null, ...e } });
  const source = { blockers: [
    held("2025-06-02T01:00:00+00:00"),
    held("2025-06-03T01:00:00+00:00", ended("2025-07-01T01:00:00+00:00",
      { action: "refile", actorKind: "rule", toPeriod: "2025-Q3" })),
    held("2025-06-04T01:00:00+00:00", ended("2025-07-02T01:00:00+00:00",
      { action: "reject", actorKind: "person", actor: "Keith Moss", reason: "a duplicate" })),
    held("2025-06-05T01:00:00+00:00", ended("2025-07-03T01:00:00+00:00",
      { action: "supersede", actorKind: "rule" })),
  ] };

  it("says how each resolved one ended, and that the open one is held and owed by nobody", () => {
    const w = load();
    const el = w.document.createElement("div");
    el.innerHTML = w.receivedWhileOffSection("cp-clients", "2025-08-01", source);
    const rows = [...el.querySelectorAll("tbody tr")].map(r => r.textContent.replace(/\s+/g, " "));
    expect(rows).toHaveLength(4);
    expect(rows[0]).toContain("held, and owed by nobody");
    expect(rows[1]).toContain("filed by the rule once 2025-Q3 was owed again");
    expect(rows[2]).toContain("rejected by Keith Moss");
    expect(rows[2]).toContain("a duplicate");
    expect(rows[3]).toContain("superseded");
    expect(rows.slice(1).some(r => r.includes("owed by nobody"))).toBe(false);
  });

  it("is still open on a date before it ended", () => {
    const w = load();
    const el = w.document.createElement("div");
    el.innerHTML = w.receivedWhileOffSection("cp-clients", "2025-06-20", source);
    const rows = [...el.querySelectorAll("tbody tr")].map(r => r.textContent);
    expect(rows.every(r => r.includes("held, and owed by nobody"))).toBe(true);
  });

  it("counts them all and says how many are still held", () => {
    const w = load();
    const el = w.document.createElement("div");
    el.innerHTML = w.receivedWhileOffLine("cp-clients", "2025-08-01", source);
    expect(el.textContent.replace(/\s+/g, " ").trim())
      .toBe(`4 received while turned off, earliest ${w.fmtDay("2025-06-02")} · 1 still held`);
  });
});

describe("a late supply for a period still owed after the turn-off (criterion 19)", () => {
  it("says the period was still owed, and nothing about excusing it", () => {
    const w = load();
    const raw = ds(TURN, { runs: [{ run_id: "r1", run_date: "2025-04-03" }],
                           arrivalByRun: { r1: { slot: "2025-Q1", arrivedAt: "2025-04-03T01:00:00+00:00" } } });
    const note = w.stillOwedNote(raw, "r1");
    expect(note).toContain("2025-Q1 was still owed after the turn-off");
    expect(note).not.toContain("excused");
    const early = ds(TURN, { runs: [{ run_id: "r0", run_date: "2025-02-02" }],
                             arrivalByRun: { r0: { slot: "2025-Q1", arrivedAt: "2025-02-02T01:00:00+00:00" } } });
    expect(w.stillOwedNote(early, "r0")).toBe("");
  });
});

describe("the runway and the exhausted notice (criterion 17)", () => {
  // Judged on the date on show (criterion 20): off for good from 2028-01-01.
  const RUNWAY = { calendars: [{ name: "quarterly", threshold: 2, lastPeriod: "2027-Q4", lastDate: "2027-11-01",
    datasets: [{ id: "cp-clients", dates: ["2027-08-01", "2027-11-01"], lastPeriod: "2027-Q4",
                 lastDate: "2027-11-01", endsOn: "2027-12-20", offGaps: [{ from: "2028-01-01", until: null }] }] }] };

  it("counts a dataset off for good only up to the day it goes off", () => {
    const w = load();
    expect(w.scheduleRunwayInPlaceOn("2027-12-25", RUNWAY).exhaustedCount).toBe(1);
    expect(w.scheduleRunwayInPlaceOn("2028-01-02", RUNWAY).exhaustedCount).toBe(0);
    expect(w.scheduleRunwayInPlaceOn("2028-01-02", RUNWAY).low).toEqual([]);
  });

  it("is not exhausted inside a temporary gap, and still warns by what it owes (REQ-PIPE-053 c19 as amended)", () => {
    const w = load();
    const temp = JSON.parse(JSON.stringify(RUNWAY));
    temp.calendars[0].datasets[0].offGaps = [{ from: "2027-12-22", until: "2028-06-01" }];
    expect(w.scheduleRunwayInPlaceOn("2028-01-02", temp).exhaustedCount).toBe(0);
    expect(w.scheduleRunwayInPlaceOn("2027-12-21", temp).exhaustedCount).toBe(1);
    expect(w.scheduleRunwayInPlaceOn("2028-07-01", temp).exhaustedCount).toBe(1);
    expect(w.scheduleRunwayInPlaceOn("2027-09-01", temp).low.length).toBe(1);
  });
});

describe("a collection's own turn-off on its card (criterion 2)", () => {
  it("shows the collection's turned_off_reason, once", () => {
    const w = load();
    const t = { reason: "<i>paused</i>", level: "collection", turnOff: { collection: "Child Protection" } };
    const col = { datasets: [{ id: "a", turnOff: t }, { id: "b", turnOff: t }, { id: "c", turnOff: null }] };
    const html = w.collectionTurnOffLine(col);
    expect(html).toContain("&lt;i&gt;paused&lt;/i&gt;");
    expect(html.match(/paused/g)).toHaveLength(1);
    expect(w.collectionTurnOffLine({ datasets: [{ id: "a", turnOff: { ...t, level: "dataset" } }] })).toBe("");
  });
});

describe("post-build-review #195", () => {
  it("D1: a supply waiting for a decision on an owed period keeps it in the rollup", () => {
    const w = load();
    const off = { turnOff: { leftOut: true } };
    expect(w.outByTurnOff(off)).toBe(true);
    expect(w.outByTurnOff({ ...off, verdictOf: { state: "awaiting" } })).toBe(false);
    expect(w.outByTurnOff({ ...off, waitingBlocker: {} })).toBe(false);
    expect(w.outByTurnOff({ turnOff: { leftOut: false } })).toBe(false);
  });

  it("D2: one marking, shared by the rollup and the per-date statuses", () => {
    const w = load();
    w.rawRealDatasetById = () => ds();
    const data = { agencies: [{ collections: [{ datasets: [{ id: "cp-clients" }] }] }] };
    w.markTurnOffs(data, "2025-05-01");
    expect(data.agencies[0].collections[0].datasets[0].turnedOffOutOfRollup).toBe(true);
  });

  it("D4: '(turned off)' only once it is turned off", () => {
    const w = load();
    const named = (phase) => ({ name: "Client Register", turnOff: { phase } });
    expect(w.turnedOffName(named("announced"))).toBe("Client Register");
    expect(w.turnedOffName(named("nothing-more-owed"))).toBe("Client Register");
    expect(w.turnedOffName(named("off"))).toBe("Client Register (turned off)");
    expect(w.turnedOffName(named("still-owed"))).toBe("Client Register (turned off)");
  });

  it("D5: the header and card say 'Turning off' before it happens", () => {
    const w = load();
    const t = (phase) => ({ phase, reason: "r", level: "collection", turnOff: { collection: "Child Protection" } });
    expect(w.turnOffReasonLine({ turnOff: t("announced") })).toContain("Turning off with Child Protection: r");
    expect(w.turnOffReasonLine({ turnOff: t("off") })).toContain("Turned off with Child Protection: r");
    expect(w.collectionTurnOffLine({ datasets: [{ turnOff: t("announced") }] })).toContain("Turning off with Child Protection: r");
  });

  it("F11: with no slot owed before the gap, nothing reads 'nothing more owed' before the effective_to", () => {
    const w = load();
    const none = ds({ ...TURN, lastOwed: null });
    expect(w.turnOffOn(none, "2020-01-01")).toBeNull();
    expect(w.turnOffOn(none, "2025-05-01").phase).toBe("off");
  });

  it("F12: the received-while-off line gives a date, and reasons come most first", () => {
    const w = load();
    const held = (at) => ({ kind: "held", datasetId: "cp-clients", supply: `s@${at}`, openedAt: at,
                            resolvedAt: null, turnedOff: { reason: "r" } });
    const el = w.document.createElement("div");
    el.innerHTML = w.receivedWhileOffLine("cp-clients", "2025-08-01", { blockers: [held("2025-06-02T01:00:00+00:00")] });
    expect(el.textContent.trim()).toBe(`1 received while turned off, earliest ${w.fmtDay("2025-06-02")} · 1 still held`);
    const off = { id: "o", turnedOffOutOfRollup: true };
    const un = { id: "u", scheduleNotAgreed: "not-yet-agreed" };
    el.innerHTML = w.notCountedMarker("notcounted", [off, { ...off, id: "o2" }, un]);
    expect(el.textContent.replace(/\s+/g, " ").trim()).toBe("3 datasets not counted: 2 turned off, 1 no schedule agreed yet");
  });
});

// REQ-DASH-180 criterion 10 names the executive tier too (Keith, 2026-10-15,
// morning report 5 Q22 - #195 F7 found it only on the cards).
describe("the asset level says how many datasets are not counted", () => {
  const off = { id: "o", turnedOffOutOfRollup: true, status: "green" };
  const counted = { id: "c", status: "red" };
  const agencies = (...ds) => [{ id: "a", status: "red", collections: [{ id: "k", datasets: ds }] }];

  it("one quiet line across every agency", () => {
    const w = load();
    const el = w.document.createElement("div");
    el.innerHTML = w.assetNotCountedLine(agencies(off, { ...off, id: "o2" }, counted));
    expect(el.textContent.replace(/\s+/g, " ").trim())
      .toBe("2 datasets not counted in this status: 2 turned off");
  });

  it("says nothing where every dataset is counted", () => {
    expect(load().assetNotCountedLine(agencies(counted))).toBe("");
  });
});
