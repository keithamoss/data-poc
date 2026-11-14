# Speed + rolling anchor v1 - the pre-build reviews, 2026-11-14

## Dashboard UX (delivery-dashboard-ux)

## delivery-dashboard-ux review: speed-anchor v1 (mainly REQ-DASH-407)

I edited no files. I read the draft, the scoper's report, Keith's settled answers (R1-R5, SA Q1-Q5, Dash C, the v6 answers), `docs/hci-ux-psychology.md`, `docs/spa-best-practices.md` and the template. I have not reopened any settled question.

**Context (per `docs/hci-ux-psychology.md`).** This is mostly an **error/failure-state** moment: a quiet or late current period that is really caused by the demo's age, not by a supplier. **First-time use** comes second, because Keith puts the demo in front of people seeing it cold.

**Principles I checked against:**
- **Attribution theory (locus):** the page has to put the cause on the demo, not on a supplier.
- **Non-punitive framing.**
- **Visibility of system status.**
- **Paradox of the Active User:** a line nobody scrolls to does nothing.
- **Consistency:** reuse what's already there.

The weighting (error states first) is why point 1 gets the hardest look.

### 1. Where the date appears: the footer alone is the least visible place for it (question Q1)
- **Where the reader actually gets confused:** at the top of the page, on the overview and the dataset rows, where a late or quiet current period first shows. The footer (template lines 1120-1124) sits below every collection, and at around 30 collections almost nobody scrolls that far.
- **How often this happens:** the default bootstrap uses the fixed anchor (REQ-GEN-405 c4, without `--roll-anchor`), and the default as-of date is today on the asset's clock (`defaultInPlaceOn()`, line 4075, settled 2026-09-16). So the normal demo today shows about seven weeks of overdue daily slots after 25 Sep, and this one line is the only explanation on the page.
- **Patterns that already exist:**
  - The masthead build stamp, `renderBuildStamp()` (lines 13131-13179). Its own comment says it answers "how current is this, and is it mine", and it adds facts to one line with ` · ` rather than adding lines (REQ-PIPE-092 c7/c17).
  - The as-of panel (`#in-place-on-panel-body`, lines 1185-1207), which is where a reader goes when the date itself is the question.
- **Why this is open to change:** the scoper marked the footer as provisional ("Keith or delivery-dashboard-ux may change it"). Dash C settled where the existing synthetic sentence goes, not where a new fact goes.

### 2. The wording has to give the reason, not just a date
"Synthetic data generated up to <date>" has two gaps. It doesn't say whether that day is included, and it leaves the reader to work out why a later period is empty. I suggest replacing REQ-DASH-407 c1 with:

> "WHERE the asset declares `synthetic: true`, THE SYSTEM SHALL show in the footer, as its own sentence immediately after the synthetic wording (REQ-PIPE-385 c12) and before the codename line, using the footer's existing type and no new class: 'The synthetic supplies on this page were generated up to and including <date>; a period after that date has no supply.' <date> is formatted by `fmtDay()` as a plain date on the asset's clock, never an instant. The text SHALL be identical whether the date is today or months ago."

The last sentence keeps it a statement of fact rather than the staleness warning R3 rejected.

For c3 (no anchor recorded), I suggest a full sentence with no command in it, since page readers are not the people who regenerate the data: "The date this synthetic data was generated up to was not recorded." For consistency, the date should go in as a field on the existing `BUILD_PROVENANCE` embed (line 2626) rather than a new top-level const.

### 3. Keep the as-of picker's range and default as they are, and say so in a criterion
`coveredDateRange()` (lines 3176-3191) caps the picker at today, and the default is today. A builder could "helpfully" cap both at the recorded anchor instead. That would make `renderInPlaceOnRangeNotice()` (line 12997) show its banner on every load of an aged demo, which is exactly the staleness warning R3 rejected. Suggested new REQ-DASH-407 criterion:

> "THE SYSTEM SHALL leave the as-of date's default (today on the asset's clock) and the picker's range (REQ-DASH-054 c8 as amended by REQ-DASH-326) unchanged by the recorded anchor, so that no notice appears on the default view of a synthetic asset because of the anchor."

