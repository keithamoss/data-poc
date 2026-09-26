// Plans tab (running-thoughts.md #10) - the small, independently
// testable display/filter helpers renderPlans()/renderPlansList() rely
// on. Full real-content rendering (real plans/*.md data, real search/
// filter/expand interaction) is instead verified by the real-browser
// e2e test (tests/test_dashboard_e2e.py) against the real built
// dashboard - same division of coverage RELEASE_NOTES/
// renderChangelogPanel() and REQUIREMENTS/renderRequirementsPanel()
// already have. PLANS itself is a top-level `const` (not a `function`),
// so - same limitation requirements.test.js's own comment already
// explains - it can't be swapped in from outside like buildSupplyHistory()'s
// `d` argument can; PLANS_FILTER, being a `let`, CAN be poked directly
// from a test.
import { afterEach, describe, expect, it } from "vitest";
import { loadDashboard } from "./support/loadDashboard.js";

let dashboard;

afterEach(() => {
  dashboard?.close();
  dashboard = undefined;
});

function load() {
  dashboard = loadDashboard();
  return dashboard.window;
}

describe("plansStatusLabel / plansStatusPill", () => {
  it.each([
    ["done", "Done"],
    ["in-progress", "In progress"],
    ["investigate", "Investigate"],
    ["todo", "To do"],
    ["parked", "Parked"],
    ["superseded", "Superseded"],
    // REQ-DOCS-072 - a sprint that has built everything it owns and
    // whose remaining criteria all belong to another sprint.
    ["blocked", "Blocked"],
  ])("labels %s as %s", (status, label) => {
    const w = load();
    expect(w.plansStatusLabel(status)).toBe(label);
  });

  it("falls back to the raw value for an unrecognized status", () => {
    const w = load();
    expect(w.plansStatusLabel("mystery")).toBe("mystery");
  });

  it("renders a real pill with the right label and status class", () => {
    const w = load();
    expect(w.plansStatusPill("done")).toContain("pill green");
    expect(w.plansStatusPill("parked")).toContain("pill nodata");
  });

  it("gives blocked a quiet pill, not an amber one", () => {
    // Grey on purpose: nothing is happening inside a blocked sprint and
    // the action belongs to its blocker, so amber would compete with
    // the entries that genuinely want attention now.
    const w = load();
    expect(w.plansStatusPill("blocked")).toContain("pill nodata");
    expect(w.plansStatusPill("blocked")).not.toContain("amber");
  });

});

describe("inlinePlansMd", () => {
  it("converts **bold** to <strong>", () => {
    const w = load();
    expect(w.inlinePlansMd("a **bold** word")).toBe("a <strong>bold</strong> word");
  });

  it("converts `code` to <code>, same as mdInlineCode", () => {
    const w = load();
    expect(w.inlinePlansMd("a `code` span")).toBe("a <code>code</code> span");
  });

  it("handles both bold and code in the same string", () => {
    const w = load();
    expect(w.inlinePlansMd("**bold** and `code`")).toBe("<strong>bold</strong> and <code>code</code>");
  });
});

describe("renderPlansMarkdown", () => {
  it("wraps a single paragraph in <p>", () => {
    const w = load();
    expect(w.renderPlansMarkdown("Just one paragraph.")).toBe("<p>Just one paragraph.</p>");
  });

  it("splits blank-line-separated blocks into separate <p> tags", () => {
    const w = load();
    const html = w.renderPlansMarkdown("First paragraph.\n\nSecond paragraph.");
    expect(html).toBe("<p>First paragraph.</p><p>Second paragraph.</p>");
  });

  it("joins soft-wrapped lines within one paragraph with a space", () => {
    const w = load();
    const html = w.renderPlansMarkdown("A line that\nwraps across two source lines.");
    expect(html).toBe("<p>A line that wraps across two source lines.</p>");
  });

  it("renders a block of consecutive bullet lines as one real <ul>", () => {
    const w = load();
    const html = w.renderPlansMarkdown("- first thing\n- second thing");
    expect(html).toBe("<ul><li>first thing</li><li>second thing</li></ul>");
  });

  it("renders a bullet block separately from a following paragraph", () => {
    const w = load();
    const html = w.renderPlansMarkdown("- one\n- two\n\nAfter the list.");
    expect(html).toBe("<ul><li>one</li><li>two</li></ul><p>After the list.</p>");
  });

  it("applies inline bold/code formatting inside list items too", () => {
    const w = load();
    const html = w.renderPlansMarkdown("- a **bold** item\n- a `code` item");
    expect(html).toBe("<ul><li>a <strong>bold</strong> item</li><li>a <code>code</code> item</li></ul>");
  });

  it("renders a block of consecutive numbered lines as a real <ol> - real bug, Keith's own report 2026-09-19", () => {
    const w = load();
    const html = w.renderPlansMarkdown("1. Phase one.\n2. Phase two.");
    expect(html).toBe("<ol><li>Phase one.</li><li>Phase two.</li></ol>");
  });

  it("falls back to <ul> for a block mixing numbered phases with nested bullet sub-items", () => {
    const w = load();
    const html = w.renderPlansMarkdown("1. Phase one.\n- a sub-detail\n2. Phase two.");
    expect(html).toBe("<ul><li>Phase one.</li><li>a sub-detail</li><li>Phase two.</li></ul>");
  });

  it("returns an empty string for empty/falsy input", () => {
    const w = load();
    expect(w.renderPlansMarkdown("")).toBe("");
    expect(w.renderPlansMarkdown(null)).toBe("");
  });
});

