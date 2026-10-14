# Draft: a "you told us / we built" Feedback tab (plans/running-thoughts.md #92)

Scoped by delivery-scoper on 2026-10-14, and revised the same afternoon
with Keith's answers to all eight questions and to RQ1-RQ3 (recorded
verbatim at the end of this file), then with the delivery-architect and
delivery-dashboard-ux reviews and Keith's answers to them, all option A
(see **Reviews folded** near the end). **Still a proposal for Keith's
sign-off.** Nothing here is in `requirements.yaml` or `plans/`. No
PROVISIONAL mark is left in the YAML.

Requirements: `docs/drafts/road-testing-feedback/requirements-draft.yaml`

- **REQ-DOCS-219** - the card format in `plans/road-testing.md`, its
  validator (`mothman dashboard validate-feedback`), the keep-the-card rule,
  and restoring the deleted entries as cards.
- **REQ-DASH-220** - the Feedback tab at `#/feedback`. Depends on
  REQ-DOCS-219 and REQ-DASH-222.
- **REQ-DASH-222** (new) - each requirement gets its own dashboard
  address, opening the Requirements panel at it. Independent of the other
  two, and outlives the tab. (219-221 are taken; 221 is in another draft.)

## The story

Someone Keith showed the PoC to gave the feedback recorded in
`plans/road-testing.md`. Keith wants to go back to them and talk them
through what happened to each point, on the real dashboard rather than
from notes.

**Every** entry in `road-testing.md` carries a short card, whoever spotted
it:

```
- **You told us:** the trend lines don't say what they measure.
- **What we heard:** a chart nobody can read is decoration; each one should say what it plots.
- **What we built:** labelled trends on the dataset and column pages, and "N of M checks not green" on the cards.
- **Evidence:** REQ-DASH-NNN; [Birth Registrations](#/agency/registry-services/collection/civil-registration/dataset/birth-registrations)
```

An entry with nothing built yet simply has no `What we built` line (and
usually no Evidence): the tab shows "Not built yet" and the status is
**Heard**, or **Planned** once the card names a not-started requirement.
No "Not yet" placeholder text - one way to say it, nothing to misspell.

`mothman check` fails if any numbered entry lacks a card. The Feedback tab
shows one card per entry, ordered by when it was raised. Status is derived
from the requirements a card names (Heard / Planned / In progress / Built),
with a typed override only for Fixed, Parked or Won't do. A requirement in
a card is a real link to its own address (REQ-DASH-222), which opens the
Requirements panel at it.

When an entry lands, its title and card stay; the analysis prose goes as
usual. That needs a one-line exception in CLAUDE.md and road-testing.md's
introduction - **the wording comes to Keith for approval before it is
applied** (REQ-DOCS-219 criterion 16). Proposed CLAUDE.md text, updated
for "every entry": *"One exception: every `plans/road-testing.md` entry
carries a feedback card, and when the entry lands its title line and card
stay while the rest of its prose goes as usual. The card is a summary
pointing at the requirement, and its status is derived from it, so it
cannot disagree with the register. The exception ends when the Feedback
tab is retired."*

## What Keith's answers changed

