# SPA / client-side routing best practices

A real reference guide for reviewing this dashboard's own client-side
routing and navigation UX - written 2026-09-19 at Keith's own ask, after
he asked for the `delivery-dashboard-ux`/`delivery-dashboard-ux-critic` subagents to
"care about clean, human-readable URLs" and "embody single page
application best practice" more generally (not just URLs). Read by both
of those agents: `delivery-dashboard-ux` checks a new requirement's approach
against this BEFORE anything is built; `delivery-dashboard-ux-critic` checks
the finished, real, running result against it AFTER, in a real browser.

Research sources are all real (see bottom). First pass (2026-09-19,
afternoon) leaned on WebSearch-crawled snippets, since this project's own
network egress proxy blocked 5 higher-quality primary sources at the
time. Keith allow-listed them the same evening; this doc was then
re-verified and extended against the real primary-source text of 4 of
those 5 (`smart-interface-design-patterns.com`, `rakhman.info`, MDN,
Wikipedia - `web.dev/articles/urls` turned out to be a genuine 404, not
a proxy issue, once actually reachable). One real, separate finding from
doing this: even after the network-level block was genuinely lifted
(confirmed via a raw `curl`, real 200s), the `WebFetch` tool itself kept
reporting the same `EGRESS_BLOCKED` error for all 5 - a stale, tool-level
check out of sync with the live proxy policy, not a real ongoing block.
Worked around by fetching the raw HTML via `curl` and reading it
directly instead. Worth remembering for any future session: don't treat
a repeated `WebFetch` failure alone as proof a domain is still blocked
after an allow-list change - verify with a raw `curl` first.

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

