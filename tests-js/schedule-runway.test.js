// Schedule runway and the exhausted state (REQ-PIPE-053).
//
// The failure this is defending against is not a schedule running out.
// It is a schedule running out QUIETLY: no periods means no slots, no
// slots means nothing is owed, nothing is owed means nothing is
// overdue - so the page goes green and STAYS green, which looks
// exactly like a healthy feed.
//
// The nodata trap is the specific shape to keep out: rollup() filters
// noDataAsOf and rollupStatuses() filters nodata before worstOf(), and
// STATUS_ORDER puts nodata at -1 where it can only ever LOSE a reduce
// that starts from green. The obvious derivation lands an exhausted
// schedule in exactly the bucket engineered to vanish.
import { afterEach, describe, expect, it } from "vitest";
import { loadDashboard } from "./support/loadDashboard.js";

let dashboard;

afterEach(() => {
  dashboard?.close();
  dashboard = undefined;
});

// The runway is passed to scheduleRunwayAsOf() rather than assigned
// onto the window: a top-level `const` in a classic script lives in
// script scope, not on globalThis, so assigning SCHEDULE_RUNWAY here
// would create a NEW global the page's own code never reads - every
// assertion would then be made against the embedded null.
function load() {
  dashboard = loadDashboard();
  return dashboard.window;
}

// One authored calendar, two datasets on it, one of which participates
// in fewer periods - which is what makes them run out at different
// times, and is the case a single shared "last date" would get wrong.
const RUNWAY = {
  configFile: "contract/data-asset.yaml",
  defaultThreshold: 4,
  calendars: [{
    name: "quarterly",
    threshold: 4,
    lastPeriod: "2027-Q4",
    lastDate: "2027-11-01",
    datasets: [
      { id: "every-quarter", lastPeriod: "2027-Q4", lastDate: "2027-11-01",
        dates: ["2027-02-01", "2027-05-01", "2027-08-01", "2027-11-01"] },
      { id: "twice-a-year", lastPeriod: "2027-Q3", lastDate: "2027-08-01",
        dates: ["2027-02-01", "2027-08-01"] },
    ],
  }],
};

describe("scheduleRunwayAsOf", () => {
  it("finds nothing exhausted while dates remain", () => {
    const w = load();
    const r = w.scheduleRunwayAsOf("2026-01-01", RUNWAY);
    expect(r.exhaustedCount).toBe(0);
    expect(r.exhausted).toEqual({});
  });

  it("counts remaining slots against the date being VIEWED, not today", () => {
    // The same configuration, three different answers - which is the
    // whole reason the page recomputes this per as-of date instead of
    // reading a boolean baked in at build time.
    const w = load();
    expect(w.scheduleRunwayAsOf("2026-01-01", RUNWAY).low[0].remaining).toBe(2);
    expect(w.scheduleRunwayAsOf("2027-06-01", RUNWAY).low[0].remaining).toBe(1);
    expect(w.scheduleRunwayAsOf("2028-01-01", RUNWAY).low[0].remaining).toBe(0);
  });

  it("says nothing at all once a calendar has room again", () => {
    const w = load();
    const roomy = {...RUNWAY, calendars: [{...RUNWAY.calendars[0], threshold: 1}]};
    expect(w.scheduleRunwayAsOf("2026-01-01", roomy).low).toEqual([]);
  });

  it("lets the dataset that runs out FIRST decide when a calendar is low", () => {
    // twice-a-year has one slot left after Feb 2027; every-quarter has
    // three. The calendar is low because of the former.
    const w = load();
    expect(w.scheduleRunwayAsOf("2027-03-01", RUNWAY).low[0].remaining).toBe(1);
  });

  it("exhausts each dataset on its own last date, not the calendar's", () => {
    const w = load();
    const r = w.scheduleRunwayAsOf("2027-09-01", RUNWAY);
    expect(Object.keys(r.exhausted)).toEqual(["twice-a-year"]);
    expect(r.exhausted["twice-a-year"].lastPeriod).toBe("2027-Q3");
  });

  it("exhausts everything once the calendar itself runs out", () => {
    const w = load();
    const r = w.scheduleRunwayAsOf("2028-01-01", RUNWAY);
    expect(r.exhaustedCount).toBe(2);
  });

  it("is a no-op when nothing is embedded", () => {
    const w = load();
    expect(w.scheduleRunwayAsOf("2028-01-01", null)).toEqual(
      { exhausted: {}, low: [], exhaustedCount: 0 });
  });
});

