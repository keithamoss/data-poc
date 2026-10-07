// REQ-DASH-155 (Keith, signed 2026-10-06): the exhausted-schedule notice says
// how many supplies are held because a schedule ended and since when - never
// a day count - from hold records as at the date on show, aggregated; and a
// dataset reads exhausted only once its last slot has CLOSED.
import { describe, it, expect } from "vitest";
import { loadDashboard } from "./support/loadDashboard.js";

const RUNWAY = {configFile: "contract/data-asset.yaml", defaultThreshold: 4, calendars: [{
  name: "quarterly", threshold: 4, lastPeriod: "2027-Q4", lastDate: "2027-11-01",
  datasets: [
    {id: "cp-clients", lastPeriod: "2027-Q4", lastDate: "2027-11-01", endsOn: "2028-01-31",
     dates: ["2027-08-01", "2027-11-01"]},
    {id: "cp-carers", lastPeriod: "2027-Q4", lastDate: "2027-11-01", endsOn: "2028-01-31",
     dates: ["2027-08-01", "2027-11-01"]}]}]};

const HOLDS = {
  "cp-clients": [{receivedAt: "2028-03-02T01:00:00+00:00", resolvedAt: null},
                 {receivedAt: "2028-02-05T01:00:00+00:00", resolvedAt: "2028-06-01T01:00:00+00:00"}],
  "cp-carers": [{receivedAt: "2028-04-01T01:00:00+00:00", resolvedAt: null}]};

function page(){
  const w = loadDashboard().window;
  w.rawRealDatasets = () => Object.entries(HOLDS).map(([id, held])=> ({id, scheduleEndedHolds: held}));
  return w;
}

describe("exhausted from when the last slot closes", () => {
  it("is not exhausted after the last period's date while its slot is open", () => {
    const w = page();
    expect(w.scheduleRunwayInPlaceOn("2027-12-15", RUNWAY).exhaustedCount).toBe(0);
  });
  it("is exhausted from the day the last slot closes", () => {
    const w = page();
    expect(w.scheduleRunwayInPlaceOn("2028-01-31", RUNWAY).exhaustedCount).toBe(2);
  });
});

describe("the notice counts what is held behind it", () => {
  it("counts the supplies held as at the date, with the earliest receipt", () => {
    const w = page();
    const html = w.exhaustedNotice(w.scheduleRunwayInPlaceOn("2028-04-15", RUNWAY), "2028-04-15");
    expect(html).toContain("3 supplies are held because of it");
    expect(html).toContain("5 February 2028");
    expect(html).not.toMatch(/\d+ days?/);
  });
  it("leaves out a hold resolved before the date, and one received after it", () => {
    const w = page();
    const html = w.exhaustedNotice(w.scheduleRunwayInPlaceOn("2028-07-01", RUNWAY), "2028-03-15");
    expect(html).toContain("2 supplies are held because of it");
    const later = w.exhaustedNotice(w.scheduleRunwayInPlaceOn("2028-07-01", RUNWAY), "2028-07-01");
    expect(later).toContain("2 supplies are held because of it");
    expect(later).toContain("2 March 2028");
  });
  it("says nothing has arrived when nothing is held", () => {
    const w = page();
    const html = w.exhaustedNotice(w.scheduleRunwayInPlaceOn("2028-02-01", RUNWAY), "2028-02-01");
    expect(html).toContain("Nothing has arrived for them since.");
  });
});

describe("the notice names each dataset by its own dates (post-build-review #132 A4)", () => {
  it("names the dataset and its last period, and says filing waits rather than processing", () => {
    const w = page();
    w.rawRealDatasetById = id => ({id, name: id === "cp-clients" ? "Client Register" : "Carers"});
    const html = w.exhaustedNotice(w.scheduleRunwayInPlaceOn("2028-02-01", RUNWAY), "2028-02-01");
    expect(html).toContain("Client Register");
    expect(html).toContain("its last delivery date is for");
    expect(html).toContain("cannot be filed");
    expect(html).not.toContain("cannot be processed");
    expect(html).toContain("still received and its files checked");
  });
});

describe("a supply held because its schedule ended (Keith, 2026-10-07: add dates only)", () => {
  it("says to add dates, not that a person must resolve it", () => {
    const w = loadDashboard().window;
    const b = {kind: "held", scheduleEnded: true, count: 1};
    expect(w.blockerReasonText(b)).toContain("Held: schedule ended");
    expect(w.blockerReasonText(b)).toContain("files itself on the next processing pass");
    expect(w.blockerUntil(b)).not.toContain("a person");
  });
  it("leaves any other hold as it was", () => {
    const w = loadDashboard().window;
    expect(w.blockerReasonText({kind: "held", count: 1})).toContain("waiting for a person");
  });
  it("shows a recorded command as code", () => {
    expect(loadDashboard().window.withCode("run `mothman x` now")).toBe("run <code>mothman x</code> now");
  });
});