For readability specifically (now confirmed against the real primary
source, `smart-interface-design-patterns.com`'s "UX Guidelines For
Better URL Design"): lowercase only, hyphens not underscores, real words
(a "slug" - Wikipedia's term for the human-readable trailing path
segment) over raw IDs/opaque strings where a real word is available, no
dynamic noise (session IDs, cache-busting params) in a URL meant to be
shared or bookmarked. Keep each segment reasonably short - that source's
own rule of thumb is ~60-75 characters for a whole URL, which doesn't
map exactly onto this dashboard's real multi-segment drill-down path
(agency+collection+dataset+column+check IDs strung together will
usually run longer than that) but the underlying principle still holds:
prefer the id/slug a data steward would already recognize over a longer
technically-more-precise one, and don't add segments that don't earn
their place. Avoid special/reserved characters (`#`, `?`, `&`, `=`, `+`,
`%`) and accented characters inside a segment - `pathSegment()`'s own
`encodeURIComponent()` call already handles this correctly (a raw
special/accented character gets percent-encoded rather than left to
break the URL, at the cost of that one segment being less readable if
the underlying id genuinely contains one). This is exactly the problem
the pre-2026-09-18 version of this dashboard had - an opaque `#` +
`encodeURIComponent(JSON.stringify(state))` blob - and exactly what the
current hash-path scheme already fixed.

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
- **Give the very first history entry real state too.** MDN's own
  History API guide (real primary source, read 2026-09-19 once
  allow-listed) flags a specific, easy-to-miss gap: the entry the
  browser creates on initial page load has NO state attached (it wasn't
  created by your own `pushState`/`replaceState`), so if the user
  navigates away and then back to that very first entry, a naive
  `popstate` handler has nothing to restore. MDN's documented fix is to
  call `replaceState` once on load to attach real state to that initial
  entry - and this dashboard's own template already does exactly that
  (`history.replaceState(STATE, "", stateToHash(STATE))` at the bottom
  of the script, run once on initial load) - real, independent
  confirmation this dashboard already follows the documented pattern
  correctly here, not a gap to flag.

## C. Deep-linking and shareability

The real test: paste a URL with a full agency/collection/dataset/column/
check path into a **fresh tab** (not just click through the app) - does
it reconstruct the exact same view, drawer and panel state included, not
just "the app loads"? This dashboard's `renderFromState()` is the real
mechanism meant to guarantee this (it reopens the column drawer/check
panel on initial load too, not just on in-app navigation) -
`delivery-dashboard-ux-critic` should actually do this cold-load test, not
assume it works because in-app clicking does.

## D. Real `<a href>` links, not just click handlers

A genuinely new point, added 2026-09-19 evening once the real primary
source became reachable (`rakhman.info`, "Respecting Browser Navigation
in Single Page Applications"). A plain `onclick`/`addEventListener
("click", ...)` handler on a non-anchor element (a `<div>`, `<button>`,
table row, card) can trigger `navigate()` just fine for a normal left
click, but it breaks every OTHER thing a browser lets you do with a
link: middle-click or Ctrl/Cmd-click to open in a new tab, right-click
→ "Copy link address", right-click → "Open in new tab". A real user who
tries any of those on what looks like a clickable row gets nothing, or
something confusing - not a "minor" gap, since it's exactly the kind of
interaction a busy data steward reaches for without thinking about it.
The fix (per the source's own worked example, and directly applicable
here): render the real navigational target as a real `<a href="#/...">`
element - even if a `click` handler still intercepts the plain left
click to avoid a full page reload - so the browser's own native
link affordances keep working; reserve a bare `onclick`-only handler for
navigation that's genuinely a side effect of a different action (the
source's own example: creating a record and redirecting to its new
detail view), not for what's actually a real link a user would expect to
behave like one.

**Real, current gap found while re-verifying this doc (2026-09-19
evening):** a grep of the template found only 5 real `<a href>`
elements in the whole file, all of them EXTERNAL links (GitHub source/
ticket links, the snapshot archive) - every INTERNAL drill-down
navigation (breadcrumb crumbs, dataset/check table rows, cards, the
Plans/Demo/home-wordmark header buttons) is wired through a plain
`addEventListener("click", ...)` on a non-anchor element instead (39
such call sites), calling `navigate()` directly. None of these support
middle-click/Ctrl-click/copy-link-address today. Not fixed as part of
this doc - logged as `plans/dashboard.md` #15 alongside the route-change
accessibility gap (same "real gap found while grounding this doc in the
actual template" origin), for real scoping later.

## E. Scroll position

`navigate()` resets scroll to top on a forward drill-down - the right
call, since a drill-down is conceptually a new "page". There's currently
no explicit scroll-restoration handling on `popstate` (Back/Forward) -
this relies on the browser's own default `scrollRestoration` behavior,
which can behave oddly if content renders asynchronously after the
`popstate` event (it doesn't here - `render()` is synchronous - so this
is a lower-priority thing to watch for, not a known-broken behavior).

## F. Accessibility on route change

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
`plans/dashboard.md` #15 for real scoping later, and `delivery-dashboard-ux-
critic` should actively check for this class of gap on every future
post-build pass, not just on a dedicated a11y-focused requirement.

## G. Common pitfalls checklist

A literal checklist `delivery-dashboard-ux-critic` should run through on any
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
- [ ] Does a genuinely navigational element (a row/card/crumb that takes
      you to a different view) render as a real `<a href="#/...">`, so
      middle-click/Ctrl-click/copy-link-address work - not just a bare
      `onclick` handler on a non-anchor element?

`delivery-dashboard-ux` should walk through the same checklist BEFORE anything
is built, as a design check against the proposed approach (not a live
test) - e.g. "will this new panel's state live in the query string or
get baked into the path", "does this new view need its own document
title", not just "does this look consistent with the rest of the page."

## Sources

**Read directly, real primary-source text** (2026-09-19 evening, once
Keith allow-listed the domains a WebSearch-only first pass had to work
around):
- MDN, "Working with the History API" (`developer.mozilla.org`) - the
  `pushState`/`replaceState`/`popstate` mechanics in section B, including
  the initial-entry-needs-`replaceState`-too point
- Smart Interface Design Patterns, "UX Guidelines For Better URL Design"
  (`smart-interface-design-patterns.com`) - the length/character/
  casing/slug guidance in section A
- Kirill Rakhman, "Respecting Browser Navigation in Single Page
  Applications" (`rakhman.info`) - the real-links-vs-click-handlers
  finding in section D
- Wikipedia, "Clean URL" (`en.wikipedia.org`) - the slug/query-string
  terminology in section A
- `web.dev/articles/urls` - checked directly once allow-listed, turned
  out to be a genuine 404 (not a proxy issue) - not used as a source

**WebSearch-crawled synthesis only** (afternoon first pass, not a direct
read of the primary source):
- Google Search Central, URL structure guidance
- Vercel Academy (`params` vs `searchParams`), LogRocket (`useSearchParams`,
  URL-as-state), TanStack Router discussion #1249 (URL-as-state patterns)
- Deque, WebAbility, SitePoint, TestParty, Orange digital accessibility
  guidelines - SPA accessibility / route-change focus management
- Telerik ("Please Respect The 'Back' Button"), Adam Silver ("The problem
  with single page applications") - SPA navigation pitfalls
