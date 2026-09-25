// Drill-down navigation: stateToHash/hashToState (the hash-based STATE
// persistence "Thread C - as of is a global filter... deliberately
// separate from" - navigate()'s own neighbouring comment) plus a real
// end-to-end navigate() call through jsdom, driving the actual DOM the
// same way a click on an agency card does.
import { afterEach, describe, expect, it } from "vitest";
import { MINIMAL_HIERARCHY, loadDashboard } from "./support/loadDashboard.js";

let dashboard;

afterEach(() => {
  dashboard?.close();
  dashboard = undefined;
});

// Every test here drives real drill-down, which needs a tree to drill
// into - and since REQ-DASH-055 the template carries none of its own.
// So a minimal one is embedded the same way the real build embeds the
// real one. The ids are the real ids on purpose: these tests assert
// that a URL like /agency/registry-services/collection/civil-registration
// still resolves, and inventing ids would let the page and the config
// disagree with nothing noticing.
function load() {
  dashboard = loadDashboard({ hierarchy: MINIMAL_HIERARCHY });
  return dashboard.window;
}

describe("stateToHash / hashToState round-trip", () => {
  it("round-trips a real drill-down state through the URL hash", () => {
    const w = load();
    const state = { tier: "dataset", agencyId: "registry-services", collectionId: "civil-registration", datasetId: "birth-registrations" };
    w.location.hash = w.stateToHash(state);
    expect(w.hashToState()).toEqual(state);
  });

  // 2026-09-18 (running-thoughts.md #9): the hash used to be opaque
  // encodeURIComponent(JSON.stringify(state)) - unreadable, but any JS
  // object round-tripped through it losslessly. Now a real, readable
  // path (#/agency/<id>/collection/<id>/dataset/<id>/column/<name>/
  // check/<key>) - this asserts that BOTH the readable shape and the
  // deepest drill-down (column + check together, arbitrary names with
  // spaces/slashes) still round-trip correctly through per-segment
  // encodeURIComponent/decodeURIComponent.
  it("produces a real, readable path for a dataset state", () => {
    const w = load();
    const state = { tier: "dataset", agencyId: "registry-services", collectionId: "civil-registration", datasetId: "birth-registrations" };
    expect(w.stateToHash(state)).toBe("#/agency/registry-services/collection/civil-registration/dataset/birth-registrations");
  });

  it("keys a check URL on its stable key, never on its display heading", () => {
    // REQ-DASH-026. The URL used to carry the check's
    // DISPLAY name, which is why headings read "Invalid values -
    // dbt:accepted_values (dbt-core)": the heading had to stay unique
    // within a column, because it WAS the identity.
    //
    // It is now the check_id's final segment, which REQ-QAC-023's
    // validate_tail_uniqueness() already guarantees unique per column -
    // a gate written for exactly this and left unwired until now. The
    // point of the test is that rewording a heading must not move a URL.
    const w = load();
    const state = {
      tier: "dataset", agencyId: "registry-services", collectionId: "civil-registration",
      datasetId: "birth-registrations", columnName: "sex",
      checkKey: "invalid_percent_soda",
    };
    const hash = w.stateToHash(state);
    expect(hash).toContain("/check/invalid_percent_soda");
    // and nothing tool-shaped leaks into it
    expect(hash).not.toMatch(/dbt|soda-core|datacontract-cli/i);
    w.location.hash = hash;
    expect(w.hashToState().checkKey).toBe("invalid_percent_soda");
  });

  it("round-trips a column+check drill-down, including names with spaces and slashes", () => {
    const w = load();
    const state = {
      tier: "dataset", agencyId: "registry-services", collectionId: "civil-registration", datasetId: "birth-registrations",
      columnName: "child_date_of_birth", checkKey: "not null / accepted range",
    };
    w.location.hash = w.stateToHash(state);
    expect(w.hashToState()).toEqual(state);
  });

  it("hashToState returns null for no hash at all", () => {
    const w = load();
    w.location.hash = "";
    expect(w.hashToState()).toBeNull();
  });

  it("hashToState returns null for a malformed hash rather than throwing", () => {
    const w = load();
    w.location.hash = "#not-real-json";
    expect(w.hashToState()).toBeNull();
  });

  it("falls back to the agency tier for a path that starts right but doesn't complete a dataset", () => {
    const w = load();
    w.location.hash = "#/agency/registry-services/collection/civil-registration";
    expect(w.hashToState()).toEqual({ tier: "agency", agencyId: "registry-services" });
  });
});