describe("an exhausted schedule is never absorbed by the rollup", () => {
  // The whole point. Under the naive derivation these all read green.
  const exhausted = { id: "x", scheduleExhausted: {calendar: "q"}, status: "exhausted", columns: [] };
  const healthy = { id: "h", status: "green", columns: [{ status: "green" }] };
  const noData = { id: "n", noDataAsOf: true, status: "nodata", columns: [] };

  it("does not vote green into its parent", () => {
    const w = load();
    expect(w.rollup([exhausted])).toBe("exhausted");
  });

  it("survives beside a dataset that merely has no data", () => {
    const w = load();
    expect(w.rollup([exhausted, noData])).toBe("exhausted");
  });

  it("does not mask a real red beside it", () => {
    const w = load();
    const red = { id: "r", status: "red", columns: [{ status: "red" }] };
    expect(w.rollup([exhausted, red])).toBe("red");
  });

  it("does not turn a healthy collection red either", () => {
    // Rejected explicitly: a supplier's clean dataset reading red
    // because WE forgot to type next year's dates is an attribution
    // error, and the fastest way to teach people red means nothing.
    const w = load();
    expect(w.rollup([exhausted, healthy])).toBe("green");
  });

  it("carries up through rollupStatuses the same way", () => {
    const w = load();
    expect(w.rollupStatuses(["exhausted"])).toBe("exhausted");
    expect(w.rollupStatuses(["exhausted", "nodata"])).toBe("exhausted");
    expect(w.rollupStatuses(["exhausted", "amber"])).toBe("amber");
    expect(w.rollupStatuses(["exhausted", "green"])).toBe("green");
  });

  it("is outside STATUS_ORDER, so worstOf REFUSES to rank it", () => {
    // CORRECTED by REQ-QAC-047, and the correction is the interesting
    // part. This test used to assert that worstOf(["exhausted",
    // "green"]) returns "green", on the reasoning that a status with no
    // rank simply loses every comparison. That reasoning is true of the
    // implementation and wrong about the requirement: returning green
    // for a status you cannot order is precisely the "I do not know
    // what this is" -> "this is fine" conversion that item 74 was
    // about, and REQ-QAC-047's own criterion forbids it in those words.
    //
    // Worth noting HOW it survived: this suite owned its own
    // expectations, so it blessed whatever the page already did. The
    // shared table in status-cases.json exists because a suite that
    // writes its own answers cannot catch that.
    const w = load();
    expect(() => w.worstOf(["exhausted", "green"])).toThrow(/cannot order/);
    expect(() => w.worstOf(["exhausted", "red"])).toThrow(/cannot order/);
  });
});

describe("it is told apart from 'no data' in words, not only colour", () => {
  it("has its own label, not the one 'no data' uses", () => {
    const w = load();
    expect(w.pill("exhausted")).toContain("Schedule ended");
    expect(w.pill("nodata")).toContain("No data");
    expect(w.pill("exhausted")).not.toContain("No data");
  });

  it("renders a pill carrying that label as text", () => {
    const w = load();
    const html = w.pill("exhausted");
    expect(html).toContain("Schedule ended");
    expect(html).toContain("exhausted");
  });
});

describe("exhaustedMarker", () => {
  it("says nothing when nothing is exhausted", () => {
    expect(load(RUNWAY).exhaustedMarker(0)).toBe("");
  });

  it("states the count in words so a tier cannot hide one", () => {
    const w = load();
    expect(w.exhaustedMarker(1)).toContain("1\n    schedule ended");
    expect(w.exhaustedMarker(3)).toContain("schedules ended");
  });
});

// REQ-PIPE-053 asks for the low-runway warning "both in the dashboard
// and as a non-fatal warning in the repository's gates". The gate half
// worked. The dashboard half did not exist: scheduleRunwayAsOf() filled
// out.low, buildData() stored it, and the only consumer was
// exhaustedNotice(), which returns "" unless something is already
// EXHAUSTED - so the warning that exists to arrive BEFORE that point
// could never be seen (post-build-review #2).
//
// Two further criteria were vacuous as a consequence - "warn once for
// that calendar, naming it, its last authored period and how many
// datasets name it", and "distinguish a warning from a failure in text
// as well as colour" - because there was no warning on the page to name
// anything or to distinguish.
//
// Live at the time of writing: the real quarterly calendar has 2 future
// slots against a threshold of 4.
describe("the low-runway warning reaches the page", () => {
  function notice(asOf) {
    const w = load();
    return w.lowRunwayNotice(w.scheduleRunwayAsOf(asOf, RUNWAY));
  }

  it("says nothing at all while there is plenty of runway", () => {
    // A LOWERED THRESHOLD rather than an earlier date: twice-a-year
    // only ever has two dates, so this fixture is "low" at every date
    // in its own past. Same construction the roomy case above uses.
    const w = load();
    const roomy = {...RUNWAY, calendars: [{...RUNWAY.calendars[0], threshold: 1}]};
    expect(w.lowRunwayNotice(w.scheduleRunwayAsOf("2026-01-01", roomy))).toBe("");
  });

  it("warns once for the calendar, naming it", () => {
    const html = notice("2027-03-01");
    expect(html).toContain("quarterly");
    expect((html.match(/quarterly/g) || []).length).toBeGreaterThan(0);
  });

  it("names the dataset the number belongs to, and that dataset's own last period", () => {
    // Same correction as the CLI's own warning (#22): `remaining` is a
    // MINIMUM across datasets, so naming the calendar's last period
    // pairs a number and a date belonging to different objects.
    const html = notice("2027-03-01");
    expect(html).toContain("twice-a-year");
    expect(html).toContain("2027-Q3");
  });

  it("says how many datasets name the calendar, without listing them all", () => {
    const html = notice("2027-03-01");
    expect(html).toContain("2 datasets");
    expect(html).not.toContain("every-quarter");
  });

  it("distinguishes itself from a failure in TEXT, not only in colour", () => {
    const html = notice("2027-03-01");
    expect(html).toMatch(/not failing|nothing has failed|no failure/i);
  });

  it("gives way to the exhausted notice rather than stacking with it", () => {
    // Once a calendar has actually run out, "running low" is no longer
    // the news and two notices about one calendar is noise.
    const w = load();
    const runway = w.scheduleRunwayAsOf("2028-01-01", RUNWAY);
    expect(runway.exhaustedCount).toBeGreaterThan(0);
    expect(w.lowRunwayNotice(runway)).toBe("");
  });

  it("carries the driving dataset on the runway itself, not only in prose", () => {
    const w = load();
    const low = w.scheduleRunwayAsOf("2027-03-01", RUNWAY).low[0];
    expect(low.drivingDataset).toBe("twice-a-year");
    expect(low.drivingLastPeriod).toBe("2027-Q3");
  });
});
