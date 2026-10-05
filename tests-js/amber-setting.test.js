// REQ-PIPE-122 NFR 1 (built 2026-10-05): the amber setting in force on the
// date on show, and where it was set, on the dataset's page.
import { describe, it, expect } from "vitest";
import { loadDashboard } from "./support/loadDashboard.js";

const DS = {amberSetting: [
  {from: "2023-01-01", value: "promote", text: "promote (set for the whole data asset, since 1 Jan 2023)"},
  {from: "2026-10-05", value: "promote-and-acknowledge",
   text: "promote and acknowledge (set for Child Protection, since 5 Oct 2026)"}]};

describe("the amber setting on the date on show", () => {
  it("is the latest change on or before that date", () => {
    const w = loadDashboard().window;
    expect(w.amberSettingAsOf(DS, "2026-10-04").value).toBe("promote");
    expect(w.amberSettingAsOf(DS, "2026-10-05").value).toBe("promote-and-acknowledge");
    expect(w.amberSettingAsOf(DS, "2022-12-31")).toBeNull();
  });

  it("is said in words, naming where it was set", () => {
    const w = loadDashboard().window;
    const html = w.amberSettingLine(DS, "2026-10-06");
    expect(html).toContain("Amber setting: promote and acknowledge (set for Child Protection, since 5 Oct 2026)");
    expect(w.amberSettingLine({}, "2026-10-06")).toBe("");
  });
});
