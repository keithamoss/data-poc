// Plans tab filter persistence in the URL (Keith's own ask, 2026-09-19) -
// q=/status=/component=/file= in location.search, written on every real
// filter mutation (writePlansFilterToUrl()) and read once on real tier
// entry (render()'s own dispatch calling plansFilterFromUrl() - never
// inside renderPlans() itself, which also runs on every internal chip-
// toggle re-render and would otherwise stomp the just-applied change).
import { JSDOM } from "jsdom";
import { afterEach, describe, expect, it } from "vitest";
import { TEMPLATE_PATH } from "./support/loadDashboard.js";
import { readFileSync } from "node:fs";

const html = readFileSync(TEMPLATE_PATH, "utf-8");
let dom;

afterEach(() => {
  dom?.window.close();
  dom = undefined;
});

function stubMatchMedia(window) {
  window.matchMedia = window.matchMedia || function matchMedia(query) {
    return {
      matches: false,
      media: query,
      addListener() {},
      removeListener() {},
      addEventListener() {},
      removeEventListener() {},
      dispatchEvent() { return false; },
    };
  };
  window.scrollTo = function scrollTo() {};
}

// beforeParse (not a post-construction assignment) - the page's own
// top-level script runs synchronously as part of parsing, and calls
// currentTheme() (which touches matchMedia) before reaching later
// top-level statements like `const SIDE_PANELS = [...]`. Stubbing after
// construction is too late: currentTheme() throws, aborting the script's
// own top-level run partway through, leaving SIDE_PANELS permanently in
// its TDZ even though the (hoisted) functions that reference it remain
// callable - the exact "Cannot access 'SIDE_PANELS' before
// initialization" this pattern avoids. Matches loadDashboard.js's own
// established stubMatchMedia/beforeParse pattern.
function loadAt(url) {
  dom = new JSDOM(html, { url, runScripts: "dangerously", pretendToBeVisual: true, beforeParse: stubMatchMedia });
  return dom.window;
}

describe("Plans filter chips write their state into the URL", () => {
  it("toggling a status chip sets status= in location.search", () => {
    const w = loadAt("http://localhost/");
    w.navigate({ tier: "plans" });
    const doneChip = [...w.document.querySelectorAll('[data-kind="status"]')].find(b => b.dataset.value === "done");
    doneChip.click();
    expect(new w.URLSearchParams(w.location.search).get("status")).toBe("done");
  });

  it("toggling a second status chip joins them comma-separated", () => {
    const w = loadAt("http://localhost/");
    w.navigate({ tier: "plans" });
    const chips = w.document.querySelectorAll('[data-kind="status"]');
    [...chips].find(b => b.dataset.value === "done").click();
    [...w.document.querySelectorAll('[data-kind="status"]')].find(b => b.dataset.value === "todo").click();
    const value = new w.URLSearchParams(w.location.search).get("status");
    expect(value.split(",").sort()).toEqual(["done", "todo"]);
  });

  it("toggling a chip back off removes it from the URL", () => {
    const w = loadAt("http://localhost/");
    w.navigate({ tier: "plans" });
    const doneChip = () => [...w.document.querySelectorAll('[data-kind="status"]')].find(b => b.dataset.value === "done");
    doneChip().click();
    doneChip().click();
    expect(new w.URLSearchParams(w.location.search).has("status")).toBe(false);
  });

  it("typing a search query sets q= in location.search", () => {
    const w = loadAt("http://localhost/");
    w.navigate({ tier: "plans" });
    const input = w.document.getElementById("plans-search");
    input.value = "resupply";
    input.dispatchEvent(new w.Event("input"));
    expect(new w.URLSearchParams(w.location.search).get("q")).toBe("resupply");
  });

  it("clearing filters removes all real filter params from the URL", () => {
    const w = loadAt("http://localhost/");
    w.navigate({ tier: "plans" });
    [...w.document.querySelectorAll('[data-kind="status"]')].find(b => b.dataset.value === "done").click();
    w.document.getElementById("plans-clear-filters").click();
    const params = new w.URLSearchParams(w.location.search);
    expect(params.has("status")).toBe(false);
    expect(params.has("q")).toBe(false);
  });

  it("does not push a new history entry per chip click (replaceState, not pushState)", () => {
    const w = loadAt("http://localhost/");
    w.navigate({ tier: "plans" });
    const before = w.history.length;
    [...w.document.querySelectorAll('[data-kind="status"]')].find(b => b.dataset.value === "done").click();
    [...w.document.querySelectorAll('[data-kind="status"]')].find(b => b.dataset.value === "todo").click();
    expect(w.history.length).toBe(before);
  });
});

describe("Plans tab restores filters from a URL on real entry", () => {
  it("loading directly on a URL with status=/component= pre-applies both filters", () => {
    const w = loadAt("http://localhost/?status=done&component=Dashboard%20UI#/plans");
    w.STATE = w.stateFromLocation();
    w.renderFromState();
    const activeValues = [...w.document.querySelectorAll(".plans-chip-toggle.active")].map(b => b.dataset.value);
    expect(activeValues).toContain("done");
    expect(activeValues).toContain("Dashboard UI");
  });

  it("loading directly on a URL with q= pre-fills the search box", () => {
    const w = loadAt("http://localhost/?q=resupply#/plans");
    w.STATE = w.stateFromLocation();
    w.renderFromState();
    expect(w.document.getElementById("plans-search").value).toBe("resupply");
  });

  it("a chip toggle after a URL-restored load does not lose the other still-active filter", () => {
    const w = loadAt("http://localhost/?status=done&component=Dashboard%20UI#/plans");
    w.STATE = w.stateFromLocation();
    w.renderFromState();
    // Toggle component off; status=done must survive (regression coverage
    // for the exact chicken-and-egg bug this design deliberately avoids -
    // re-reading the URL inside renderPlans() itself would stomp this).
    [...w.document.querySelectorAll('[data-kind="component"]')].find(b => b.dataset.value === "Dashboard UI").click();
    const params = new w.URLSearchParams(w.location.search);
    expect(params.get("status")).toBe("done");
    expect(params.has("component")).toBe(false);
  });
});

describe("Plans filter chips render with real .pill status colours", () => {
  it("status chips carry the same PLANS_STATUS_CLASS colour class real item pills use", () => {
    const w = loadAt("http://localhost/");
    w.navigate({ tier: "plans" });
    const doneChip = [...w.document.querySelectorAll('[data-kind="status"]')].find(b => b.dataset.value === "done");
    expect(doneChip.classList.contains("pill")).toBe(true);
    expect(doneChip.classList.contains("green")).toBe(true); // PLANS_STATUS_CLASS.done === "green"
  });

  it("an inactive chip is visually dimmed; clicking it makes it .active", () => {
    const w = loadAt("http://localhost/");
    w.navigate({ tier: "plans" });
    const doneChip = () => [...w.document.querySelectorAll('[data-kind="status"]')].find(b => b.dataset.value === "done");
    expect(doneChip().classList.contains("active")).toBe(false);
    doneChip().click();
    expect(doneChip().classList.contains("active")).toBe(true);
  });
});