| Q | Keith | Effect on the draft |
|---|---|---|
| 1 Which entries | **Every entry** (differs from my recommendation) | Gate now requires a card on every numbered entry; no opt-in, no "whose was it" judgement. New NFR on the filing cost. Raised RQ1 (the first line's label). |
| 2 Deleted entries | Restore as cards (as recommended) | Criterion 17 no longer provisional on *whether*, only on *which* (RQ2, because Q1 widened the field). |
| 3 On landing | Title + card stay (as recommended) | Provisional marker removed; decision cites Keith. |
| 4 "What we heard" | Own line (as recommended) | Decision cites Keith. |
| 5 Status | Derived (as recommended) | Provisional marker removed; decision cites Keith. |
| 6 Requirement ids | **Deep link** (differs) | New REQ-DASH-222. REQ-DASH-220's requirement evidence is now a real `<a href>` to it; 220 depends on 222. Raised RQ3 (address form). |
| 7 Naming | Never (as recommended) | Provisional marker removed; decision cites Keith. |
| 8 Label/route | "Feedback", `#/feedback` (as recommended) | Provisional marker removed; decision cites Keith. |

The two open questions those answers settled ("which entries are the
reviewer's", and every PROVISIONAL tied to Q3/Q5/Q7/Q8) are gone from the
YAML and live on as decisions citing "Keith, 2026-10-14, Q<n>".

## Questions RQ1-RQ3 (ANSWERED 2026-10-14, all option A - kept as the record of what was asked)

1. **RQ1 - What does a card say first, for an entry the project found
   itself?** Seven entries were found by sessions, critics or regenerates
   (#7, #13, #15-#19), not by the reviewer, and the tab is public.
   - **A (recommended):** `We noticed:` on those, `You told us:` on the
     reviewer's. The author picks one per card; the gate requires exactly
     one. Honest on a public page, and costs one extra label.
   - **B:** `You told us:` on every card, as you chose knowing the
     headings. Simplest, but tells the reviewer they raised things they
     did not.
2. **RQ2 - Which deleted entries come back as cards?** You said restore
   the deleted ones; with "every entry" the set could be wider.
   - **A (recommended):** all eleven deleted entries (table below),
     matching "every entry". #17 was closed as *not reproduced*, so this
     adds one override status, "Couldn't reproduce".
   - **B:** only the five the reviewer raised (#5, #8, #11, both #14s).
     Fewer cards, no new status, but the tab then holds every *current*
     entry and only some of the past ones.
3. **RQ3 - A requirement's address.**
   - **A (recommended):** `?panel=requirements&req=REQ-DASH-197`. Keeps
     `panel=` the only thing that opens a drawer; `req=` is that drawer's
     view, like `cmp=` for a check.
   - **B:** `?req=REQ-DASH-197` as in your example. Shorter, but a second
     way to open a panel that every panel path must learn.

Not asked now, still recorded on the requirements: whether a second
reviewer's feedback shares this tab (219), and whether the tab appears on
every deployment (220; recommendation: no switch).

## Deleted entries and the commit each card is rebuilt from

"Last held in" is the last commit whose `plans/road-testing.md` contains
the entry - the text to rebuild from (`git show <sha>:plans/road-testing.md`).
"Deleted by" is the commit that removed it. Every row was checked against
the file's real history on 2026-10-14.

| Old # | Raised | Sighting | Spotted by | Last held in | Deleted by | Resolved by | Card status | In RQ2-B? |
|---|---|---|---|---|---|---|---|---|
| 5 | 2026-09-24 | Times shown in UTC, not Perth time | reviewer | 35edcab | cd57aaf | REQ-DASH-071 | Built (derived) | yes |
| 8 | 2026-09-24 | Closing a check panel jumped back two levels | reviewer | e6aa094 | 03cb93e | defect fix 03cb93e (no requirement) | Fixed (override); Evidence a dashboard link to a check panel | yes |
| 11 | 2026-09-24 | Supply-history columns out of line; raw dates | reviewer | e6aa094 | 03cb93e | 5c5a616 (columns), REQ-DASH-071 (dates) | Built (derived from REQ-DASH-071) | yes |
| 14 (first) | 2026-09-28 | "Arrived at" was the earliest row, not the arrival | unclear - recorded during REQ-GEN-044 work (added 8392873) | 8a942e7 | e99ae3c | REQ-PIPE-080 (3adb8d8) | Built (derived) | yes |
| 14 (second) | 2026-09-26 | "Client reference" three times, nothing to tell them apart | unclear - noticed driving REQ-QAC-037's section (added fcf9133) | e6aa094 | 03cb93e | REQ-QAC-037 (built, 2 unmet criteria) | In progress (derived) | yes |
| 7 | 2026-09-24 | A misconfigured Soda check passed silently | session verifying #6 | e99ae3c | 15edf01 | REQ-QAC-001, REQ-QAC-002 | Built (derived) | no |
| 13 | 2026-09-24 | Soda Core cannot run a change-over-time check | session (split out of #5) | 8a942e7 | e99ae3c | finding now in REQ-QAC-108's decisions | derived from REQ-QAC-108 | no |
| 15 | 2026-10-04 | `bootstrap --force` no longer reproduces the same content | session (REQ-PIPE-105 regenerate) | 8a942e7 | e99ae3c | REQ-PIPE-144 (`--force` refuses over history, 138cf67) | Built (derived) | no |
| unnumbered | 2026-09-28 | Seventeen "missing supply" items in a column | session, once promotion worked | 8a942e7 | e99ae3c | REQ-DASH-133 (grouped gaps, 0f96148) | derived from REQ-DASH-133 | no |
| 17 | 2026-10-05 | The same trial gave different verdicts once | session | cd57aaf | 1ac13eb | closed as not reproduced | Couldn't reproduce (new override, RQ2-A only) | no |
| 18 | 2026-10-07 | A past date warned about files from years later | dashboard UX critic (post-build-review #132) | 8393db2 | 6319f7f | REQ-DASH-197 (and 198) | Built (derived) | no |

Notes on that table:

- **The two #14s sat in the file together.** "Client reference" (added
  fcf9133, 2026-09-26, without the status/date tag at first) and "Arrived
  at" (added 8392873, 2026-09-27) were both numbered 14 from 8392873 to
  8a942e7 - e.g. lines 701 and 723 of `git show 8a942e7:plans/road-testing.md`.
  e99ae3c deleted "Arrived at" and gave "Client reference" its tag. Both get
  new numbers, which is why restoring under old numbers is ruled out.
- **#3 is not restored, because it is not deleted.** It was deleted in
  03cb93e (as fixed by REQ-PIPE-167) and reopened by Keith the same
  evening in 35edcab as a different, still-unscoped concept. It gets an
  ordinary card in place. Its last-held text before the false deletion
  is e6aa094, if anything from that version is worth recovering.
- **Two derived statuses deserve a look when the cards are written.**
  #13's card names REQ-QAC-108, but what it records is a finding rather
  than a build, so it may read better as "Built" with a "What we built"
  line saying we compute those checks ourselves. And the second #14
  will read "In progress" because REQ-QAC-037 has unmet criteria
  unrelated to the label point - accepted in REQ-DASH-220's decisions.
- **Attribution is from the entries' own wording and commit messages,
  not from asking anyone.** "Keith's own sighting" on the 2026-09-24
  entries is read as Keith relaying the reviewer; the two #14s say only
  "noticed" and I cannot tell who. Under RQ1-A that decides which label
  their card carries, so Keith may want to glance at those two.

## Preview: current entries

Statuses as of the register on 2026-10-14. "First line" is RQ1-A's label.

**After review-dashboard-ux Q2 (A):** #1, #2, #4, #6, #9 and #10 cite their road-testing sprint (`sprint 1`, `sprint 3`, `sprint 4`) in Evidence and so read **Planned**, not Heard. #19 stays Heard (no sprint). The tab shows no entry numbers; they are here for the author only.

| # | First line | Raised (short) | What we built (draft) | Evidence | Status |
|---|---|---|---|---|---|
| 1 | You told us | "Trend" lines don't say what they measure | (absent) - sprint 1 | (none yet) | Heard |
| 2 | You told us | You can see something is wrong, not how big | (absent) - sprint 1 | (none yet) | Heard |
| 3 | You told us | Some datasets deliver for the *next* period | "Half of it: a dataset can say its supplies are for the following period. Data arriving now that belongs in next period's schema is still to be scoped." | REQ-PIPE-167 only if that line stays; otherwise none | Built if it names 167 (overstates), Heard if not - see REQ-DOCS-219's #3 decision |
| 4 | You told us | Watch how many distinct values, not which | (absent) - sprint 4 | (none yet) | Heard |
| 6 | You told us | Declare known bad dates of birth, tolerate to a % | (absent) - sprint 4 | (none yet) | Heard |
| 9 | You told us | Show this supply's values beside the last one | (absent) - sprint 3 | (none yet) | Heard |
| 10 | You told us | Say which values were invalid and how many | (absent) - sprint 3 | (none yet) | Heard |
| 12 | You told us | Completeness check for a tall dataset | "Parked until the 30-dataset asset is closer." | (none) | Parked |
| 16 | We noticed | A clean resupply piles up behind earlier ones | built, decisions still moving into requirements | REQ-PIPE-118 (and those after it) | derived |
| 19 | We noticed | On a past date, supply history shows today's state | (absent) | (none yet) | Heard |

## Non-functional angles considered

- **Answered in the draft:** privacy on a public repo and site; the build
  reads only configuration and plans; offline use and government networks
  (relative links, no fetch); scale (15-21 cards; for REQ-DASH-222, a
  drawer of 200+ requirements that already renders whole); fail loudly;
  filing cost of "every entry" (new); maintainability and retirement as
  one change (REQ-DASH-222 explicitly outlives the tab); observability
  (derived status cannot go stale); accessibility (focus to the opened
  requirement, mark not by colour alone); security of the `req=` value
  (compared against embedded ids, escaped); durability of a requirement
  address (ids never reused).
- **Ruled out:** performance beyond the existing panel render; compliance
  and retention (authored prose, not data); cost (none).
- **Nothing left to Keith on NFRs** beyond RQ1, which is partly a privacy
  and honesty question on a public page.

## Found while scoping REQ-DASH-222 - CONFIRMED, now post-build-review #180

**Update after the reviews:** the main session reproduced this in a browser (a cold-loaded
`?panel=requirements` closed with Escape went to about:blank; in a truly fresh tab the panel could not be
closed at all), and it affects all five side panels. Keith chose to fix it now, test-first, for all five,
as post-build-review #180 (review-architect Q1, review-dashboard-ux Q4). REQ-DASH-222 c9 now only drops
`req=` and relies on #180. The original note follows.

Reading `closePanel()` in the template: it calls `history.back()` whenever
`STATE.panel` is set, and `STATE.panel` is set from the address on a cold
load - so closing any side panel opened from a `?panel=` link in a fresh
tab looks like it would step Back out of the dashboard. That is the side-
panel twin of road-testing #8 (fixed for the check panel in 03cb93e).
REQ-DASH-222 criterion 9 fixes it for the Requirements panel because a
shared requirement link makes it the common case. **This is from reading
the code, not from driving the page**; if it holds, it probably deserves
its own road-testing sighting for the other panels.

## Draft plans entry (for a human to apply, not applied)

Appended to `plans/running-thoughts.md` #92, which owns the idea:

> **Scoped 2026-10-14 by delivery-scoper** as REQ-DOCS-219 (a feedback
> card on every road-testing entry, `mothman dashboard validate-feedback`,
> the keep-the-card rule, and restoring deleted entries as cards),
> REQ-DASH-220 (the Feedback tab at `#/feedback`, status derived from the
> requirements each card names) and REQ-DASH-222 (each requirement's own
> dashboard address, which the tab's cards link through). Keith answered
> all eight scoping questions the same afternoon (every entry gets a
> card; requirements deep-linked), then RQ1-RQ3 ("We noticed:" beside
> "You told us:", all eleven deleted entries restored, and
> `?panel=requirements&req=<id>`), and the delivery-architect and
> delivery-dashboard-ux reviews' questions, all option A. Draft in
> `docs/drafts/road-testing-feedback/`, unsigned. The closePanel() defect
> found while scoping is post-build-review #180.

## Keith's answers, set 1 (2026-10-14 afternoon)

1. Which entries get a card: **EVERY entry** in plans/road-testing.md, whoever
   spotted it (not the scoper's recommended #1-#6/#8-#12 subset). So a card
   no longer needs a "came from the reviewer" judgement, and the gate can
   require a card on every entry.
2. Entries already deleted as fixed: **restore as cards** (A), rebuilt from
   git and the fixing requirements, card-only, under new numbers.
3. On landing: **title + card stay, the analysis prose goes** (A). The
   wording change to road-testing.md's intro and CLAUDE.md comes to Keith
   for approval before it is applied.
4. "What we heard": **its own short line** in our words (A).

## Keith's answers, set 2 (2026-10-14 afternoon)

5. Card status: **derived from requirements** (A), typed only for Fixed /
   Parked / Won't do.
6. Requirement ids: **add a deep link** (B) - each requirement gets its own
   URL (e.g. `?req=REQ-DASH-197`) that opens the Requirements panel at it;
   a separate requirement of its own, which REQ-DASH-220's cards then use.
7. Naming the reviewer: **never** (A).
8. Label and route: **"Feedback", `#/feedback`** (A).

## Keith's answers to RQ1-RQ3 (2026-10-14 afternoon)

- RQ1: **A** - "We noticed:" on entries the project found itself, "You told
  us:" on the reviewer's; the gate requires exactly one of the two.
- RQ2: **A** - all eleven deleted entries come back as cards, with a
  "Couldn't reproduce" status added for #17.
- RQ3: **A** - `?panel=requirements&req=<id>`.

## Reviews folded (2026-10-14 afternoon)

Sources:
- `review-dashboard-ux.md` beside this file.
- The batch-B half of `../unsigned-triage/review-architect.md`.
- Keith's answers to RQ1-RQ3 above.

How they were folded:
- Every finding is now in a criterion, an NFR or a decision.
- Each of Keith's answers is a decision citing "Keith, 2026-10-14, <review> Q<n>" (or "RQ<n>"), with the
  rejected option named.
- **No criterion was renumbered**: changes are made in place, and new criteria are appended.
- Each requirement carries a "REVIEWS FOLDED" decision listing what changed.

**REQ-DOCS-219** (18 -> 22 criteria)
- RQ1 folded: c1 is no longer provisional, and the gate requires exactly one of `You told us` /
  `We noticed`.
- RQ2 folded:
  - c11 adds `not-reproduced`.
  - c6 and c12 treat it like parked and won't-do.
  - c17 is no longer provisional.
  - A decision lists all eleven restored entries, with the commit each is rebuilt from and what
    resolved it.
- The validator is **`mothman dashboard validate-feedback`** (review-architect Q2 A).
- c7 accepts `sprint <n>` as an Evidence item. A sprint-only card derives Planned in 220
  (review-dashboard-ux Q2 A).
- New criteria:
  - c19: the date first raised is the `[status, date]` tag's date. It is not changed when the status
    changes, and restored entries carry their original date (architect).
  - c20: a cited sprint must exist in road-testing.md's sprint list.
  - c21: `in-place-on=` is allowed with a well-formed date (review-dashboard-ux Q3 A).
  - c22: the relative-address check sits in the shared parser in `dashboard/plans_md.py`, so the build
    refuses a bad target and not only CI (architect, a security finding).
- NFRs:
  - The parser is built on `_parse_numbered_items`.
  - The validator sits under `mothman dashboard`.
  - The scale is twenty-one cards.

**REQ-DASH-220** (16 -> 22 criteria)
- Changed in place:
  - c1: an h2 heading, and the header entry is a real link with an emoji, like its siblings.
  - c3: the intro wording is no longer provisional (RQ1).
  - c4: the reviewer's `You told us` cards come first by date, then a "We noticed" section
    (review-dashboard-ux Q1 A). The evidence is labelled "Where to see it" (Q5 A), and no entry number
    is shown.
  - c6: a sprint-only card is Planned, and "Couldn't reproduce" is added (RQ2).
  - c8: the summary line counts each group.
  - c9: a requirement's status appears as plain words in the link text, with no pill (dashboard-ux H3).
- New criteria:
  - c17: exactly one status pill per card, and no use of REQ_STATUS_CLASS on cited requirements (H3).
  - c18: "Why not" replaces "What we built" for Parked, Won't do and Couldn't reproduce (M2).
  - c19: a past-date link lands as a Scenarios jump does, with a neutral jump bar, and Back restores the
    Feedback tab's date (H2, Q3 A).
  - c20: a sprint is shown as text, not a link.
  - c21: the build refuses a non-relative href (architect).
  - c22: focus returns to the card's link when the panel closes, and the list keeps its scroll.
- NFRs: renderPlansMarkdown's escaping is reused, sprint_state.survey's "built" predicate is shared, and
  the evidence href is checked at build.
- The date-order decision is marked as amended by Q1.

**REQ-DASH-222** (12 -> 16 criteria)
- RQ3 folded: c1 is no longer provisional, and a decision cites Keith, with the bare `?req=` rejected.
- Changed in place:
  - c9: the close criterion only drops `req=` with `panel=` and relies on **post-build-review #180**
    (Keith, review-architect Q1 and review-dashboard-ux Q4, option A). The old cold-load decision is
    marked superseded, and a new one cites #180.
  - c2: the linked-to mark is .arrival-notice's left accent bar.
  - c3: the heading carries tabindex=-1.
  - c7: the notice is .stale-link-notice with role=status, not forgetStaleSegment().
- New criteria:
  - c13: the header button opens the panel at the top and drops `req=`.
  - c14: navigating away drops `req=` and `panel=requirements` (architect, on navUrl).
  - c15: focus returns to the link that opened the panel.
  - c16: rows carry data-req-id and are found by iteration, never by a selector built from the address
    (architect).
- NFRs:
  - The SECURITY NFR now says no selector is built from the value at all.
  - New: `req` is held in STATE.

**Not adopted as written:**
- The card's source label in road-testing.md stays `Evidence`, and only the tab shows "Where to see it".
  This is a decision marked main session, low stakes. Renaming the source label would change
  REQ-DOCS-219's format for no reader's gain.
- The dashboard-ux "header link with emoji" finding is adopted. The emoji itself is left to the build,
  to match whatever its siblings use.

**Validation, 2026-10-14 after folding:**
- This draft alone validates **OK - 3 requirements, zero errors**.
- Both drafts merged into a copy of the register validate **OK - 208 requirements, zero errors**. The
  merge replaced the seven same-id unsigned entries and appended 219-223.

## Ready for sign-off

**All three requirements are ready to walk.**
- Every question put to Keith is answered.
- Every PROVISIONAL mark is gone.
- Two open questions are kept on record without blocking the build. Both say "not asked now", and
  neither changes what is built:
  - REQ-DOCS-219: whether a second reviewer's cards would share this file and tab.
  - REQ-DASH-220: whether the tab shows on every deployment. The recommendation is no switch for now.

**Points worth a glance during the walk** (recommended reading first):
1. **The two #14s' first line.** Attribution comes from wording and commit messages, not from asking.
   - The draft gives both `You told us`.
   - Say if either was the project's own, in which case it reads `We noticed`.
2. **#13's card** names REQ-QAC-108, which records a finding rather than a build.
   - Recommended: a "What we built" line saying we compute those checks ourselves, which derives
     Built.
3. **The fourth label.** "Where to see it" shows on the tab, and the file keeps `Evidence`. Say if you
   want the file to read "Where to see it" too.

**Recommended build order** (the architect's, adjusted for the answers):
1. **post-build-review #180** first. The main session is doing it now.
2. **REQ-DASH-222.** It is independent and relies on #180's guard.
3. **REQ-DOCS-219**, including restoring the eleven cards and the CLAUDE.md/road-testing.md wording
   Keith approves at build.
4. **REQ-DASH-220.**

For the full order across both batches, see `../unsigned-triage/summary.md`, "Ready for sign-off".
