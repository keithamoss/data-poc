# Draft: road-testing sprint 1, "where do I put my effort?" (plans/road-testing.md #1, #2)

Scoped by delivery-scoper on 2026-10-14 (Perth), and **revised the same day
(~17:00) to fold in Keith's answers to Q1-Q8** (at the end of this file).
**This is still a proposal for Keith's sign-off.** Nothing here is in
`requirements.yaml` or `plans/`. Criteria marked PROVISIONAL now depend only
on the three NEW questions below (NQ1-NQ3).

Requirements: `docs/drafts/road-testing-sprint-1/requirements-draft.yaml`

| Id | What | MoSCoW | Depends on |
|---|---|---|---|
| **REQ-DASH-224** | One function decides red / amber / green / not counted, per check, per column (worst check) and per check section, returning red and amber separately. Builds on the Trend defect fix (post-build-review #181). | must | - |
| **REQ-DASH-225** | Dataset list: "N of M columns not green", "2 red, 1 amber", sections counted as columns and named, with two small trend lines (red solid, amber dashed) on a fixed 0-100% scale. | must | 224 |
| **REQ-DASH-226** | Agency cards (and collection headings, provisionally): "N of M datasets not green", red and amber in words, plus a small labelled trend of datasets not green. | must | 224, 225 |
| **REQ-DASH-227** | Dataset page: a new two-line red/amber trend with axis titles, key and "View as table"; the same style in the column panel and on the column tiles. | should | 224, 225 |
| **REQ-DASH-228** | A check's own chart names its measure, from its rule kind through one mapping. | should | - |

## What changed, per requirement, after Keith's answers

- **REQ-DASH-224.** No longer the defect fix - Keith chose to fix that now,
  test-first, as **post-build-review #181**, and this builds on it. Still "one
  function decides not green", now also deciding a column's status (worst
  counted check, Q2), treating each check section as a column (Q3), and
  returning red and amber counts separately (Q2's two lines). Its test is
  new: the red/amber split and the section-as-column cases.
- **REQ-DASH-225.** Two lines, red solid and amber dashed, one key in the
  column header, no endpoint dot, neutral ink in a quiet state (Q2). Sections
  count as columns; a header note says so, and a red/amber section is named in
  the row's "2 red (one is Supply-level checks), 1 amber" line (Q3). The
  separate section line is gone. Q1 and Q6 confirmed and recorded.
- **REQ-DASH-226.** Counts **datasets** by their own pill, not checks (Q4).
  M stays "the datasets the card's rollup counts" - Keith's choice changed the
  unit, not the set, so that recommendation stands and is recorded. The
  cross-table de-duplication criterion and test are gone (a dataset counts
  once whatever it shares). The card **keeps** a small labelled trend of
  datasets not green (Q5), drafted as two lines (NQ3).
- **REQ-DASH-227.** The dataset-page trend is two lines with a key and a
  two-series "View as table" (run date, red, amber, N of M) (Q7). I also made
  the column panel and the tile lines two-line, for one vocabulary per page -
  my call, not asked; say if you would rather the tiles stay single.
- **REQ-DASH-228.** Q8 confirmed; PROVISIONAL marks removed.

## How the two lines work at sparkline size (REQ-DASH-225, reused by 226 and 227)

- Today's box is about 180 x 28 px. Red is a solid line, amber a dashed one,
  on a fixed 0-100% scale. Because each column counts once at its worst
  check, red + amber never exceeds 100%.
- Colour is never alone: line style distinguishes the two; the header carries
  one key in words; each row's accessible name gives the latest red and amber
  of M; the dataset page's "View as table" gives both full series.
- The cost of a fixed scale at this height is that one column in fifteen sits
  about 2 px off the baseline. That is accepted (Q6) - the count beside it
  carries the exact figure.
- The endpoint dot goes: with two coloured lines it would be a third mark
  repeating the count. In a quiet state (post-build-review #57) both lines draw
  in neutral ink, told apart by dash alone.

## How "columns" includes the check sections (Q3)

- Each section with at least one counted check is one unit, named by the
  heading the dataset page already shows: **Supply-level checks**,
  **Table-level checks**, **Cross-table checks**, and (NQ1) **File checks**.
- The list's header carries one line: "Supply, table, cross-table and file
  checks each count as one". Any section that is red or amber is named in the
  row.
- **A cross-table section counts once per dataset it is filed under.** It
  already sits in each participating dataset's columns and already turns each
  one red (Keith, 2026-09-26, "counts against both"), so the count follows
  the pill. Since the agency card now counts datasets, no figure spans
  datasets at check level, so no de-duplication is needed anywhere.

## NEW questions for Keith (one set, recommended option first)

**NQ1. File checks: one of the "columns", or left out?** Your Q3 answer named
file checks. But **REQ-DASH-097 criterion 2** (signed and built) says "THE
SYSTEM SHALL NOT fold a file check's verdict into any data check's status,
count or trend", and its criterion 7 says a file-check warning does not
change the dataset's status. A refused file already turns the row into a
single reason row with no count (REQ-DASH-148), so in practice a file unit
would only add amber warnings, and these would show beside a green pill
("1 of 15 not green, 1 amber" on a green dataset). File checks are also
recorded per load attempt, not per QA run.
- **A (recommended): leave file checks out.** Supply, table and cross-table
  sections count; the file section stays on its own, as REQ-DASH-097 decided.
  The count and the pill always agree.
- B: count them as "File checks", as drafted now. This is what you said, but it
  amends REQ-DASH-097 criterion 2 (a signed requirement) and accepts an amber
  count beside a green pill for a file warning.

**NQ2. What does the agency card's trend plot at each point?** A dataset's full
status on a past date (outstanding supply, period closed with no supply)
depends on cadence logic, and doing that for 30 datasets at every point is
the heaviest thing on the page.
- **A (recommended, drafted): check verdicts only.** One point per date on
  which any counted dataset had a QA run, each dataset judged by its latest QA
  run's verdict through REQ-DASH-224. This is cheap, but the line can end
  below the card's count when a dataset is red only for a missing supply. The
  label would say "by check results".
- B: full status as of each date. The line always ends at the card's count,
  but render time must be measured, and points need a date grid (per period or
  per week) since datasets run on different cadences.

**NQ3. Is the agency card's trend two lines, red and amber, like the list?**
- **A (recommended, drafted): two lines.** One vocabulary across tiers.
- B: one "datasets not green" line. Quieter on a card that already has a pill,
  a count and markers.

## Still open from the first pass (not among Q1-Q8)

- Collection headings on the agency tier get the same datasets count as the
  agency card (REQ-DASH-226 criterion 5, PROVISIONAL).
- Sorting the dataset list by red count is not in this sprint (REQ-DASH-225
  open question).
- Wording for your approval at sign-off: the "Columns not green" header, its
  section note, and the grid label on the dataset page.

## Non-functional angles: what I settled and what I ruled out

- **Settled myself:**
  - **Scale.** One count per row, one shared scale, and cards carry counts
    rather than names.
  - **Accessibility.** Red and amber in words and by line style, every trend
    with a text equivalent, axis titles as text (REQ-DASH-070 criterion 6).
  - **Performance.** No new embedded data, one pass over the checks. The
    agency card's trend is now the largest series on the page, so measure it
    once (and NQ2 B would raise this).
  - **The build rule.** Everything is computed in the page from embedded
    recorded results, with no supply rows.
  - **As-of correctness.** Every figure is judged on the date on show, with
    tests at a past date as well as the build's own date.
  - **Compatibility.** No new assets, so file:// and offline viewing are
    unaffected. A phone is not a target.
  - **Maintainability.** One counting function, no Python twin. The rule-kind
    mapping is guarded by a test.
  - **Test-first claims that can fail.** Every browser test asserts its
    subject exists first.
  - **Observability.** These changes are CHANGELOG.yaml-worthy.
- **Ruled out as not applying:**
  - Security, privacy, compliance and retention, and cost - as in the first
    pass: counts only, nothing new stored or computed server-side.
  - Reliability: these are pure page computations, with no network.

## Carry-over check (the source threads against the draft)

- #1, the Trend column plots a rate: REQ-DASH-224, decision "rate in the line stands".
- #1, the endpoint dot is the run's worst status: REQ-DASH-225, decision "no endpoint dot" (replaced, not lost).
- #1, the aria-label is the only text: REQ-DASH-225, the accessible-name criterion.
- #1, the per-check chart's missing y-axis title and its "Value" header: REQ-DASH-228.
- #1, "a falling line means different things": REQ-DASH-227 NFR CONSISTENCY and REQ-DASH-228.
- #1, the 0.05 floor: REQ-DASH-225, decision "one fixed 0-100% scale".
- #1, named in place or a different treatment: REQ-DASH-225, decision "named in place".
- #1, "Rows, latest run" read as the same series: not needed as its own criterion, as before.
- #2, worst-of is deliberate: REQ-DASH-226, decision "the pill stays worst-of".
- #2, checks or columns: REQ-DASH-225 decisions (Q1) and REQ-DASH-226 (Q4, datasets).
- #2, what Tier 1 shows: REQ-DASH-226.
- #2, where the count sits: REQ-DASH-225, decision "in its own column".
- #2, "how many amber, how many red": REQ-DASH-225, decision "red and amber as two lines", and the words criterion.
- The sprint line's "every red looking the same stops triage at 30": scale NFRs on 225 and 226.
- The Trend defect: post-build-review #181 (Keith's call), cited by REQ-DASH-224.

## Draft entry for plans/road-testing.md (for a human to apply, replacing the Sprint 1 bullet)

```
- **Sprint 1 - "where do I put my effort?" (#1, #2; M).** SCOPED 2026-10-14 by
  delivery-scoper as REQ-DASH-224 to 228, Keith's Q1-Q8 answers folded in the
  same day, awaiting his sign-off (docs/drafts/road-testing-sprint-1/). The
  Trend defect found while scoping (inactive and no-data checks counted as
  failing) is fixed separately first, post-build-review #181. 224 is the one
  red/amber counting function; 225 the dataset list's columns count with red
  and amber trend lines; 226 the agency cards' datasets count and trend; 227
  the dataset page's and column panel's labelled trends; 228 a check chart's
  axis named. Three questions are open (NQ1-NQ3 in the draft's summary).
```

Entries #1 and #2 stay until their requirements are built.

## Validation (re-run after the revision)

- `uv run mothman dashboard validate-requirements --draft docs/drafts/road-testing-sprint-1/requirements-draft.yaml`
  reports only the expected cross-reference errors (REQ-DASH-070, 180 and 182,
  and REQ-PIPE-115, which the draft does not contain).
- The draft appended to a copy of `requirements.yaml` (scratchpad
  `requirements-merged.yaml`): `requirements validation OK - 213 requirements,
  zero errors`.

## Keith's answers (2026-10-14, ~17:00)

- Q1: **A** - the dataset-list row counts COLUMNS, and the small trend beside
  it measures the same thing.
- Q2: **A, with a change** - a column counts once at its worst check; and
  "maybe have separate lines for red vs orange" - clarified: TWO TREND LINES,
  red columns and amber columns drawn as separate series.
- Q3: **B (not the recommendation)** - checks that belong to no column
  (supply-level, table-level, file, cross-table) COUNT AS EXTRA "COLUMNS".
- Q4: **C (not the recommendation)** - agency cards count DATASETS not green
  ("N of M datasets not green"), not checks.
- Q5: **B (not the recommendation)** - the agency card KEEPS a small labelled
  trend (of datasets not green over time).
- Q6: **A** - small trends share one fixed 0-100% scale.
- Q7: **A** - a new dataset-level trend on the dataset page (red and amber as
  two lines, matching the list) plus a label over the column grid.
- Q8: **A** - a check chart's measure name comes from its rule kind through one
  mapping, with a test naming any kind missing from it.
- The Trend defect (inactive/nodata counted as failing): **fix now,
  test-first**, as a post-build-review defect; REQ-DASH-224 then builds on it.

## Keith's answers to NQ1-NQ3 and the tiles call (2026-10-14, ~17:15)

- NQ1 (file checks as a column): **NEITHER - split out and scoped separately.**
  Keith: "Let's separate this and scope it separately - I do think they need
  to display through all levels of the dashboard, but just not sure how yet."
  So sprint 1 leaves file checks OUT of every count and trend (REQ-DASH-097
  stands untouched for now), and how file-check verdicts surface at every
  level of the dashboard is its own item: plans/running-thoughts.md #96.
- NQ2 (agency card trend points): **B** - each dataset's full status as of
  each date (always ends at the card's count; needs per-dataset cadence logic
  and a date grid).
- NQ3: **A** - the agency card trend is two lines, red and amber.
- Column tiles and column panel: **two lines everywhere** (the scoper's call,
  confirmed).
