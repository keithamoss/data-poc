// The selected asset's snapshot archive in the panel (REQ-DASH-373 criteria 3
// and 5): links into snapshots/<asset>/, and an empty archive says when it
// starts - never the old developer instruction.
import { afterEach, describe, expect, it } from "vitest";
import { readFileSync } from "node:fs";
import { loadDashboard } from "./support/loadDashboard.js";

const TEMPLATE = readFileSync(new URL("../dashboard/qa-reporting-dashboard.template.html", import.meta.url), "utf8");
// The page as a build embeds it: the template with SNAPSHOT_ARCHIVE set.
const withArchive = archive => {
  const html = TEMPLATE.replace("const SNAPSHOT_ARCHIVE = null;", `const SNAPSHOT_ARCHIVE = ${JSON.stringify(archive)};`);
  if(html === TEMPLATE) throw new Error("SNAPSHOT_ARCHIVE placeholder not found");
  return loadDashboard({ html });
};

let dashboard;
afterEach(() => { dashboard?.close(); dashboard = undefined; });

describe("the snapshots panel (REQ-DASH-373)", () => {
  it("says when an empty archive starts, in the settled words", () => {
    dashboard = withArchive({asset: "quarterly", from: "2026-11-21"});
    const w = dashboard.window;
    w.renderSnapshotsPanel();
    const text = w.document.getElementById("snapshots-panel-body").textContent.replace(/\s+/g, " ").trim();
    expect(text).toBe("Snapshots start from this asset's first publish after the split, Saturday, 21 November 2026.");
    expect(text).not.toContain("mothman pipeline run --snapshot");
  });

  it("links each snapshot into the asset's own folder", () => {
    dashboard = withArchive({asset: "daily", from: "2026-11-21"});
    const w = dashboard.window;
    expect(w.snapshotHref("20261121T000000Z_abc1234.html")).toBe("snapshots/daily/20261121T000000Z_abc1234.html");
  });

  it("links where it always did in the raw template, with no archive embedded", () => {
    dashboard = loadDashboard();
    expect(dashboard.window.snapshotHref("x.html")).toBe("snapshots/x.html");
  });
});
