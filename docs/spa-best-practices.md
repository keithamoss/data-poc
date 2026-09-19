# SPA / client-side routing best practices

A real reference guide for reviewing this dashboard's own client-side
routing and navigation UX - written 2026-09-19 at Keith's own ask, after
he asked for the `requirements-ux`/`requirements-ux-critic` subagents to
"care about clean, human-readable URLs" and "embody single page
application best practice" more generally (not just URLs). Read by both
of those agents: `requirements-ux` checks a new requirement's approach
against this BEFORE anything is built; `requirements-ux-critic` checks
the finished, real, running result against it AFTER, in a real browser.

Research sources are all real (see bottom) - this project's own network
egress proxy blocked several higher-quality primary sources while
researching this (MDN, web.dev, Wikipedia, two specific blog posts -
`CLAUDE.md`'s own blocked-domains list has the full account), so this
leans more on WebSearch-crawled snippets of those and other sources than
this project's docs usually do. Flag it if anything here reads thin and
Keith can allow-list the blocked domains to fill the gap for real.

## What "SPA" actually means for this project specifically

This dashboard is a single, static, self-contained HTML file
(`dashboard/qa-reporting-dashboard.html`, gitignored build output of
`dashboard/qa-reporting-dashboard.template.html`) published as-is to
GitHub Pages - there is no server-side router, no catch-all rewrite rule,
nothing that can turn a request for `/agency/foo` into `index.html`.
That's not a gap to fix - it's why this dashboard's real, already-built
routing (`stateToPath()`/`pathToState()`/`stateToHash()`/`hashToState()`
in the template's own inline JS, `plans/running-thoughts.md` #9,
2026-09-18) uses the URL **hash** (`#/agency/<id>/...`) rather than a
bare `history.pushState` path with no `#`. A hash never gets sent to the
server on reload or a shared link, so there's nothing for GitHub Pages
to 404 on - the whole app loads from `index.html` every time and the JS
resolves the rest client-side. **Don't flag hash-based routing itself as
a problem for this specific app** - a bare-path History API approach
would need a server capable of rewriting every path back to `index.html`,
which a plain static-file host doesn't give you. This is a deliberate,
correct choice for this app's real hosting constraints, not a naive
default.

The real, current URL shape (both agents should treat this as the actual
baseline to check new work against, not a hypothetical):
- Hash = the "page" - identity/hierarchy, always fully explicit:
  `#/agency/<id>/collection/<id>/dataset/<id>[/column/<name>[/check/<key>]]`,
  plus flat top-level tiers `#/plans` and `#/demo`.
- Query string = orthogonal, non-navigational view state: `asof=`
  (as-of date), `panel=` (which header side-panel is open), `cmp=`
  (which run a check is compared against).

## A. URL design: path segments vs. query parameters

Rule of thumb: if a value changes *which resource* is being shown, it's
a path segment; if it changes *how the same resource is being viewed*
(optional, combinable, order-independent), it's a query parameter. This
dashboard already draws that line correctly - `agencyId`/`collectionId`/
`datasetId`/`columnName`/`checkKey` are path segments (each one narrows
which real thing you're looking at); `panel`/`cmp`/`asof` are query
params (you can have any of them, in any combination, without changing
which dataset/column/check is on screen).

For readability specifically: lowercase, real words over raw IDs/opaque
strings where a real word is available, no dynamic noise (session IDs,
cache-busting params) in a URL meant to be shared or bookmarked. This is
exactly the problem the pre-2026-09-18 version of this dashboard had -
an opaque `#` + `encodeURIComponent(JSON.stringify(state))` blob - and
exactly what the current hash-path scheme already fixed.

## B. History API mechanics

- `pushState` for a real navigation the user should be able to hit Back
  on (this dashboard's `navigate()` does this correctly).
- `replaceState` for a same-"page" state tweak that shouldn't spawn a
  new history entry (this dashboard's `cmp=`/`panel=`/`asof=`/theme
  writes already use `replaceState`, not `pushState` - right call; the
  comment at the `cmp=` write site explains a real bug this avoided:
  `pushState` there used to leave N stray history entries behind after N
  comparison-run picks, so a single Back only undid the most recent one).
- The state object must be plain, JSON-serializable (no DOM nodes,
  functions, class instances) - this dashboard's `STATE` already is.
- `popstate` never fires for your own `pushState`/`replaceState` calls -
  only for a real user-driven Back/Forward/swipe. Don't expect it to
  double as a "did my own navigation just happen" signal.

## C. Deep-linking and shareability

The real test: paste a URL with a full agency/collection/dataset/column/
check path into a **fresh tab** (not just click through the app) - does
it reconstruct the exact same view, drawer and panel state included, not
just "the app loads"? This dashboard's `renderFromState()` is the real
mechanism meant to guarantee this (it reopens the column drawer/check
panel on initial load too, not just on in-app navigation) -
`requirements-ux-critic` should actually do this cold-load test, not
assume it works because in-app clicking does.

## D. Scroll position

`navigate()` resets scroll to top on a forward drill-down - the right
call, since a drill-down is conceptually a new "page". There's currently
no explicit scroll-restoration handling on `popstate` (Back/Forward) -
this relies on the browser's own default `scrollRestoration` behavior,
which can behave oddly if content renders asynchronously after the
`popstate` event (it doesn't here - `render()` is synchronous - so this
is a lower-priority thing to watch for, not a known-broken behavior).

## E. Accessibility on route change

The part most likely to have a real, currently-unaddressed gap - a
plain click-through won't surface any of these, only checking for real:

- **Page title.** A traditional multi-page site updates the browser tab
  title on every navigation for free; an SPA has to do it manually
  (`document.title = ...`) or screen-reader users and anyone using the
  browser's own tab/history UI lose their main orientation cue for
  "where am I now."
- **Focus.** A real full-page navigation resets keyboard focus to the
  top of the document automatically; a client-side route change does
  not - focus silently stays on whatever link/button was clicked. After
  a route change, focus should move somewhere sensible (the new view's
  own heading or main region) so the next Tab continues from the right
  place and a screen reader actually announces the change.
- **An ARIA live region** ("Navigated to Birth Registrations" or
  similar) is the complementary/fallback mechanism when there's no
  single natural heading to move focus to.

**Real, current gap found while researching this doc (2026-09-19):** a
grep of the template's own inline JS for `document.title`, `.focus(`,
`aria-live`, and `role="status"`/`role="alert"` returned zero matches -
none of the three mechanisms above exist today, on any of this
dashboard's many real client-side route changes. Not fixed as part of
this doc (out of scope for a guidance-only pass) - logged as
`plans/dashboard.md` #15 for real scoping later, and `requirements-ux-
critic` should actively check for this class of gap on every future
post-build pass, not just on a dedicated a11y-focused requirement.

## F. Common pitfalls checklist

A literal checklist `requirements-ux-critic` should run through on any
dashboard-facing requirement that adds or changes a client-side view:

- [ ] Cold-load a deep link (with drawer/panel state) in a fresh tab -
      does it show the exact right view, not just "the app loads"?
- [ ] Click Back after 2-3 real navigations - does it go where a user
      would actually expect, not skip an entry, re-trigger a duplicate
      state, or dead-end?
- [ ] After a route change, is keyboard focus somewhere sensible (not
      silently stuck on whatever was clicked)?
- [ ] Does the browser tab title reflect the current real view?
- [ ] Is optional/combinable view state (filters, sort, which comparison
      run, which panel) in the query string, not baked into the path?
- [ ] Is the path free of raw encoded JSON / opaque IDs where a real,
      readable word is available?
- [ ] Does a rapid sequence of the same kind of state change (e.g.
      several comparison-run picks in a row) use `replaceState`, not
      leave a trail of `pushState` entries a single Back can't undo?

`requirements-ux` should walk through the same checklist BEFORE anything
is built, as a design check against the proposed approach (not a live
test) - e.g. "will this new panel's state live in the query string or
get baked into the path", "does this new view need its own document
title", not just "does this look consistent with the rest of the page."

## Sources

Primary sources for this research (MDN, web.dev, Wikipedia, two specific
blog posts) were blocked by this project's own network egress policy -
see `CLAUDE.md`'s blocked-domains list. What follows is WebSearch-crawled
synthesis, not a direct read of any one of these:

- Wikipedia, "Clean URL" and "Human-readable medium and data" articles
- Google Search Central, URL structure guidance
- Vercel Academy (`params` vs `searchParams`), LogRocket (`useSearchParams`,
  URL-as-state), TanStack Router discussion #1249 (URL-as-state patterns)
- Deque, WebAbility, SitePoint, TestParty, Orange digital accessibility
  guidelines - SPA accessibility / route-change focus management
- Telerik ("Please Respect The 'Back' Button"), Adam Silver ("The problem
  with single page applications") - SPA navigation pitfalls