Also worth `delivery-dashboard-ux-critic` checking: SA Q5 often sets a rolled anchor to yesterday. So a demo built later on the day it was rolled will show today's daily slot with no supply. The new sentence is what explains that, so the critic should look at a same-day rolled build.

### 4. Saved scenario links break after a roll (deep links, `docs/spa-best-practices.md` A and C; question Q2)
- **What the link holds:** `scenarioChipHref()` (line 11999) writes both `?in-place-on=<date>` and `&scenario=<id>`.
- **What a cold load does:** `SCENARIO_ON_LOAD` (lines 13197-13209) uses the date in the URL (`to: CURRENT_IN_PLACE_ON`).
- **Why that breaks:** REQ-GEN-406 moves the daily scenarios' dates with the anchor. A scenario link copied before a roll then opens on the old date and says "Viewing <old date> for TS-62". `markScenarioSubject()` finds nothing to mark and gives up silently (line 12024). That is a silent dead end, which is the worst kind in the error-state context.
- **Why the scenario's date should win:** per guide A, the scenario id says which thing the reader wants, and its date follows from it.
- **Suggested criterion (REQ-DASH-407 or REQ-GEN-406):** "WHEN a page is opened cold with `?scenario=<id>` naming a known scenario whose current date differs from the link's `?in-place-on=`, THE SYSTEM SHALL show the scenario's current date and rewrite the address with `replaceState`; with a test that opens a link carrying a stale date."

### 5. Configuration dates written as offsets (REQ-GEN-406)
c3 already says the build reads resolved dates. Add a criterion the post-build critic can check on the page:

> "THE SYSTEM SHALL show every configuration date on the built page (calendar versions, correction dates in the 'decisions made since then' note, setting eras) as an absolute date formatted by `fmtDay()`, and no text on the page SHALL name an offset or the anchor."

### 6. Things I checked that need no change
- **Route-change accessibility:** this adds no new view or route, so there are no `document.title`, focus or `aria-live` changes to make.
- **Real `<a href>` links:** the change adds no new navigation elements, so none are needed.
- **Snapshots and printouts:** keeping the date in the footer means past snapshots and printed pages carry it automatically. That favours the footer as the base in every option below.
- **The CLI lines** in REQ-DASH-407 c4 (the bootstrap output and `mothman env current`) are for `delivery-cli-ux`, not me.

### For `delivery-dashboard-ux-critic`
Check the default view of a non-rolled demo and of a same-day rolled demo. Confirm the sentence explains the empty periods with no banner. Confirm the picker's maximum is still today. Cold-load an old scenario link after a roll.

### Questions for Keith (one batch)
**Q1. Where does "generated up to" appear?** (REQ-DASH-407)
- (a) The footer only, as drafted. Fits Dash C most strictly, but it's below the fold, which is where the confusion is least likely to be cleared up.
- (b) The footer, plus one quiet line in the as-of panel under the date picker ("Synthetic supplies run up to and including <date>"). It meets the reader exactly when they're asking about dates, and puts no synthetic text in the page's main chrome. **Recommended.**
- (c) The footer, plus "· synthetic data to <date>" added to the masthead build stamp. Seen on first load and follows REQ-PIPE-092's pattern, but it adds synthetic text to the always-visible masthead, which stretches Dash C's "footer only" further.

**Q2. A scenario link saved before a roll** (REQ-DASH-407 or REQ-GEN-406)
- (a) The scenario's current date wins on a cold load, and the address is quietly rewritten. The link always lands where it should. **Recommended.**
- (b) The link's date wins, plus a one-line note "TS-62 is now on <date>" with a link to it. More transparent, but it's one more thing to read.
- (c) No change. Links copied before a roll open on the old date and the scenario mark is missing. Acceptable only if nobody shares scenario links outside a single session.

Everything in points 2, 3 and 5 stands whichever way Q1 and Q2 are answered.

**Files:** `/home/user/data-poc/docs/drafts/speed-anchor-v1.yaml`, `/home/user/data-poc/dashboard/qa-reporting-dashboard.template.html`, `/home/user/data-poc/docs/drafts/decisions-2026-11-01.md`
