// Loads the REAL, committed dashboard/qa-reporting-dashboard.template.html
// into jsdom exactly as a browser would - runScripts:"dangerously" executes
// its two inline <script> blocks in document order, against the template's
// own real markup (theme toggle button, panels, etc. all already exist in
// that markup, so no synthetic DOM stubbing is needed beyond matchMedia,
// which jsdom doesn't implement). Every top-level `function foo(){}`
// declaration in the main script becomes a plain property of `window` (the
// same way it becomes a property of `window` in a real, non-module browser
// script), so this needs NO changes to the template itself - the
// hand-authored single-file source (CLAUDE.md's own description of it)
// stays exactly that.
//
// With nothing embedded (the template's own placeholder consts - null
// here, real data only once dashboard/embed_dashboard_data.py has run)
// the page renders its "no data embedded" state, because since
// REQ-DASH-055 the whole agency/collection/dataset tree comes from the
// embedded HIERARCHY and the template carries no tree of its own.
//
// A test that needs a tree passes one to loadDashboard({hierarchy}),
// which embeds it the same way the real build does - by replacing the
// const in the HTML before jsdom ever parses it. That is deliberately
// the real mechanism rather than assigning to window afterwards: these
// are `const` declarations in a non-module script, so they are not
// window properties and could not be set that way even if we wanted to,
// and going through the same substitution the build uses keeps the test
// honest about what it is exercising.
import { readFileSync } from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";
import { JSDOM } from "jsdom";

const __dirname = path.dirname(fileURLToPath(import.meta.url));
export const TEMPLATE_PATH = path.join(__dirname, "..", "..", "dashboard", "qa-reporting-dashboard.template.html");

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
  // jsdom doesn't implement smooth-scrolling (navigate()'s own
  // window.scrollTo({top:0, behavior:"smooth"}) call) - a real "not
  // implemented" jsdom warning, not a page bug, so stubbed the same way
  // as matchMedia rather than let it print noise on every drill-down test.
  // (jsdom's own window.scrollTo already exists as a function - it just
  // throws that warning when called - so this must unconditionally
  // replace it, not `||` against it.)
  window.scrollTo = function scrollTo() {};
}

/**
 * Loads the real template into a fresh jsdom Window and returns it, along
 * with every console.error/uncaught-exception message the page produced
 * while loading - the same "zero console errors" bar this project's real
 * Playwright checks (dashboard/check_dashboard_renders.py, and Phase 6
 * step 6's own planned suite) already hold the BUILT dashboard to, applied
 * here to the raw template's own inline logic instead.
 *
 * Caller must call `close()` when done (afterEach) - jsdom windows aren't
 * garbage-collected on their own the way a real browser tab is.
 */
export function loadDashboard({ html, hierarchy } = {}) {
  let source = html ?? readFileSync(TEMPLATE_PATH, "utf-8");
  if (hierarchy !== undefined) {
    const line = `const HIERARCHY = ${JSON.stringify(hierarchy)};`;
    const before = source;
    source = source.replace(/const HIERARCHY = .*?;\n/, `${line}\n`);
    if (source === before) {
      throw new Error("could not find `const HIERARCHY = ...;` to replace - has the template changed?");
    }
  }

  const errors = [];
  const dom = new JSDOM(source, {
    url: "http://localhost/",
    runScripts: "dangerously",
    pretendToBeVisual: true,
    beforeParse: stubMatchMedia,
  });

  const { window } = dom;
  const realConsoleError = window.console.error.bind(window.console);
  window.console.error = (...args) => {
    errors.push(args.map(String).join(" "));
    realConsoleError(...args);
  };
  window.addEventListener("error", (event) => {
    errors.push(event.error ? String(event.error.stack || event.error) : event.message);
  });

  return {
    window,
    document: window.document,
    errors,
    close: () => dom.window.close(),
  };
}


/**
 * The smallest tree that still exercises real drill-down: two agencies,
 * one collection each, the real ids the rest of this suite navigates by.
 *
 * Deliberately the REAL ids rather than invented ones - these tests
 * assert that a URL like /agency/registry-services/collection/... still
 * resolves, and inventing ids here would let the page and the config
 * disagree without any test noticing.
 */
export const MINIMAL_HIERARCHY = {
  agencies: [
    {
      id: "registry-services",
      name: "Registry Services",
      collections: [
        {
          id: "civil-registration",
          name: "Civil Registration",
          datasets: [{ id: "birth-registrations", name: "Birth Registrations" }],
        },
      ],
    },
    {
      id: "child-protection-family-support",
      name: "Department for Child Protection and Family Support",
      collections: [
        {
          id: "child-protection",
          name: "Child Protection",
          datasets: [{ id: "cp-clients", name: "Client Register" }],
        },
      ],
    },
  ],
};
