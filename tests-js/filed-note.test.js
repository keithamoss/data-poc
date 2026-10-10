// REQ-PIPE-147 criterion 7 and REQ-PIPE-103 criterion 19: the arrival
// detail says whether a person filed a supply, by which route and who, and
// sets their statement of the original arrival BESIDE our receipt.
import { describe, it, expect } from "vitest";
import { loadDashboard } from "./support/loadDashboard.js";

const load = () => loadDashboard().window;

describe("who filed a supply, and when they say it arrived", () => {
  it("names the person and the route for a supply filed by hand", () => {
    const w = load();
    const html = w.filedNote({filedBy: {kind: "person", route: "folder", who: "Keith Moss"},
                              statedOriginal: "2026-09-20T10:00:00+08:00",
                              arrivedAt: "2026-09-25T09:00:00+08:00"});
    expect(html).toContain("by hand");
    expect(html).toContain("Keith Moss");
    expect(html).toContain("a folder");
    expect(html).toContain("(stated)");
    // Labelled as a statement and never as the receipt.
    expect(html).toContain("never used to file or judge");
    expect(html).not.toMatch(/2026-09-20T10/);
  });

  it("says not known as such, never as a time", () => {
    const w = load();
    const html = w.filedNote({filedBy: {kind: "person", route: "file", who: "a"},
                              statedOriginal: "not-known"});
    expect(html).toContain("not known");
  });

  it("adds nothing to a row received automatically, and says so on hover", () => {
    const w = load();
    const e = {filedBy: {kind: "automated"}};
    expect(w.filedNote(e)).toBe("");
    expect(w.receivedTitle(e)).toBe("Received automatically");
  });
});