describe("side panels - openPanel()/closePanel() real history integration", () => {
  // 2026-09-18 (running-thoughts.md #9): the 4 header side panels
  // (activity/changelog/requirements/snapshots) used to be independent
  // DOM-only open()/close() pairs, entirely outside STATE/URL. Now
  // unified under openPanel()/closePanel() - opening one is a real
  // history.pushState (synchronous, safe to assert directly), closing
  // goes through history.back() (async in a real browser/jsdom - the
  // real back-button behaviour itself is covered by the Playwright e2e
  // suite, tests/test_dashboard_e2e.py, not duplicated here).
  it("opening a panel shows its DOM, sets ?panel= in the URL, and pushes a real history entry", () => {
    const w = load();
    const before = w.history.length;
    w.openPanel("activity");
    expect(w.document.getElementById("activity-panel").classList.contains("open")).toBe(true);
    expect(new w.URLSearchParams(w.location.search).get("panel")).toBe("activity");
    expect(w.history.length).toBe(before + 1);
  });

  it("opening a second panel closes the first rather than stacking both open", () => {
    const w = load();
    w.openPanel("activity");
    w.openPanel("requirements");
    expect(w.document.getElementById("activity-panel").classList.contains("open")).toBe(false);
    expect(w.document.getElementById("requirements-panel").classList.contains("open")).toBe(true);
    expect(new w.URLSearchParams(w.location.search).get("panel")).toBe("requirements");
  });

  it("a plain navigate() call closes any open panel", () => {
    const w = load();
    w.openPanel("snapshots");
    w.navigate({ tier: "agency", agencyId: "registry-services" });
    expect(w.document.getElementById("snapshots-panel").classList.contains("open")).toBe(false);
  });
});

describe("navigate() - real drill-down through the DOM", () => {
  it("starts on the executive tier with every real agency card rendered", () => {
    const w = load();
    const cards = dashboard.document.querySelectorAll("#agency-grid .card");
    expect(cards.length).toBeGreaterThan(0);
    // registry-services comes from the embedded hierarchy now, not from
    // a hardcoded id in buildData() - which is the whole point of
    // REQ-DASH-055.
    const navs = [...cards].map((c) => JSON.parse(c.dataset.nav));
    expect(navs.some((n) => n.agencyId === "registry-services")).toBe(true);
  });

  it("drilling into an agency updates the hash, the rail, and removes the exec grid", () => {
    const w = load();
    w.navigate({ tier: "agency", agencyId: "registry-services" });

    expect(w.hashToState()).toEqual({ tier: "agency", agencyId: "registry-services" });
    expect(dashboard.document.getElementById("agency-grid")).toBeNull();
    expect(dashboard.document.getElementById("rail").textContent).toContain("Registry Services");
  });

  it("drilling all the way to a real dataset resolves the exact same dataset via resolveContext", () => {
    const w = load();
    const state = { tier: "dataset", agencyId: "registry-services", collectionId: "civil-registration", datasetId: "birth-registrations" };
    w.navigate(state);

    const ctx = w.resolveContext(state);
    expect(ctx).not.toBeNull();
    expect(ctx.ds.id).toBe("birth-registrations");
    expect(ctx.ag.id).toBe("registry-services");
    expect(ctx.col.id).toBe("civil-registration");
  });

  it("resolveContext returns null for a state that doesn't resolve to a real agency/collection/dataset", () => {
    const w = load();
    expect(w.resolveContext({ agencyId: "does-not-exist" })).toBeNull();
    expect(w.resolveContext(null)).toBeNull();
  });
});