describe("plansEntryMatchesFilter", () => {
  // PLANS_FILTER is a top-level `let`, not a `function` - same limitation
  // the file-header comment already flags for `const PLANS`: a classic
  // script's top-level `let`/`const` bindings live in a separate global
  // lexical environment, never on `window`, so `w.PLANS_FILTER = {...}`
  // would silently create an unrelated window property that
  // plansEntryMatchesFilter()'s own closure never reads (confirmed the
  // hard way - that approach was tried first and every assertion below
  // failed the opposite way). Driving state through a REAL chip click/
  // search-input event instead works correctly, since the click/input
  // handlers and plansEntryMatchesFilter() share the exact same closure.
  function entry(overrides) {
    return { status: "done", components: ["Dashboard UI"], file: "wider", title: "A title", body: "Some body text.", ...overrides };
  }
  function renderedView(w) {
    const view = w.document.getElementById("view");
    w.renderPlans(view);
    return view;
  }
  function clickChip(view, kind, value) {
    const btn = [...view.querySelectorAll(`[data-kind="${kind}"]`)].find(b => b.dataset.value === value);
    btn.click();
  }
  function typeSearch(w, text) {
    const input = w.document.getElementById("plans-search");
    input.value = text;
    input.dispatchEvent(new w.Event("input", { bubbles: true }));
  }

  it("matches everything when no filter is set", () => {
    const w = load();
    renderedView(w);
    expect(w.plansEntryMatchesFilter(entry({}))).toBe(true);
  });

  it("offers blocked as a real filter chip", () => {
    // REQ-DOCS-072. Asserted by clicking the chip rather than by
    // reading PLANS_ALL_STATUSES, which is a const and so never
    // reaches `window` - and which would prove the list contains a
    // string, not that the filter works.
    const w = load();
    const view = renderedView(w);
    clickChip(view, "status", "blocked");
    expect(w.plansEntryMatchesFilter(entry({ status: "blocked" }))).toBe(true);
    expect(w.plansEntryMatchesFilter(entry({ status: "done" }))).toBe(false);
  });

  it("excludes an entry whose status isn't in a non-empty status filter, once a status chip is clicked", () => {
    const w = load();
    const view = renderedView(w);
    clickChip(view, "status", "parked");
    expect(w.plansEntryMatchesFilter(entry({ status: "done" }))).toBe(false);
    expect(w.plansEntryMatchesFilter(entry({ status: "parked" }))).toBe(true);
  });

  it("excludes an entry with none of its components in a non-empty component filter, once a component chip is clicked", () => {
    const w = load();
    const view = renderedView(w);
    clickChip(view, "component", "QA checks & contract");
    expect(w.plansEntryMatchesFilter(entry({ components: ["Dashboard UI"] }))).toBe(false);
    expect(w.plansEntryMatchesFilter(entry({ components: ["Dashboard UI", "QA checks & contract"] }))).toBe(true);
  });

  it("excludes an entry whose file isn't in a non-empty file filter, once a file chip is clicked", () => {
    const w = load();
    const view = renderedView(w);
    clickChip(view, "file", "qa-pipeline");
    expect(w.plansEntryMatchesFilter(entry({ file: "wider" }))).toBe(false);
    expect(w.plansEntryMatchesFilter(entry({ file: "qa-pipeline" }))).toBe(true);
  });

  it("matches a search query against title or body, case-insensitively, once typed into the search box", () => {
    const w = load();
    renderedView(w);
    typeSearch(w, "LEADERBOARD");
    expect(w.plansEntryMatchesFilter(entry({ title: "Leaderboard launch" }))).toBe(true);
    expect(w.plansEntryMatchesFilter(entry({ title: "Unrelated", body: "mentions the leaderboard here" }))).toBe(true);
    expect(w.plansEntryMatchesFilter(entry({ title: "Unrelated", body: "no match here" }))).toBe(false);
  });

  it("combines multiple active filter dimensions (clicked chips) with AND logic", () => {
    const w = load();
    const view = renderedView(w);
    clickChip(view, "status", "done");
    clickChip(view, "component", "Dashboard UI");
    expect(w.plansEntryMatchesFilter(entry({ status: "done", components: ["Dashboard UI"] }))).toBe(true);
    expect(w.plansEntryMatchesFilter(entry({ status: "parked", components: ["Dashboard UI"] }))).toBe(false);
    expect(w.plansEntryMatchesFilter(entry({ status: "done", components: ["QA checks & contract"] }))).toBe(false);
  });

  it("clicking an already-active chip again clears that filter back to 'show all' for that dimension", () => {
    const w = load();
    const view = renderedView(w);
    clickChip(view, "status", "parked");
    expect(w.plansEntryMatchesFilter(entry({ status: "done" }))).toBe(false);
    clickChip(view, "status", "parked");
    expect(w.plansEntryMatchesFilter(entry({ status: "done" }))).toBe(true);
  });
});

describe("renderPlans (raw template, empty PLANS placeholder)", () => {
  it("shows a 0-of-0 entries state against the raw template's own null-placeholder PLANS", () => {
    const w = load();
    const view = w.document.getElementById("view");
    w.renderPlans(view);
    expect(w.document.getElementById("plans-count").textContent).toBe("0 of 0 entries");
    expect(w.document.getElementById("plans-list").innerHTML).toContain("No plans entries match");
  });
});