// A STALE DEEP LINK IS AN ORDINARY EVENT, not a broken page. Someone
// bookmarks a dataset, the dataset is later renamed or removed, and the
// bookmark still gets opened. REQ-DASH-055 made that concrete by
// removing fourteen datasets at once, but the case was always reachable
// - renderAgency() and renderDataset() both dereferenced whatever
// find() returned without checking, so the page threw an uncaught
// TypeError and rendered nothing at all.
describe("a URL pointing at something that no longer exists", () => {
  it("shows a not-found state for a removed dataset instead of throwing", () => {
    const w = load();
    w.navigate({
      tier: "dataset", agencyId: "registry-services",
      collectionId: "civil-registration", datasetId: "death-registrations",
    });
    expect(dashboard.errors).toEqual([]);
    const view = dashboard.document.getElementById("view").textContent;
    expect(view).toMatch(/not found/i);
    expect(view).toMatch(/death-registrations/);
  });

  it("shows a not-found state for a removed agency instead of throwing", () => {
    const w = load();
    w.navigate({ tier: "agency", agencyId: "transportation" });
    expect(dashboard.errors).toEqual([]);
    expect(dashboard.document.getElementById("view").textContent).toMatch(/not found/i);
  });

  it("still offers a way back to the top tier from a not-found state", () => {
    const w = load();
    w.navigate({ tier: "agency", agencyId: "transportation" });
    // A dead end with no exit is the other half of this bug: rendering
    // nothing and rendering something unusable are the same to a reader.
    expect(dashboard.document.getElementById("rail").textContent).toContain("Agencies");
  });
});

// A STALE COLUMN OR CHECK LINK IS THE SAME EVENT AS A STALE DATASET
// ONE, and got none of the same treatment (post-build-review #11).
// renderNotFound() was added for agency/collection/dataset after
// exactly this class of bug; column and check were never extended.
//
// What happened instead: renderFromState() found no matching column,
// fell through to hideDrawer(), and left the reader on the dataset page
// with no message, STATE.columnName still set to the bad value, and the
// broken segment still in the URL - so re-sharing propagates it. At
// thirty datasets with evolving schemas, a stale column bookmark is the
// common case rather than the edge.
describe("a URL pointing at a column or check that no longer exists", () => {
  const DATASET = {
    tier: "dataset", agencyId: "registry-services",
    collectionId: "civil-registration", datasetId: "birth-registrations",
  };

  // OPENED, not navigated to. navigate() never opens a drawer - it
  // renders a tier and pushes a hash - so the stale-link case only
  // arises when a URL is ARRIVED AT: an initial load, or back/forward.
  // Both run renderFromState(), which popstate is the reachable lever
  // for from out here (STATE is a module-scoped `let`, so it is not a
  // window property a test can assign).
  function open(state) {
    const w = load();
    w.location.hash = w.stateToHash(state);
    w.dispatchEvent(new w.PopStateEvent("popstate", { state: null }));
    return w;
  }

  it("says so rather than silently showing the dataset page", () => {
    const w = open({ ...DATASET, columnName: "a_column_that_was_dropped" });
    expect(dashboard.errors).toEqual([]);
    const view = dashboard.document.getElementById("view").textContent;
    expect(view).toMatch(/no longer/i);
    expect(view).toMatch(/a_column_that_was_dropped/);
    // The rest of the page is still the dataset the reader asked for -
    // unlike a missing dataset, everything except the column resolved.
    expect(view).toMatch(/Birth Registrations/);
  });

  it("does not leave the dead segment in the URL to be re-shared", () => {
    const w = open({ ...DATASET, columnName: "a_column_that_was_dropped" });
    expect(w.location.hash).not.toContain("a_column_that_was_dropped");
  });

  it("does not leave STATE pointing at the thing it could not find", () => {
    const w = open({ ...DATASET, columnName: "a_column_that_was_dropped" });
    expect(w.hashToState().columnName).toBeUndefined();
  });

  it("drops a dead check key too, not just a dead column", () => {
    const w = open({ ...DATASET, columnName: "gone", checkKey: "retired_check" });
    expect(dashboard.errors).toEqual([]);
    expect(w.hashToState().checkKey).toBeUndefined();
  });

  // THE MUST-NOT-CHANGE HALF LIVES IN THE PLAYWRIGHT SUITE, not here,
  // and deliberately: this harness carries only a hierarchy, so its
  // datasets have zero columns and EVERY column name is stale in it.
  // That makes it the right place to test what happens to a name that
  // does not resolve, and the wrong place to test that a real one still
  // opens its drawer - which needs real check data.
  // tests/test_dashboard_e2e.py's TestAStaleDeepLinkSaysSo has it.
});

// EVERYTHING THAT NAVIGATES IS A REAL LINK (post-build-review #10,
// Keith's own principle, 2026-09-25: "there should be links everywhere.
// Everything should be an actual link. Nothing should be a magic
// JavaScript link or magic JavaScript button").
//
// There were 2 real anchors in the entire rendered page, so middle-click,
// Ctrl-click, open-in-new-tab, copy-link-address and hover-to-see-target
// did nothing on breadcrumbs, agency cards or dataset rows.
//
// A <button> stays a button where it performs an ACTION rather than a
// navigation - opening a panel, toggling the theme, picking a date.
describe("everything that navigates is an anchor carrying its own route", () => {
  it("breadcrumbs are links to the tier they go to", () => {
    const w = load();
    w.navigate({ tier: "dataset", agencyId: "registry-services",
                 collectionId: "civil-registration", datasetId: "birth-registrations" });
    const crumbs = [...dashboard.document.querySelectorAll("#rail .crumb")];
    expect(crumbs.length).toBeGreaterThan(1);
    for (const c of crumbs) {
      expect(c.tagName).toBe("A");
      expect(c.getAttribute("href")).toMatch(/^#\//);
    }
  });

  it("an agency card is a link to that agency", () => {
    const w = load();
    const card = dashboard.document.querySelector("#agency-grid .card");
    expect(card.tagName).toBe("A");
    expect(card.getAttribute("href")).toBe(
      w.stateToHash({ tier: "agency", agencyId: JSON.parse(card.dataset.nav).agencyId }));
  });

  it("a dataset row carries a real link to its dataset", () => {
    // A <tr> cannot be an <a>, so the link lives on the dataset name -
    // which is the thing a reader would aim at anyway. The row stays
    // clickable as a convenience; the LINK is the navigation.
    const w = load();
    w.navigate({ tier: "agency", agencyId: "registry-services" });
    const link = dashboard.document.querySelector("tbody tr a.dataset-link");
    expect(link).not.toBeNull();
    expect(link.getAttribute("href")).toContain("/dataset/");
  });

  it("a plain click is still intercepted for the SPA route", () => {
    const w = load();
    const card = dashboard.document.querySelector("#agency-grid .card");
    const before = w.history.length;
    card.dispatchEvent(new w.MouseEvent("click", { bubbles: true, cancelable: true }));
    expect(w.hashToState().tier).toBe("agency");
    expect(w.history.length).toBe(before + 1);
  });

  it("a ctrl-click is left to the browser rather than hijacked", () => {
    // "Intercepting unconditionally is how a link becomes a magic
    // JavaScript button wearing an <a>, which is the thing this
    // decision is against."
    const w = load();
    const card = dashboard.document.querySelector("#agency-grid .card");
    const ev = new w.MouseEvent("click", { bubbles: true, cancelable: true, ctrlKey: true });
    card.dispatchEvent(ev);
    expect(ev.defaultPrevented).toBe(false);
  });

  it("a middle click is left to the browser too", () => {
    const w = load();
    const card = dashboard.document.querySelector("#agency-grid .card");
    const ev = new w.MouseEvent("click", { bubbles: true, cancelable: true, button: 1 });
    card.dispatchEvent(ev);
    expect(ev.defaultPrevented).toBe(false);
  });

  it("a meta- or shift-click is left alone as well", () => {
    const w = load();
    const card = dashboard.document.querySelector("#agency-grid .card");
    for (const mods of [{ metaKey: true }, { shiftKey: true }]) {
      const ev = new w.MouseEvent("click", { bubbles: true, cancelable: true, ...mods });
      card.dispatchEvent(ev);
      expect(ev.defaultPrevented).toBe(false);
    }
  });

  it("a control that performs an action is still a button", () => {
    // The other half of the rule. Opening a panel or toggling the theme
    // is not a navigation and must not become a link.
    const w = load();
    const d = dashboard.document;
    for (const id of ["theme-toggle", "wordmark-btn"]) {
      const el = d.getElementById(id);
      if (el) expect(el.tagName).toBe("BUTTON");
    }
  });
});
