# Post-build review

What the post-build critic agents found when turned at work that is
already BUILT AND SHIPPED, and what was decided about each finding.

Deliberately a separate file, at Keith's own ask, 2026-09-24. The
neighbouring files hold work not yet done - designs, sprints,
requirements, sightings. This one holds judgements about code that is
already in the repo and already running, which is a different thing to
read and a different thing to act on.

## The standing rule: Keith signs off every finding before anything changes

His own words, 2026-09-24: "a finding about code that we've already
shipped does deserve my eye before we change anything... I'd like to
sign off on all of their findings."

So the sequence is fixed, and it is not the same as the pre-build one:

1. A critic reports. Its report is model output, not a verdict.
2. This session VERIFIES anything load-bearing against the real code -
   a critic's finding is a claim until it has been checked, and several
   of this project's agent findings have arrived with a wrong citation
   or a wrong premise attached to a correct conclusion.
3. The finding is written up HERE, with its evidence, what it would
   cost to fix, and a recommendation.
4. **Keith decides.** Nothing in shipped code changes before that -
   not a "trivially safe" fix, not a one-liner.
5. A finding he accepts becomes real work: a requirement if it is a
   behaviour change, a bug fix with a failing test first if it is a
   defect (`CLAUDE.md`'s standing rule), or a recorded decision to
   leave it alone.

**Why the gate is stricter here than for a new requirement.** A
pre-build finding costs a conversation to act on. A post-build finding
costs a change to something people are already relying on, and the
repository's own history is the argument: a fix written to prevent a
false green introduced one (`plans/qa-pipeline.md` item 74). Acting
fast on shipped code is how the second bug gets written.

Same conventions as every other numbered-item plans file: a closed
status (`todo` / `investigate` / `in-progress` / `parked` / `done` /
`superseded`), one or more component tags, and a date. A finding that
is verified and rejected stays here as `done` with the reasoning, so
the same finding arriving again from a later pass is recognisable
rather than re-litigated.

## 2026-09-24 - the first pass, over twelve requirements built in sprints 1-6

`plans/running-thoughts.md` #34's own subject: twelve requirements were
built across 2026-09-21..23 and **not one went through any post-build
critic**. The sprints ran build, gate, commit, next, and the post-build
half of the pipeline documented in `docs/agent-orchestration.md` was
simply never invoked while they were moving. Nothing was skipped
deliberately.

The twelve: `REQ-QAC-039`, `REQ-GEN-040`, `REQ-GEN-042`, `REQ-GEN-043`,
`REQ-QAC-047`, `REQ-PIPE-048`, `REQ-PIPE-049`, `REQ-PIPE-050`,
`REQ-PIPE-051`, `REQ-PIPE-052`, `REQ-PIPE-053`, `REQ-DASH-055`.

Four critics, one pass each over the whole set rather than twelve
passes - Keith's own call, 2026-09-23 ("happy to do one pass with that,
that's fine, rather than twelve"): `delivery-critic` on all twelve,
`delivery-cli-ux-critic` on the `mothman schedule` surfaces,
`delivery-dashboard-ux-critic` then `delivery-dashboard-visual-critic`
on the dashboard ones - in that order and never in parallel, per the
orchestration doc's own hard-won constraint.

Run against a real built dashboard: 3.8MB, real embedded data, 6,545
check results across 60 runs, both datasets.

**Findings follow as each critic lands.**

---

## Queued for Keith - the visual critic's four questions

**First thing when you are back, 2026-09-24 evening, your own ask.**
These are the four from `delivery-dashboard-visual-critic`. They are
here rather than in its own section below so you can answer them
without reading 58 findings first - each is self-contained, and the
finding number beside it has the measurements if you want them.

They are the four where a critic could see the defect but not the right
answer, and each would change what gets built. Every one of them is
about something already shipped, so nothing moves until you say.

Six more questions are behind these - four from the CLI critic (#17,
#19, #21, #31) and two from the functional one (#1, #37). Say the word
and they go in the same queue.

### Q1. The executive tier is half empty, and that is a design call

**What is there.** `.grid` uses `auto-fill`, so at 1180px it lays out
four 284.5px tracks and fills two. The two real agency cards span 583px
of a 1180px grid - **exactly half the front page is empty** - and the
phantom tracks are held open rather than collapsed. This is the direct
visual consequence of `REQ-DASH-055` removing three invented agencies
from a grid that had been tuned for five. (#54)

**Three ways, and the critic was explicit that this is a judgment call
rather than a defect:**
- **Collapse the tracks** (`auto-fit`) - the two cards stretch to
  ~583px each and fill the row. No dead space, but two very wide cards
  for a small amount of content, and it looks different again the day a
  third agency appears.
- **Cap the grid to its content** - a narrower container so two cards
  sit in a deliberate-looking block rather than a half-empty four-track
  row. Keeps the card proportions; adds a width rule tuned to today's
  count.
- **Leave it** - only visible at two agencies, and it self-corrects as
  the asset grows toward thirty datasets.

**ANSWERED 2026-09-24 evening - Keith asked whether capping hardcodes
the agency count, "bearing in mind we'll have probably eight or so
agencies in reality." That fact changes the answer, so the lean above
is withdrawn rather than defended.**

**At eight agencies the problem does not exist.** The grid lays out
four 284.5px tracks at 1180px, so eight cards fill two complete rows
with no dead tracks at all. Five, six or seven give one partial row,
which is what every card grid on the internet looks like. The half-empty
row is purely an artefact of being at two.

**And yes, capping means pinning something.** The no-hardcode version
would be `width: fit-content` with `margin-inline: auto` on the
container - but `auto-fill` needs a definite width to compute its track
count, and under intrinsic sizing that resolution is exactly the thing
that goes strange. In practice you end up pinning a width, which is
tuning for a state the asset is about to leave.

**So: leave the grid alone.** Revised lean, on Keith's own fact.

**What IS worth fixing regardless of agency count is the other half of
#54**, and it gets worse at eight rather than better: `.card` is plain
block flow with `.card-meta` unpinned, so a one-line title and a
three-line title put the sparkline and the meta row 50px apart. At two
agencies that is two ragged cards; at eight it is two ragged ROWS, and
at thirty datasets' worth of collections below it, more. The fix is
`.card{display:flex; flex-direction:column}` plus
`.card-meta{margin-top:auto}` - no count anywhere, and it is correct at
any number of agencies.

**SIGNED OFF AND FIXED, 2026-09-24 evening** ("make sure you fix how the
cards align internally"). One line, `margin-top:auto` on `.card-meta`.

**One correction to the critic, found while fixing it.** Its finding
said "`.card` is plain block flow" - it is not, and never was. `.card`
has been `display:flex; flex-direction:column` since it was written.
The cards are equal height because the grid stretches them, and the
slack fell below the meta row because nothing pushed it down. Right
conclusion, wrong premise - the fourth of these, and the reason the
standing rule says a critic's finding is a claim until it has been
checked.

**Failing test first**, per that rule:
`tests/test_dashboard_e2e.py::TestQuietStatesAreVisiblyBuilt::
test_every_agency_card_pins_its_meta_row_to_the_same_place` measures,
in a real browser, how far each card's meta row sits above its own
bottom edge. Before: `[69, 19]`, matching the critic's own numbers.
After: equal on every card. The whole module passes, 60 tests.

### Q2. The exhausted count markers duplicate the pill beside them

**What is there.** `exhaustedMarker()` adds a count pill at each tier.
At today's scale that count is 1, so it restates the pill next to it -
the critic measured **three identical `.pill.exhausted` within 40px
vertically** on the Tier-2 page, the last two literally adjacent. (#57)

**This is the one finding in the whole pass that gets BETTER at scale.**
"17 schedules ended" at an agency is genuinely useful; "1 schedule
ended" beside a pill already saying "Schedule ended" is not.

- **Keep as built** - redundant now, correct, and becomes the useful
  form at thirty datasets with no second change.
- **Suppress the marker when the count is 1** - removes the duplicate
  today, shows the marker only when it is actually aggregating.
- **Merge them** - one pill per tier reading "Schedule ended" at count
  1 and "N schedules ended" above. Fewest pills, but it turns the
  marker into a status pill and blurs two roles.

**My lean: suppress at 1.** A small conditional, no behaviour change at
scale, and it keeps the marker's role clean - it aggregates, and when
there is nothing to aggregate it says nothing.

**SIGNED OFF AND FIXED, 2026-09-24 evening** - and **the approved
proposal had to be narrowed while building it**, which is worth
recording because the naive version was actively wrong.

**Suppressing by COUNT ALONE would have hidden real information.** The
marker exists because `REQ-PIPE-053` says an exhausted schedule must
never be absorbed by the rollup - "one exhausted among five red still
reads Red plus a count marker". A RED agency containing one exhausted
dataset has no other signal on its card: its own pill says Red. Drop
the marker at count 1 and that dataset disappears from the tier
entirely - the exact absorption the requirement forbids, reintroduced
by a fix meant to tidy it up. Same shape as `plans/qa-pipeline.md` item
74, where a fix written to prevent a false green introduced one.

**So the test is REDUNDANCY, not count.** `exhaustedMarker(count,
status)` now returns nothing only when `count === 1` **and** the
group's own pill already says `Schedule ended`. Both call sites pass
their own status. A single exhausted dataset under a red, amber, green
or no-data pill still gets its marker.

**Failing tests first**, in `tests-js/relative-time-and-markers.test.js`
- including one that pins the narrowing itself
(`STILL shows a count of one when the group's own pill says something
else`), so a later tidy-up cannot quietly restore the wrong version.

### Q3. Fixing the "No data" pill means making the quiet state louder

**What is there,** recomputed here from the real tokens rather than
taken from the report: the pill's text measures **2.81:1 in light and
3.55:1 in dark** against 4.5:1 for 12.5px bold, so it fails WCAG AA in
both themes. Its dashed border measures **1.51:1** - not visible at
all, either theme. The exhausted pill beside it measures 13.22:1 and
12.78:1, a **4.7x gap**. (#49)

**Two things make this more than a contrast fix.** The code comment
says the exhausted pill is distinguished by "a solid border and a
square marker" - but the border difference is really *invisible versus
visible*, and both 9px markers are squares (1px versus 2px radius is
imperceptible). So all the work separating the two quiet states is
being done by the text contrast, on the token that fails.

- **Raise both tokens** - clears AA, but narrows the 4.7x gap that is
  currently doing the actual distinguishing.
- **Fix only the border** - makes dashed-versus-solid a real
  distinction instead of a notional one; leaves the text failing.
- **Out of scope for now, logged as a standing accessibility item**
  across every muted token - the footer (#54) and `--ink-faint`
  generally have the same problem, so fixing one pill leaves the
  pattern.

**My lean is a blend of the last two:** fix the border now, because it
is cheap and it makes the design the code already claims real - then
fold the text contrast into one accessibility pass with #8 (keyboard
cannot reach a dataset), #9 (focusable controls inside `aria-hidden`
drawers), #10 and #55 (seven of eleven focusable types have no designed
focus ring). Those four are already one job waiting to happen, and the
muted-token audit belongs with them rather than ahead of them.

**SIGNED OFF AND FIXED, 2026-09-24 evening** ("yeah, fix that"), taken
as approving that blend: the border now, the text contrast into the
accessibility pass.

**What changed:** `.pill.nodata`'s border token moves from
`--line-strong` to `--ink-faint` - the same token as its own label. It
measures 2.81:1 light / 3.55:1 dark instead of 1.51:1, so the dashed
edge is as visible as the words inside it, while staying quieter than
exhausted's 5.35:1.

**Why the same token rather than a hand-picked colour:** when the
accessibility pass raises `--ink-faint` to clear AA, this border is
lifted with it. A bespoke value would have to be found again.

**Failing test first**, in both themes:
`test_the_nodata_pills_border_is_at_least_as_visible_as_its_own_label`
asserts the border's measured contrast against its own fill is at least
the label's. The bar is deliberately that, not WCAG's 3:1 for non-text
contrast - the muted tokens do not meet 3:1 yet, and raising them is
the wider decision this defers. Before: 1.51 against 2.81 and 3.55.
After: equal in both.

**It also largely settles #48.** With a visible border the pill still
reads as a pill when its fill merges into a hovered row. The root - one
token serving both the pill's fill and the row's hover - is untouched
and remains #48's to decide.

### Q4. Two render sites disagree about the clock, and one shows raw ISO strings

**What is there.** `REQ-PIPE-048` made every stored instant carry its
own offset. Two render sites never caught up. The SLA tile builds its
value by character-slicing the wall clock out of the string and
appending `" UTC"` unconditionally - right today only because every
stored value happens to be `+00:00`, which is the thing that
requirement changed. And the supply-history table renders the field
raw: **43 values of the form `2026-09-16T05:17:30.280161+00:00`**,
confirmed in the built data, landing in a user-facing TIMING column.
(#51)

**The tile is the more pointed one.** In one four-across strip the SLA
tile reads `Daily, by 14:00 AWST` and the arrival tile reads
`05:29 UTC`, and a reader adds eight in their head, across two tiles,
to judge the "Early" verdict in the same cell. Against a requirement
whose story is "so that a supply that arrived at 10pm in Perth is not
read as having arrived the following afternoon."

- **Render every user-facing instant in the asset timezone** - matches
  the story exactly, one formatter; changes what several existing views
  display, so it wants its own requirement rather than a tidy-up.
- **Keep UTC but format it** - drop the microseconds, use tabular
  numerals, label the zone consistently. Cheaper, leaves the reader
  doing +8 between two adjacent tiles.
- **Split it** - format the supply-history timestamps now as a plain
  rendering defect, and scope the UTC-versus-AWST question separately.

**DECIDED 2026-09-24 evening, and wider than the question asked.**
Keith's own call, in his words: "let's make a call... that will
standardise the display of all timestamps and dates across the entire
code base."

**The standard he set:**

| Kind | Form | His example |
|---|---|---|
| Date and time | time, then weekday, then day and month | `2:15pm Friday 29 September` |
| Date alone | weekday, then day and month | `Friday, 29 September` |
| Relative | "X <unit> ago", scaling by unit | `X minutes ago`, `X hours ago`, `X days ago`, `X weeks ago`, `X months ago`, `X years ago` |

**And one prohibition, stated flatly: no raw ISO timestamps anywhere a
person can see.** That kills #51's supply-history column and #14's
`.slice(11,16)+" UTC"` tile outright, rather than choosing between the
three options that were on the table.

**This is a DISPLAY standard, not a storage change** - recorded
explicitly because the distinction is load-bearing and nothing in the
dictated version says it. Every stored instant keeps its ISO form with
its offset: `qa_results/` is a permanent history read by machines,
`REQ-PIPE-048` exists precisely to make those offsets explicit, and
changing what is written would break the lot. The standard governs what
reaches a human eye - the dashboard, the CLI, anything printed.

**It needs a requirement before anything is built** (`CLAUDE.md`'s
sign-off gate), and it is genuinely cross-cutting rather than a tidy-up:
it lands on the dashboard's `fmtDate`/`fmtDateShort`/`fmtArrival`/
`updateAsOfButtonLabel`, the supply-history table, the SLA tile, the
`mothman schedule` output (`2027-11-01`, `09:00 +0800`), and every
other print site. Four existing findings collapse into it - #3, #14,
#51 and road-testing item 5 - plus road-testing item 11's "make the
dates readable, not bloody raw timestamps".

**Five things the dictated standard does not settle, and each would
change what gets built - for Keith, before drafting:**
1. **The year.** Neither example carries one, and this dashboard shows
   multi-year history: supply runs from 2026, as-of dates out to 2028,
   a Plans tab full of dated entries. Always show it, or only when it
   is not the current year?
2. **The timezone.** The format carries no zone label - which, given
   the question this answers, most naturally means *everything is the
   asset's clock and therefore needs no label*. That is the whole
   substance of Q4 and it should be said out loud rather than inferred
   from a format string.
3. **Where relative, where absolute.** "Live · updated 39s ago" already
   exists; supply history, last-QA-run and arrival times are absolute
   today. One rule, or absolute with a relative tooltip, or relative
   under some threshold and absolute beyond it?
4. **Punctuation.** The two dictated examples differ - `2:15pm Friday
   29 September` has no comma, `Friday, 29 September` has one. Worth
   pinning, since this will be applied mechanically across a lot of
   sites.
5. **The CLI's machine-ish output.** `mothman schedule show` prints
   dates into a table somebody may well be eyeballing against
   `data-asset.yaml`, where `2027-11-01` matches the file and
   `Monday, 1 November` does not. Does the standard cover config-echoing
   output, or only prose?

**ANSWERED 2026-09-24 evening, three of the five:**

1. **The year is shown.** Keith's own call ("that should actually
   mention the year - good point"). Taken as always, not
   only-when-not-this-year, which is the reading that needs no rule and
   never surprises anybody. Reversible if he meant the narrower one.
2. **The absence of a timezone means everything is in asset time** -
   his own words, and this is the substantive answer to Q4. Every
   user-facing instant is rendered on the asset's clock, and carries no
   zone label because there is only one. `#3`, `#14` and `#51` all
   resolve to this.
3. **Relative versus absolute:** he asked for a pass now rather than an
   item later. It follows.

Still open: **punctuation** (the two dictated examples differ on the
comma) and **whether config-echoing CLI output is covered**.

### The relative-time pass (Keith's ask, 2026-09-24 evening)

"If you want to just do a pass now and find some of the high value
areas to add relatives, that'd be handy."

**What already exists, and it is less than it looks.**
`fmtRelativeTime()` (template:3679) does minutes, hours and days, then
**gives up at 30 days and returns an absolute date** - so Keith's weeks,
months and years are not built. It is called from **exactly one place**,
the Recent activity panel. And the masthead's `Live · updated Ns ago`
clock (:4359) does its own seconds-and-minutes arithmetic inline rather
than calling it - a second implementation of the same idea, which is
the shape this project has been bitten by four times (`plans/qa-
pipeline.md` item 74, and #34 in this very file).

**Where relative genuinely earns its place** - the test being whether
the reader's real question is "how long has it been?" rather than "which
day was it?":

| Site | Today | Worth it? |
|---|---|---|
| **`Last QA run` column**, Tier 2 (:2643) | `Sep 22, 2026` | **Highest value on the page.** The question is "is this stale?", and a date makes you do the arithmetic yourself. "2 days ago" answers it outright. |
| **`Latest arrival`**, Tier 2 and the SLA tile | absolute time | **Both.** The absolute is needed to judge against the SLA deadline; the relative answers "has anything landed lately?". Absolute primary, relative alongside. |
| **Past snapshots panel** (:3617) | `Sep 20, 2026 · 14:32` | **High.** You are choosing among archives, and "3 weeks ago" is how people pick one. |
| **Release notes and Plans dates** | absolute | **Medium.** "How current is this thinking?" is a real question about both. |
| **Recent activity** | already relative | Extend past 30 days to weeks/months/years. |
| **The `Live · updated` clock** | its own inline maths | Point it at the one helper. |
| **Supply history TIMING column** | `1 day since previous` + a raw ISO string | The between-rows relative is already right and should stay. The raw string becomes an absolute formatted one (#51). A third "ago" per row would be noise on a historical table. |
| **`Retired <date>`, `Definition changed <date>`** | absolute | **Leave absolute.** These are records of when something was decided, not elapsed time. Relative belongs in the tooltip if anywhere. |
| **The as-of chip, trend-axis labels** | absolute | **Never relative.** The as-of is a date somebody chose; "3 days ago" for a deliberate selection would be actively wrong. |

**Two traps the pass turned up, and the first is the important one:**

1. **Relative to WHOSE now?** Every relative string on this page would
   be computed from the browser's real clock - but the dashboard is
   routinely read **as of a past or future date**. Viewing as of
   2027-09-01, a `Last QA run` reading "2 days ago" against the real
   2026 clock is not merely unhelpful, it is false. **Relative time on
   this page must be relative to `CURRENT_AS_OF`, not to `new Date()`**,
   everywhere except the masthead clock (which genuinely is about now).
   That is a rule the standard has to carry, and nothing in the
   dictated version implies it.
2. **The standard has no future tense.** "X ago" covers the past.
   `mothman schedule show` is a table of **future** dates - Due,
   Claimable from - and the runway warning counts forward. Those want
   "in 3 days" / "in 2 quarters". Worth settling with the same
   conversation rather than discovering it mid-build.

**Recommendation:** one requirement, covering the absolute format, the
relative format in both directions, the as-of-relative rule, and a
single helper that both the dashboard and the CLI resolve through - not
two more implementations. It supersedes #3, #14, #51 and road-testing
items 5 and 11.

**The 30-day fallback is FIXED, 2026-09-24 evening** (Keith: "also fix
the bug where it stops at 30 days"). `fmtRelativeTime()` now runs
minutes, hours, days, weeks, months, years and never returns an
absolute date. Handover points are expressed in days so there is one
number per boundary - a week at 7, a month at 30 - with the year
decided by the computed month count rather than a day threshold, which
is what stops "12 months ago" ever being printed.

**Everything else in this pass still needs the requirement.** Keith
agreed the analysis of the high-value sites; none of them are wired up
yet, and they should not be until the standard is signed off - the
as-of-relative rule above is exactly the kind of thing that is cheap to
build in and expensive to retrofit.

**Q4 IS NOW CLOSED AS A DECISION, 2026-09-24 evening.** Everything it
asked is settled; none of it is built beyond the two defect fixes
recorded above, and it still needs drafting as a real requirement
before any more is.

**Punctuation - Keith's call was that it is mine.** Settled as ONE date
string with an optional time in front of it, rather than two formats:

| | |
|---|---|
| A date | `Friday, 29 September 2026` |
| A date and time | `2:15pm Friday, 29 September 2026` |

Time is lowercase `am`/`pm`, no full stops, no leading zero on the
hour, and minutes always shown even on the hour (`2:00pm`), so a column
of them lines up.

**Why this shape.** His two dictated examples disagreed on the comma,
and the cheapest way to settle that is not to pick a winner but to stop
having two strings: the date form is his own example exactly, and the
date-and-time form is that same string with the time prefixed. One
thing to build, one thing to read, and no rule about when the comma
appears because it always does, in the same place.

**The CLI matches** - his own call, closing the fifth open point. Worth
recording the consequence once, since it was the reason for asking:
`mothman schedule show`'s date columns will read `Monday, 1 November
2027` rather than `2027-11-01`, so they no longer match the
`data-asset.yaml` a reader may have open beside them. He has made the
call and it is not re-litigated here - noted so that whoever hits it
later knows it was a decision rather than an oversight.

**Future tense is in** - his own call. The standard runs in both
directions: `in 3 days`, `in 2 weeks`, `in 2 quarters` as well as `X
ago`. Which means the trap the pass turned up is now a requirement of
the standard rather than a gap in it.

**THE RELATIVE HALF IS PARKED** - his own word, 2026-09-24 evening:
"let's park the whole relative date thing."

Read as parking the WORK, not the decisions. What stops: wiring
relative time into the high-value sites the pass identified - the
`Last QA run` column, the snapshots picker, latest arrival, release
notes and plans dates. None of that was built and none of it starts.

What stands:
- **The 30-day fix stays shipped.** He asked for it specifically,
  earlier in the same conversation, and it is in `d5158a1` and green.
  `fmtRelativeTime()` keeps running to years.
- **The decisions above stay recorded**, future tense included, so
  unparking is a matter of drafting rather than re-deciding.
- **The as-of-relative rule stays on the record** as the thing that
  must be built in rather than retrofitted, since it is the reason
  parking is cheap now and expensive later.

**So the absolute half is live and the relative half is parked.** #3,
#14, #51 and road-testing items 5 and 11 all resolve against the
absolute standard, and none of them needs the relative work.

**Next step, not taken:** draft this as a requirement. It has not been
drafted, and per `CLAUDE.md` nothing is built until Keith has signed
one off.

## Findings

Numbered continuously across critics. Each carries the critic's own
label in brackets so the original report is findable, what this session
**verified against the real code** (separately from what the critic
claimed), what a fix would cost, and a recommendation.

**Every one of these is waiting on Keith.** Nothing below has been
acted on.

Three did not survive verification unchanged, and the corrections are
recorded with them rather than quietly applied: #5's crash has a
narrower and more exact trigger than reported, #18's flag collision is
three-way rather than two-way, and #9's severity depends on a claim
about `mothman check` that turned out to be true for a different reason
than the one given.

**Where to start, if you read one thing.** Four findings are false
greens or broken renders in code that is live right now, and they are
the four this session would put in front of you first:

| # | What | Cost |
|---|---|---|
| **#5** | An uncaught `TypeError` on three of seven dataset pages, at the default as-of, dropping the Supply History panel - shipping past a gate whose whole job is to catch it | small fix, real gate work |
| **#1** | The executive legend counts `exhausted` and `nodata` agencies as GREEN - "Green, 2 agencies" directly above "6 datasets cannot be processed" | one expression |
| **#4** | Eleven "no automated quality rule defined" placeholders that read as passing checks everywhere above the fourth click | a design question |
| **#34** | Month names case-insensitive in the runtime, case-SENSITIVE in the gate - valid config refused with an untrue message | one `.lower()` |

Two more are missed criteria on requirements already marked `built`,
which is a different kind of problem: **#2** (the low-runway warning
never rendered in the dashboard, and it is due right now) and **#3**
(every date rendered on the viewer's clock, not the asset's).

**#33 and #47 are process questions, not code** - whether the register
should be able to say "built except for these criteria", and whether a
post-build critic should see a requirement's own `evidence:`.

### From `delivery-dashboard-ux-critic` (2026-09-24)

1. **[todo, 2026-09-24]** **[Dashboard UI]** **[F1] The executive tier
   counts every non-red, non-amber agency as GREEN - including
   `exhausted` and `nodata`.** The single most prominent sentence on the
   landing page can state that both agencies are healthy directly above
   a notice saying six datasets cannot be processed.

   **Verified.** `dashboard/qa-reporting-dashboard.template.html:2525`
   computes the green count by subtraction:
   `${DATA.agencies.length-redCount-amberCount} agencies`, where
   `redCount`/`amberCount` filter on `status==="red"`/`"amber"` only.
   Nothing else is subtracted, so `nodata` and `exhausted` land in the
   green bucket by arithmetic.

   The critic checked the rest and found it correct, and so did this
   session's read: `rollup()`/`rollupStatuses()` genuinely exclude both
   statuses, and one exhausted among five red still reads Red plus a
   marker. **It is only the legend counter.**

   Against `REQ-PIPE-053`'s "SHALL NOT allow an exhausted schedule to be
   absorbed by the worst-of status rollup at any tier" this is arguably
   met in letter - a legend counter is not `worstOf()` - and defeated in
   purpose. It is also exactly the false-green shape `runway.py`'s own
   docstring opens with.

   **Cost:** small. One expression, plus a decision about what the
   legend should say when the three buckets do not sum to the total.

   **Recommendation: fix.** Of everything in this file it is the
   cheapest severe one.

2. **[todo, 2026-09-24]** **[Dashboard UI, Pipeline & publishing]**
   **[F2] The low-runway warning is computed, tested, and never
   rendered anywhere in the dashboard.** `REQ-PIPE-053`'s criterion says
   "surface the low-runway warning both in the dashboard and as a
   non-fatal warning in the repository's gates". The gate half works.
   The dashboard half does not exist.

   **Verified.** `scheduleRunwayAsOf()` fills `out.low`
   (template:1694), `buildData()` stores it as `data.scheduleRunway`
   (:1822), and the ONLY consumer is `exhaustedNotice()` (:2475), which
   returns `""` unless `exhaustedCount` is non-zero. `grep` finds no
   other read of `.low` in the file. Two further criteria are vacuous
   as a consequence - "warn once for that calendar, naming it, its last
   authored period and how many datasets name it", and "distinguish a
   warning from a failure in text as well as colour" - because there is
   no warning on the page to name anything or to distinguish.

   This is live today: the quarterly calendar has 2 future slots against
   a threshold of 4, so a warning is due right now and no reader of the
   dashboard can see it.

   **What makes it worth Keith's eye rather than just fixing:** the
   requirement's own `decisions:` records `delivery-dashboard-ux`
   catching this exact half as "lost in scoping", and Keith explicitly
   choosing both surfaces. It was then lost again at build time, and the
   requirement is marked `built`.

   **Cost:** moderate. A real render path plus its placement, which is a
   design question, not a patch.

   **Recommendation:** treat as a missed criterion on a `built`
   requirement, not a new feature - and see #21, which asks what the
   register should have recorded.

3. **[todo, 2026-09-24]** **[Dashboard UI]** **[F3] Every date on the
   page renders in the VIEWER's timezone, not the asset's.** For any
   viewer west of UTC the displayed date is a day early, silently.

   **Verified.** `fmtDate()` (template:764) and `fmtDateShort()` (:765)
   are bare `toLocaleDateString("en-US", …)` with no `timeZone` option,
   fed `new Date(DATE_STR + "T00:00:00Z")`. Midnight UTC is the previous
   calendar day anywhere west of Greenwich.

   The critic measured it in four real browser contexts. In
   `America/New_York` the header chip read "As of: Sep 23, 2026" while
   the data shown was as of the 24th, and all six CP datasets reported
   arriving "Jul 31, 2026" when they arrived on 1 August.

   `REQ-PIPE-048`'s criterion 2 - "SHALL derive every wall-clock
   computation from that value, and SHALL NOT carry a hardcoded offset
   anywhere" - was built correctly in the engine (the critic confirmed
   the asset-clock default as-of holds even at UTC+14, which is the real
   bug that requirement killed) and the display layer was left behind.

   **Severity, honestly:** Perth is UTC+8, always ahead of UTC, so every
   date on this page is correct by coincidence for its actual audience.
   It breaks for a federal counterpart, a vendor, or Keith on a trip -
   with no indication anything has been re-interpreted. The same
   "right by coincidence" shape `REQ-PIPE-048`'s own decisions use.

   **Cost:** small-to-moderate. A `timeZone` option threaded through
   two formatters and the as-of label, and a decision about where the
   zone comes from.

   **Recommendation: fix**, and pair it with road-testing item 5
   (Keith's own sighting that the dashboard should display Perth time,
   not UTC) - they are the same subject arriving from two directions.

4. **[todo, 2026-09-24]** **[Dashboard UI, QA checks & contract]**
   **[F4] The "No automated quality rule defined" placeholder reads as
   a passing check at every level a reader actually looks.** Its honest
   label is four clicks deep; everywhere above that, an unchecked
   column reads as a healthy one.

   **Verified, including the count.** `pipeline/build_dashboard_data.py`
   (and the CP twin) synthesise a placeholder check with
   `current_status: "green"`, a full green `history`, and an honest
   `note`. The source comment says green "is the truthful answer"
   *because* the gap is labelled in `note` - and `note` renders in
   exactly one place, the check panel.

   Counted directly out of the real built `reports/*.json`: **11
   placeholders across the 7 real datasets** - all six CP datasets'
   `extract_timestamp`, `cp-investigations.end_date`,
   `cp-placements.placement_end`, and the `table` scope of
   `cp-clients`, `cp-carers` and `cp-case-workers`. The critic's
   browser pass found the column tile Green, the drawer reading
   "Passing 1, Warning 0, Failing 0" over 18 solid green squares, and a
   `table`-scope placeholder rolling a whole "Table-level checks"
   section to Green on its own.

   **One of the eleven is already about to go.**
   `cp-investigations.end_date` gets a real rule the next time CP runs -
   the date-ordering check added today. The other ten stay.

   **Cost:** moderate, and it is a design question rather than a patch:
   green is defensible, the problem is that "no rule" and "rule passed"
   are indistinguishable until the fourth click.

   **Recommendation:** worth a requirement of its own. At 30 datasets
   this is the most likely of anything in this file to become a real
   false-green incident.

5. **[todo, 2026-09-24]** **[Dashboard UI]** **[F5] An uncaught
   `TypeError` on three of seven datasets, at the DEFAULT as-of, on an
   ordinary drill-down - and it ships past the zero-console-errors
   gate.**

   **Verified, and the trigger is narrower and more exact than
   reported.** The critic said the crash hits `cp-clients`, `cp-carers`
   and `cp-case-workers` and named the placeholder's missing `key` as
   the cause. Both halves are right, but the correlation is exact and
   worth recording: those three are **precisely the three datasets
   carrying a `table`-scope placeholder** (counted in #4). The crash is
   in the `.scope-check` re-lookup loop (template:2895-2898), which only
   runs over scope sections - so `cp-investigations` and
   `cp-placements`, which have column-scope placeholders, do not crash,
   and `cp-notifications` and `birth-registrations` are clean. The
   critic's clean/crashing list is correct; the rule behind it is "has a
   table-scope placeholder", not "has a placeholder".

   The mechanism: rows are built with `data-check="${ck.key}"`, the
   placeholder has no `key` (confirmed absent in the real built JSON),
   so the attribute renders as the literal string `"undefined"`; the
   re-lookup `find(ck=> ck.key===btn.dataset.check)` compares
   `undefined === "undefined"`, matches nothing, and `check.name`
   throws. Everything `renderDataset()` renders after that loop is
   silently dropped, and the reader is left with a blank row that is a
   bare Green pill - and, in the accessibility tree, a `button "Green"`
   with no name.

   **The part that matters beyond the bug:**
   `dashboard/check_dashboard_renders.py` holds the built page to zero
   console errors and this is shipping, so that gate is evidently not
   exercising a Tier-3 drill-down. Same "verify at the LAST transform
   before the user" lesson `CLAUDE.md` already records from
   `plans/qa-pipeline.md` item 74, recurring.

   **Cost:** the crash itself is small. The gate gap is the real work.

   **Recommendation: fix, with a failing test first** per `CLAUDE.md` -
   and the test belongs at the render layer, not the data layer, for
   exactly the reason item 74 records.

6. **[todo, 2026-09-24]** **[Dashboard UI]** **[F6] The executive
   tier's own explanatory sentence is now false.** It reads "worst-of,
   so nothing silently hides behind a healthy average" (template:2521)
   directly above the legend counter that is doing precisely that (#1).
   Two statuses are now deliberately excluded from the rollup, by design
   and correctly, and the copy was never updated.

   **Verified** by reading the line. **Cost:** one sentence.
   **Recommendation: fix alongside #1** - they are the same paragraph.

7. **[investigate, 2026-09-24]** **[Dashboard UI]** **[F7] The
   exhausted notice says how many datasets cannot be processed and
   never says which, or what is waiting.** `REQ-PIPE-053` asks a
   message to "state how many supplies are waiting and since when" -
   which may be one of the filing-layer criteria its own `[BUILD]`
   decision already defers to sprint 8. Flagged rather than judged:
   the notice as written asserts "nothing can be filed" without saying
   what is piling up, which is the reader's next question.

   **Recommendation:** resolve as part of sprint 8 rather than now, but
   see #20 - at 30 datasets the missing names are a hunt.

8. **[todo, 2026-09-24]** **[Dashboard UI]** **[U1] You cannot reach a
   dataset from an agency page by keyboard at all.**

   **Verified.** The Tier-2 dataset rows - the primary drill-down, the
   thing this dashboard exists for - are bare `<tr data-nav='…'>`
   (template:2599, 2607, 2619) with no `tabindex`, no `role` and no
   `href`; `grep` finds no `tabindex` anywhere in the file. The critic
   captured the real Tab sequence and not one of the six rows appears
   in it.

   Tier 1 agency cards and Tier 3 column tiles ARE real `<button>`s, so
   keyboard navigation dead-ends at exactly one level above the data.

   **Cost:** small per row, but it belongs with #9 and
   `plans/dashboard.md` #15 as one accessibility pass rather than three
   patches.

9. **[todo, 2026-09-24]** **[Dashboard UI]** **[U2] Nine focusable
   controls live inside closed, `aria-hidden="true"` drawers.** After
   the last on-screen control, focus disappears into invisible widgets
   with no focus indicator anywhere. A WCAG 4.1.2 violation, and
   practically it reads as "Tab stopped working".

   **Not independently verified** beyond the critic's own captured
   focus trace - it is a runtime observation and the visual critic is
   currently driving the only browser. Recorded as reported.

10. **[todo, 2026-09-24]** **[Dashboard UI]** **[U3] `plans/dashboard.md`
    #15 confirmed still present, both halves**, checked across four
    distinct views: `document.title` never updates, focus never moves on
    route change, no ARIA live region announces one, and there are **2
    real anchors in the entire rendered page** - so middle-click,
    Ctrl-click and "copy link address" do nothing on breadcrumbs,
    agency cards, dataset rows or column tiles. A confirmation of an
    existing entry rather than a new finding; belongs with #8/#9.

11. **[todo, 2026-09-24]** **[Dashboard UI]** **[U4] A stale column or
    check deep link fails silently** - lands on the dataset page with no
    message, `STATE.columnName` still set to the bad value, and the
    broken segment still in the URL, so re-sharing propagates it.
    `REQ-DASH-055`'s evidence records a not-found state added for agency
    and dataset after exactly this class of bug; it was not extended to
    column or check. At 30 datasets with evolving schemas, stale column
    bookmarks are the common case, not the edge.

12. **[todo, 2026-09-24]** **[Dashboard UI]** **[U5] The placeholder
    check is not deep-linkable and Back cannot close its panel.** A real
    keyed check behaves perfectly (URL gains `/check/<key>`, Back closes
    the panel and restores the drawer, Escape does the same and syncs
    the URL - the critic verified all of it). The keyless placeholder
    from #4/#5 opens a panel with no URL change: not shareable, and Back
    skips past it. **Same root cause as #5** - fix the key and this goes
    with it.

13. **[investigate, 2026-09-24]** **[Dashboard UI]** **[U6] The
    exhausted dataset page is a dead end that hides real history.** It
    replaces the ENTIRE dataset page - columns, checks, arrival history,
    trends - with the exhausted message. `cp-case-workers` has 18 real
    committed runs behind that message and no affordance to reach them.
    Also: the two quiet states share one background
    (`rgb(238,234,221)`), differing only in dashed-vs-solid border and
    text colour, so "Schedule ended" and "No data" read the same at a
    glance. The visual critic is looking at that half in both colour
    schemes.

14. **[todo, 2026-09-24]** **[Dashboard UI]** **[U7] The asset's own
    timezone is configured, and the page still shows two zones side by
    side.** A dataset page reads `SLA: … by 09:00 AWST` next to
    `Latest arrival: 01:00 UTC`, leaving the reader to convert in their
    head to answer "did it meet the deadline". Both strings are
    hardcoded: `cadenceLabel()` writes `"AWST"` literally, and
    `arrivedAt` is `…slice(11,16) + " UTC"`, which takes the wall-clock
    characters and labels them UTC **regardless of the stored offset**.
    Correct today only because every stored value is `+00:00` - and
    making other offsets storable was `REQ-PIPE-048`'s entire point.
    **Same family as #3**; worth fixing together.

15. **[todo, 2026-09-24]** **[Dashboard UI]** **[U8] A broken sentence
    in the footer, on every page.**

    **Verified** at template:554: "…not just single-column rules Every
    dataset on this page is real, computed the same way…" - no sentence
    terminator where the mock-data sentence was removed by
    `REQ-DASH-055`, and "computed the same way" now appears three times
    in one paragraph.

    **Cost:** trivial. **Recommendation: fix** - it is visible on every
    page of the dashboard and it is one edit.

16. **[todo, 2026-09-24]** **[Dashboard UI]** **[U9] The agency page
    overflows horizontally on a phone.** `scrollWidth` 537 against a
    390px viewport, driven by `TABLE.dataset-table` at 539px: "Rows,
    latest run" is clipped mid-word and "Last QA run" / "Trend" are
    entirely off-screen. Before the first dataset row a reader scrolls
    past roughly two screenfuls of chrome. The exec page and the
    exhausted notice both render cleanly at that width.

    **Recorded as reported** - the visual critic has this one in scope
    and may add measurements.

### From `delivery-cli-ux-critic` (2026-09-24)

All of these were verified by this session running the real commands
just now, not by reading the critic's transcript.

17. **[todo, 2026-09-24]** **[Testing & dev tooling, Pipeline & publishing]** **[A1] The gate's success line asserts the exact
    opposite of the warning three lines below it.**

    **Verified** at `qa_tools/common/validate_schedule.py:740` - the OK
    line is a fixed string, `"… {n} dataset(s), every one of them
    expecting something."` `_expects_nothing_errors` asks whether a
    dataset derives zero periods **ever**; the OK line generalises that
    into a claim about **now**, and the two part company the moment a
    calendar runs out. With the asset clock past the quarterly
    calendar's last date, the gate prints "every one of them expecting
    something" immediately above a warning that six of the seven cannot
    be processed.

    **Cost:** small - one conditional, or dropping the clause.

    **SIGNED OFF AND FIXED, 2026-09-24 - Keith chose option (b)**: keep
    the headline as a statement about configuration validity and drop
    the clause. It now reads `schedule validation OK - 2 calendar(s),
    7 dataset(s), no configuration errors.`

    **Rejected: making the headline runway-aware**, the other option on
    the table. Config validity and remaining runway are deliberately
    separate concerns in this gate - one fails the build and the other
    must never do - and a headline speaking for both is exactly where
    they would get confused.

    **Failing test first**, `tests/test_validate_schedule.py::
    TestTheSuccessLineDoesNotContradictTheWarningBelowIt`. It drives the
    real gate against the REAL committed config with the asset clock
    moved past the quarterly calendar's last authored period, so the
    genuine exhausted warning fires, and asserts the headline makes no
    claim the warning contradicts. Two sibling tests guard the
    preconditions: that the gate still passes and the warning still
    fires - without which there is nothing to contradict - and that
    dropping the clause did not leave a bare "OK", since the counts are
    what tell a reader the gate read the whole file rather than falling
    out early.

18. **[todo, 2026-09-24]** **[Testing & dev tooling]** **[A2] The
    header's dataset count is not the number of datasets affected.**

    **Verified** at `validate_schedule.py:709` - the count comes from
    `{e.scope for e in errors if e.scope and e.scope.startswith("dataset ")}`,
    so a calendar-scoped error contributes **zero** to it no matter how
    many datasets that calendar serves. The critic reproduced a run
    reporting "affecting 1 dataset(s)" where seven of seven were
    affected.

    Criterion 22 is met in form. The number it produces is what a reader
    uses to judge urgency, and it is wrong in the safe-looking
    direction.

    **Cost:** small, but it needs a decision about what "affected"
    means, since it now has to fan a calendar error out to its datasets.

19. **[todo, 2026-09-24]** **[Testing & dev tooling]** **[A3] Every
    error names a correction; the one it names is the wrong one, and
    the options offered include the typo.**

    **Verified** at `validate_schedule.py:329` - the fix line is built
    from the calendar names present in the file. Rename `quarterly` to
    `quarterley` (one character) and six datasets each get "names
    calendar 'quarterly', which this asset does not define. Use one of:
    daily, quarterley, or add that calendar."

    Two real consequences: the true fix - one character, one line above
    those six datasets - **is never named**; and following the text
    literally points six datasets at the misspelling, turns the gate
    **green**, and commits a typo'd calendar name.

    **This is not a re-litigation of Keith's individual-reporting rule.**
    That rule is faithfully implemented and the critic says so
    explicitly: nothing is hidden and the header count is true (#18
    aside). A cause line printed ABOVE all six hides nothing and changes
    no count.

    **Cost:** small for the second half (stop offering a just-invented
    name among valid options); moderate for the first (a cause line
    needs to know which errors share a cause).

    **Keith's call**, and the critic's Q2 offers exactly that split:
    (a) add the cause line, (b) stop listing the typo, (c) both.

20. **[todo, 2026-09-24]** **[Testing & dev tooling]** **[A4/A5] One
    mistake produces two errors in two idioms, and the generated half of
    the fix lines names nothing.**

    **Verified** at `validate_schedule.py:148-159`. The three generated
    fixes are `"Remove it, or correct the spelling …"`, **`"Add it."`**
    and **`"Correct the value."`** The last two name no shape, no
    example and nowhere to look - against an NFR reading "every error
    here must be one a human can act on immediately". The hand-written
    fixes in the same report are genuinely excellent by contrast
    ("Write a duration with its unit, like 14d or 4h. This is never
    guessed at - a bare number could mean either."), and the generated
    ones are what a mistyped or missing key produces, which is the most
    common real mistake.

    Separately, the schema and semantic layers both fire for one
    mistake: `claim_window: 14` yields
    `calendars -> 0 -> versions -> 0 -> claim_window: Input should be a
    valid string. Correct the value.` AND `version 1's claim_window is
    14, which is not a duration with a unit.` - the same version,
    0-indexed and 1-indexed, two lines apart. The build decision "so one
    mistake is one error" was applied within `_expects_nothing_errors`
    and not across this seam, which also inflates #18's count.

    **Cost:** small for the wording. Moderate for the double-fire, which
    is a real seam between two validators.

21. **[todo, 2026-09-24]** **[Testing & dev tooling, Pipeline & publishing]** **[A6] The exhausted schedule wears the warning's
    label, in the one place a maintainer would act.**

    **Verified** in `qa_tools/common/runway.py`. `warning_lines()`
    prefixes BOTH states with `"WARNING (not failing the build)"`, and
    `summary()` says `"calendar 'quarterly' is low on runway"` for a
    calendar with **no** runway at all - then appends "The gate itself
    PASSED." Exit 0.

    The module's own docstring opens by calling these "TWO STATES,
    DELIBERATELY DIFFERENT IN KIND" and says an exhausted schedule is "a
    HARD FAILURE". Today they are textually the same state, and the
    severe one reads as the mild one. `REQ-PIPE-053` criterion 14 asks
    for a warning to be distinguished from a failure "in text as well as
    colour".

    **Defensible on the letter** - at the gate, nothing IS failing the
    build, and the hard failure lands at filing in sprint 8.

    **Keith's call**, and the critic's Q3 is the fork: change the words
    now ("NOT LOW - EXHAUSTED", and drop "low on runway" for that case),
    or leave it until the filing layer lands, on the grounds that
    changing the gate's voice twice is worse than once.

22. **[todo, 2026-09-24]** **[Testing & dev tooling]** **[A7] The
    runway number and the last period in one sentence belong to
    different objects, and the number cannot be checked against the
    file.**

    **Verified with real numbers**, run just now against the real
    committed config at `as_of` 2026-09-24:

    | | |
    |---|---|
    | quarterly calendar, future periods | **5** |
    | cp-clients and four siblings, future slots | **5** each |
    | cp-case-workers, future slots | **2**, its own last being 2027-Q3 |
    | what the warning prints | "calendar 'quarterly' has only **2** future supply slot(s) left - its last authored period is **2027-Q4**" |

    `remaining` is correctly the min across datasets - `runway.py`'s own
    docstring explains why - but the sentence attributes that dataset
    fact to the calendar, pairs it with the CALENDAR's last period, and
    names neither the driving dataset nor that a min was taken. Somebody
    opens `data-asset.yaml`, counts five future dates, and the tool's
    number is unreproducible.

    **This is the same confusion `REQ-PIPE-053`'s own `[BUILD]` decision
    already fixed on the dashboard side** - "a dataset's message names
    its OWN last period, not its calendar's" - surviving intact on the
    CLI side. At 30 datasets with mixed participation it is the normal
    case.

    **Cost:** small. **Recommendation: fix**, and it is the same edit
    the dashboard already had.

23. **[todo, 2026-09-24]** **[Testing & dev tooling]** **[A8] The
    low-runway warning is printed and not surfaced.**

    **Verified** at `cli/check.py:126-130` - the summary table has
    exactly three outcomes, `passed` / `not installed` / `FAILED`, all
    derived from a return code. The schedule gate returns 0, so the row
    is green `passed`, the closing line is "Every gate passed.", and the
    word WARNING appears nowhere in the summary.

    **One correction to the critic's framing.** It attributed the miss
    to the warning being "eight gates and two and a half minutes above
    the table". That is true and is the smaller half. The structural
    half is that `cli/check.py` has **no warning state to render at
    all** - a gate cannot report one even if it wanted to, so no amount
    of scrolling would change the summary.

    `REQ-PIPE-053` criterion 12 asks for the warning "as a non-fatal
    warning in the repository's gates". It is non-fatal and it is in a
    gate. It does not reach the surface anybody reads.

    **Cost:** moderate - a fourth outcome in `mothman check`, which is a
    change to every gate's contract with it, not just this one.

24. **[todo, 2026-09-24]** **[Testing & dev tooling]** **[B1/B2/B3]
    Ordinary wrong input produces Python tracebacks.**

    **Verified by running all four just now**, real `uv run mothman`,
    all exit 1, all ending in a 30-40 line traceback:

    | command | ends in |
    |---|---|
    | `schedule show --dataset birth-registrations` | `ScheduleConfigError: … pass \`until\` to say where to stop.` |
    | `schedule show --dataset nope` | `UnknownDatasetError: "'nope' is not a dataset…"` |
    | `schedule show --dataset cp-case-workers --until notadate` | `ValueError: Invalid isoformat string: 'notadate'` |
    | `schedule candidate-dates --calendar nope --year 2028` | `UnknownCalendarError: 'nope' is not a calendar…` |

    Four things wrong at once in the first: **the most obvious
    invocation for this repo's flagship dataset crashes**; it
    half-renders the dataset header and then dies; the message itself is
    genuinely good and is buried under 34 frames; and it names
    `` `until` ``, the Python parameter, rather than `--until
    YYYY-MM-DD`, the flag.

    The `--until` pair is the worst: a bare `ValueError` from
    `date.fromisoformat`, naming neither the flag, the format nor the
    command - because `cli/schedule.py:34` declares `--until` as free
    text rather than `click.DateTime`. Click's own convention
    (`Invalid value for '--until': …`) was one parameter away, and is
    what every other mothman command does. Meanwhile
    `candidate-dates`' Click-level errors are model behaviour: clean
    boxes, exit 2, usage line, `--help` pointer. **Same command group,
    two languages.**

    **Cost:** small and mechanical - `click.DateTime` for `--until`, and
    a `ClickException` wrap around the three known config errors.

    **Recommendation: fix, and decide it once for `mothman supply`
    too** - whatever `schedule` ends up doing here, `supply` should do
    the same way.

25. **[todo, 2026-09-24]** **[Testing & dev tooling]** **[B4] On a
    failing gate, the only coloured thing on screen carries no
    information.** The four real errors print uncoloured - visually
    identical to the OK output - and the ending is a red, full-width,
    boxed panel that repeats line 1 and adds "see output above",
    pointing back past what could be sixty lines.

    **Verified structurally**: `cli/schedule.py`'s `validate_command()`
    raises `click.ClickException("schedule validation failed - see
    output above.")`, and `_report()` prints every error with plain
    `print(..., file=sys.stderr)` - no Rich markup anywhere in it.

    **Cost:** small.

26. **[todo, 2026-09-24]** **[Testing & dev tooling]** **[B5] The
    stdout/stderr split reverses the printed order, defeating the
    code's own stated intent.**

    **Verified, reproduced just now.** `validate_schedule.py`'s comment
    says the warning is "printed AFTER the OK line rather than instead
    of it, so it reads as an additional thing to know rather than as the
    gate's verdict". The OK line goes to **stdout** (:740), the warning
    to **stderr** (:766-771). With `PYTHONUNBUFFERED` unset - i.e. CI,
    and a plain shell:

    ```
    $ env -u PYTHONUNBUFFERED uv run mothman schedule validate 2>&1 | head -6

      WARNING (not failing the build): calendar 'quarterly' has only 2 future supply slot(s) left …

      calendar 'quarterly' is low on runway. The gate itself PASSED.
    schedule validation OK - 2 calendar(s), 7 dataset(s), every one of them expecting something.
    ```

    The warning arrives **first**, with no verdict above it, and the OK
    line lands last. In a GitHub Actions log the first thing under this
    gate is an unqualified WARNING - exactly the reading the comment
    says the arrangement was chosen to avoid. This sandbox has
    `PYTHONUNBUFFERED=1`, which is why it has never been seen here.

    **Cost:** trivial - one stream, or one flush.
    **Recommendation: fix.**

27. **[todo, 2026-09-24]** **[Testing & dev tooling]** **[B6] The claim
    window renders as a raw `timedelta`.** `cli/schedule.py:71` prints
    `schedule.claim_window(dataset)` directly, giving `14 days, 0:00:00`
    and `4:00:00`. The config is authored `14d` and `4h`, and
    `REQ-PIPE-050` rejects any other form on purpose - "four ways to
    write one duration is four ways for thirty datasets' config to read
    differently". The one surface that displays it invents a fifth.
    `4:00:00` reads as a time of day, in a table whose neighbouring
    columns are literally times (`09:00 +0800`).

28. **[todo, 2026-09-24]** **[Testing & dev tooling]** **[B8/B9]
    `candidate-dates` tells you to copy something it does not give you,
    and will propose any year you ask for.**

    **Verified by running it.** `--year 2027` proposes four periods that
    are **already authored** - paste them and `validate` rejects them as
    duplicates. `--year 2020` proposes six years into the past,
    cheerfully. `--year 2030` leaves 2028 and 2029 unauthored, which is
    the zero-slots hole `REQ-PIPE-050` exists to catch, produced by the
    command the runway warning points you at as the remedy. The command
    knows the calendar's last authored period - the warning prints it
    one screen earlier - and does not use it.

    Separately its own help says "Copy what you want into
    contract/data-asset.yaml", and what it prints is a Rich table, not
    YAML. There is no `--json`/`--yaml` on any of the three commands.

    **Cost:** small for the year guard. Small for a `--yaml` output.

29. **[todo, 2026-09-24]** **[Testing & dev tooling]** **[B10] At daily
    cadence there is no way to ask "what's next?"**
    `schedule show --dataset birth-registrations --until 2026-09-24`
    prints **1370 lines** (counted just now), no pager, no `--from`, no
    `--limit`, no marker for today or the next due slot - and for a
    daily calendar `Period` and `Date` are the same string in all 1363
    data rows. The data team leader's actual question - *is my next
    supply due today, and am I past it?* - has no answer short of
    dumping three years. `slots.is_overdue()` and
    `next_unfilled_claimable()` exist in the model with no CLI surface.

30. **[todo, 2026-09-24]** **[Testing & dev tooling, Docs & process]**
    **[B11/B12] Help text and footers explain things the reader never
    sees, and enumerate nothing they do.**
    `mothman schedule --help` shows **`validate  Gate: a config error
    can never silently produce zero slots (REQ-PIPE-050).`** - a
    requirement ID in a Tier 1, human-facing listing (one other exists,
    `dashboard validate-hierarchy`; none of the other seven groups do
    it). `validate --help`'s body is a siting rationale written for a
    developer. There are **no examples anywhere in the group**, which
    `clig.dev` puts first. `--dataset TEXT` / `--calendar TEXT`
    enumerate nothing although the values are finite and known - and the
    penalty for guessing is #24's traceback. `--until` is described as
    "For a daily calendar, the last date to list" when it is **required**
    for one. And the per-dataset footer explains a period/slot
    distinction that no shipped config exercises, while the thing a
    reader would actually wonder about - why `cp-case-workers` shows 10
    rows against 20 calendar dates - is answered only by inference.

31. **[investigate, 2026-09-24]** **[Testing & dev tooling]** **[B13]
    `--dataset` means two different things - and it is actually three.**

    **Verified, and the critic understated it.** `grep` across `cli/`:

    | site | type |
    |---|---|
    | `cli/pipeline.py:59` | `click.Choice(["bdm","cp","all"])` |
    | `cli/debug.py` ×5 | `click.Choice(["bdm","cp"])` |
    | **`cli/debug.py:150`** (`debug changelog`) | **free text, "e.g. birth-registrations"** |
    | `cli/schedule.py:33` | free text, a dataset_id |

    So the fork **predates `schedule`** - `mothman debug changelog` has
    taken a real dataset id under this flag name all along. That does
    not make it better, but it does mean this is an existing
    inconsistency being inherited rather than one `schedule` introduced.

    `schedule`'s vocabulary is arguably the correct one (`bdm`/`cp` are
    collections, not datasets). The finding is that a fork exists and
    **`mothman supply` will have to pick a side**, and whichever it
    picks, one group reads wrong.

    **Keith's call**, and the critic's Q4 offers: (a) `supply` follows
    `schedule`, older usage is legacy; (b) `supply` uses a different
    flag name so the collision is not deepened; (c) decide the whole
    CLI's noun now and plan one reconciliation - against Keith's own
    recorded reasoning that "renames are how a CLI surface rots".

### What both critics found genuinely working

Recorded deliberately - a post-build pass that only lists faults gives
a false picture of the state of the code, and several of these are
things the critics tried to break and could not.

- **Back/Forward on the dashboard is exactly right.** Four navigations
  deep then four real back steps: each unwinds exactly one level, the
  drawer closes on the right entry, no skipped entries, Forward
  re-applies cleanly, Escape on a check panel closes it AND syncs the
  URL.
- **Deep links reconstruct real state cold**, and the query-string /
  path-segment split matches `docs/spa-best-practices.md` section A
  exactly.
- **`REQ-PIPE-048`'s headline fix holds** in all four viewer timezones
  tested, including UTC+14 where the viewer's own calendar had already
  rolled over. The bug it was written to kill is dead. (#3 is a
  different layer.)
- **`REQ-QAC-047`'s loud-failure behaviour works in the real page** -
  `checkStatus()` and `worstOf()` throw on an unknown value naming the
  value, where it came from and the valid set, and explain
  `exhausted` as "recognised but deliberately unorderable". The
  level-scoped vocabulary is called out as genuinely good design. One
  caveat worth carrying forward: in a browser "fail loudly" means an
  uncaught throw mid-render, which the VIEWER experiences as a silently
  half-drawn page - #5 is exactly that shape.
- **The dataset-level exhausted message is the best error copy on the
  dashboard** - names the dataset's OWN last period (the `[BUILD]`
  decision landed), says plainly "Nothing is wrong with the data", names
  the file to edit and the command that proposes the dates. Textbook
  attribution-theory error handling.
- **Exhausted is surfaced at every tier and correctly excluded from the
  rollup**, and is evaluated against the selected as-of rather than
  baked at build time. The notice cannot be dismissed.
- **`REQ-DASH-055` is met**: only real datasets, a "No data" tile rather
  than a vanishing dataset, and the raw unembedded template renders "No
  data embedded" with zero console errors.
- **Performance is comfortably inside the Doherty threshold**: 273ms
  cold load of a 3.7MB page, 14ms tier navigation, 11ms full as-of
  rebuild.
- **The YAML parse-failure path is exactly right** - one error, file
  named, line and column, "nothing below it can be checked until then",
  and no cascade. Criterion 23 clean, and the hardest one to get right.
- **The hand-written `fix` lines set a real bar** (see #20 for the
  contrast with the generated ones).
- **The runway warning names the file to edit and the command to run**,
  and warns **once per calendar** with a dataset count and no
  enumeration - the aggregation criterion is genuinely built and is the
  right shape for 30.
- **`mothman check` running every gate rather than stopping at the
  first** is the correct call and visibly pays off.
- **The Tier 1 siting decision for `mothman schedule` was right** -
  `delivery-cli-ux` won that one on the merits and nothing the critic
  drove contradicts it.

### What works at 2 datasets and will not at ~30

32. **[investigate, 2026-09-24]** **[Dashboard UI, Testing & dev tooling]** **Scale findings, collected.** Each belongs to a finding
    above; they are listed together because the shared cause is breadth,
    not any one of them.

    - One asset-level typo produces ~30 near-identical stanzas with the
      one-character fix named in none of them (#19).
    - The header's denominator gets wronger as calendar-level errors fan
      out (#18).
    - Runway's min-across-datasets attribution is guaranteed to be the
      normal case with mixed participation (#22).
    - `mothman schedule show` with no arguments will print a `used by:`
      line wrapping 30 dataset ids, with no summary and - in the one
      place somebody editing calendars actually is - no mention of
      runway at all.
    - No machine-readable output on any `schedule` command, across two
      separately-deployed assets somebody will want to script (#28).
    - The exhausted notice names a count and never a dataset (#7). Keith
      chose the notice over a badge and the decision names the risk
      ("a notice that sits there for weeks becomes wallpaper") - so this
      is a watch-item against a decision already taken, not a
      disagreement with it.
    - The false-green legend gets worse, not milder: at 30 datasets a
      handful of exhausted or never-supplied ones is routine (#1).
    - Eleven "no rule defined" placeholders across 7 datasets, honest
      label four clicks deep (#4).
    - The Tier-2 table repeats the same two-line provider string on
      every row and already overflows at 390px; at 30 rows that is 60
      lines of identical text (#16).
    - `worstOf([])` returns green, so a table whose checks are all
      retired rolls up green by vacuum. `REQ-QAC-047` **pins this as
      parity-not-bug** and names sprint 16's zero-active-checks gate as
      the fix - listed only so the pin stays visible.

### A process question, not a code one

33. **[todo, 2026-09-24]** **[Docs & process]** **`REQ-PIPE-053` is
    marked `built` and its dashboard half is not built** (#2). The
    requirement's own `[BUILD]` decision already records that `built`
    overclaims for the filing-layer criteria, and says so plainly - so
    the register is not silent about the gap in general. #2 is a
    different thing: a dashboard criterion, on a sprint whose dashboard
    work WAS in scope, which `delivery-dashboard-ux` had already rescued
    once from being lost in scoping.

    The question is whether the register's binary `built`/`not_started`
    model should be able to record "built except for these criteria",
    and if so how. The critic flagged it rather than deciding it, which
    is right - it is a call about how this project keeps its own
    records, and it belongs with Keith.

### From `delivery-critic` (functional, 2026-09-24)

Four of its findings are the same defects the dashboard UX critic
reached independently, by a different route, and are recorded above
rather than twice: its **A1** is #2 (runway never rendered), **A2** is
#1 (the exec green counter), **D1** is #5 (the `TypeError`), **D4** is
#15 (the footer). Two things that arriving twice does tell us, and both
are worth having:

- **#5 predates these twelve.** The functional critic traced it to
  commit `6dba466` (REQ-DASH-033, 2026-09-20), and found that
  `REQ-DASH-055`'s own evidence describes finding and fixing the **same
  class of bug in the same function** - `renderDataset()` dereferencing
  whatever `find()` returned - without covering this call site.
- **Its own consequence is worse than the UX critic saw.** The
  `forEach` aborts, so everything after that block in `renderDataset()`
  never runs, and what is lost is the **Supply History panel**. Verified
  in its own browser pass: present on the four clean datasets, gone on
  the three that throw.

It also read the requirements' own `evidence:` and `decisions:` blocks
(which sit in the same file as the criteria) and **disclosed that it
did**, flagging the isolation risk itself. It mitigated by checking
every load-bearing claim independently - and that turned out to matter,
because **three evidence claims are overstated** (#35, #39, #43). Worth
deciding whether a future critic gets criteria-only extracts; recorded
here as its own question, not acted on.

34. **[todo, 2026-09-24]** **[Pipeline & publishing]** **[A3] Month
    names are case-insensitive in the runtime and case-SENSITIVE in the
    gate, so valid config is rejected with an untrue message.**

    **Verified by running both implementations just now:**

    ```
    schedule.parse_month_name("february")  -> 2
    validate_schedule._month_number("february") -> None
    validate_schedule._month_number("February") -> 2
    ```

    `REQ-PIPE-049` criterion 6 says "SHALL accept full month names only,
    **case-insensitively**"; `REQ-PIPE-050` criterion 4 says the gate
    "SHALL reject a month name that is not a real, full month name".
    `schedule.py`'s `parse_month_name()` lowercases;
    `validate_schedule.py`'s `_month_number()` does `_MONTHS.index()`
    against title case. The pydantic schema imposes nothing.

    The critic reproduced the end-to-end consequence on a copy of the
    real config: `delivery_months: [february, august]` produces **three**
    errors - two saying "names delivery month 'february', which is not a
    month" (untrue), and a third, "expects no supply in any period at
    all", which is a cascade of the first two and therefore inflates the
    header count that criterion 21 calls "the true count" (see #18).

    **Direction is a false RED, not a false green** - config the runtime
    honours perfectly is refused at the gate. But it is the same
    two-implementations-of-one-rule shape `REQ-QAC-047` exists to stamp
    out, one requirement earlier in the same batch.

    **Cost:** trivial - one `.lower()`. **Recommendation: fix, with a
    failing test first,** and the test should be the parity kind: the
    two functions should be held to each other, not each to its own
    expectation.

35. **[todo, 2026-09-24]** **[Pipeline & publishing]** **[A4] Two
    wall-clock computations are not on the asset clock.**
    `REQ-PIPE-048` criterion 2 - "SHALL derive every wall-clock
    computation from that value, and SHALL NOT carry a hardcoded offset
    anywhere". The hardcoded `AWST_OFFSET` is genuinely gone and
    `asset_time.py` is well built; two residues remain, neither covered
    by the requirement's own recorded exceptions.

    **Verified both.**

    - `qa_tools/common/validate_schedule.py:622` - `today = today or
      date.today()`. This is the boundary the retrospective-edit guard
      uses to decide "already in the past", and it is the RUNNER's naive
      local date. On GitHub Actions that is UTC, eight hours behind
      Perth, so for roughly a third of each Perth day a date is
      classified on the wrong side of "today" - precisely the class of
      bug this requirement is named for.
    - `dashboard/qa-reporting-dashboard.template.html:1739-1741` -
      `assetTodayDateStr()` falls back **silently** to
      `toDateStr(new Date())` (UTC) both when `ASSET_TIMEZONE` is null
      and when the zone name does not resolve. The raw-template case is
      legitimate and the comment says so ("never blank the page over
      it"); a built file whose embed produced a null, or an IANA name a
      given browser does not know, reverts to exactly the fixed bug with
      no signal. Against this requirement's own "no silent
      interpretation" stance, a visible degradation would be more
      consistent.

    **Cost:** small for the first. The second is a judgement about how
    loudly a browser should fail, which is the same question #5 raises
    from the other side.

36. **[todo, 2026-09-24]** **[QA checks & contract, Pipeline & publishing]** **[A5] Hierarchy identifiers are still restated inline
    across many modules, and the requirement's own evidence says the
    count is zero.**

    `REQ-QAC-039` criterion 1: "SHALL define each dataset's place in the
    hierarchy in exactly one place, and SHALL resolve every consumer's
    need for those identifiers through it." Its evidence reads *"the
    count is now zero, and the two that remain
    (`cp_common.COLLECTION_ID`, `bdm_common.DATASET_ID`)…"*.

    **The direction is confirmed and the evidence is wrong.** The critic
    counted **17 inline literals across 10 modules**, none of them the
    two named constants, and listed every site. This session's own
    broader grep finds 26 occurrences across 15 files - a looser count
    that also catches the two constants' own definitions and some
    comments, so the critic's narrower number is the more careful one
    and this session did not re-derive it line by line. Either way,
    "zero" is not the state of the code.

    It also names two structural neighbours:
    `qa_tools/bdm/evidently_check_lifecycle.py:25-27` spells the whole
    tree out as a literal check_id string, and
    `qa_tools/common/validate_hierarchy.py:66-69` keeps a hand-maintained
    contract-filename map that restates a relation `hierarchy.
    contract_path()` already holds - two places to edit when a third
    collection arrives.

    **What makes this more than tidiness is #41.**

    **Recommendation:** the evidence line needs correcting regardless of
    whether the literals do - an overstated `evidence:` is the thing a
    future session trusts instead of re-checking, which is the same
    failure `CLAUDE.md` records about a fabricated test count.

37. **[investigate, 2026-09-24]** **[Data generation]** **[A6/B3] Three
    `REQ-GEN-040` criteria describe capabilities no operator can reach.**

    **Verified by grep.** `partial_resupply=True` appears in the whole
    repository exactly three times, **all in `tests/`**
    (`test_generate_cp_runs.py:406`, `test_resupply.py:372/419/438`).
    Neither `generate_cp_runs.py` nor `generate_runs.py` ever passes it,
    and no `mothman` command exposes a flag, so `run_slot_chain()`'s
    default `partial_resupply=False` is the only behaviour a person can
    produce. `first_arrival_offset_days` is the same story - non-zero
    only in tests.

    Criterion 2 is phrased as an obligation on **output** ("SHALL
    generate at least one delivery in which some of a collection's
    tables are resupplied and the rest are not"), and as shipped the
    system does not. Criteria 1, 4 and 5 (single-dataset supply, early
    arrival, arbitrary lateness) are the same shape.

    Keith's own `[BUILD]` decision sanctions the sequencing, so this is
    not a surprise - but "the capability ships" is true of the library
    and not of the product.

    **Keith's call**, and the critic's Q2 frames it: give these a real
    `mothman` flag now (small, makes the criteria satisfiable by a
    person, and gives `REQ-GEN-044` a lever), or keep them library-only
    until the staging overlay lands. Its own caution against the flag is
    worth quoting: it would create a way to write a partial CP delivery
    into `data/deliveries/` that today's warehouse builder will crash
    on, which is what the off-by-default currently guards against.

38. **[investigate, 2026-09-24]** **[Pipeline & publishing, Dashboard UI]** **[A7] The dashboard is two slots away from asserting a stop
    that does not happen.**

    `REQ-PIPE-053` criteria 4, 5, 6, 7, 9 and 22 are self-admittedly
    unbuilt, and the critic confirmed it independently rather than
    taking it on trust: `grep -rn "exhausted" cli qa_tools pipeline`
    outside `runway.py` / `dataset_status.py` / `validate_schedule.py`
    returns **nothing**. No orchestrator, CLI command or filing path
    knows an exhausted schedule exists.

    **The consequence it names is the finding.** The quarterly calendar
    has two slots left (#22). On the day it runs out, the dashboard will
    render "N datasets cannot be processed - the delivery schedule has
    ended" while `mothman pipeline run` processes them exactly as before
    and publishes their results. The page will assert a stop that is not
    happening, and today there is nothing to stop it.

    **Recommendation:** this is sprint 8's work and it is already
    scoped - the finding is the DATE. It stops being theoretical when
    the calendar runs out, which is a known, computable day.

39. **[todo, 2026-09-24]** **[Pipeline & publishing]** **[B1/B2] Three
    model functions built in this batch have zero production callers.**

    **Verified by grep across `cli/ qa_tools/ pipeline/ generator/
    dashboard/`: no callers at all** for `schema_name`, `is_overdue`,
    `is_claimable` or `next_unfilled_claimable` outside their own
    definitions and tests.

    - `REQ-PIPE-051` criterion 6, "SHALL name a warehouse schema after a
      period": no warehouse schema in this repo is named after a period.
      It is a correct, tested pure function that nothing uses.
    - `REQ-PIPE-052` criterion 7, "SHALL determine whether a slot is
      overdue": nothing currently determines that anything is overdue,
      and no overdue slot appears anywhere a user can see.
      `next_unfilled_claimable`'s own docstring says "DO NOT USE THIS AS
      THE ASSIGNMENT RULE… nothing calls this yet, which is why it is a
      trap rather than a bug" - an honest warning and the right call.

    **Defensible for an early sprint**, and the critic says so. Its
    actual point is the record: `status: built` plus assertive
    `evidence:` prose reads, to anyone who does not open the code, as
    though these are live. Same subject as #33.

40. **[todo, 2026-09-24]** **[Data generation, Pipeline & publishing]**
    **[B4] Two signed criteria in this batch contradict each other.**

    `REQ-GEN-040` criterion 6: "SHALL NOT decide, record or emit which
    slot a generated supply fills."
    `REQ-GEN-043` criterion 6: "SHALL keep the generator's own
    bookkeeping - which scenario a delivery came from, **which slot it
    was built to fill** - in an artefact outside every delivery."

    The built system does the latter: `data/generator_bookkeeping.json`
    records `slot_id` and `period` per arrival. 043 is later and more
    specific so it plainly wins, and `tests/test_arrivals.py`'s static
    firewall is a strong guard on the pipeline side - but **040/6 as
    written is not met**, and the only thing between "recorded outside
    the delivery" and "read while filing" is that test.

    **Cost:** a wording change. **Recommendation:** reconcile the two
    rather than leave two signed criteria disagreeing - a future session
    reading 040 alone would conclude the bookkeeping file is a defect.

41. **[todo, 2026-09-24]** **[Pipeline & publishing]** **[D2]
    `arrivals_for()` answers an unknown collection with silence.**

    **Verified** at `qa_tools/common/arrivals.py:141-142` - `if found !=
    collection_id: continue`, returning `[]`. The critic confirmed the
    behaviour live: `arrivals_for('civil-registration-RENAMED','run_')`
    → `[]` against `42` for the real id.

    Combined with #36's inline literals, **renaming a collection in
    `contract/data-asset.yaml` gives every BDM/CP entry point zero
    arrivals rather than an error** - a pipeline that processes nothing
    and reports nothing wrong. The check-lifecycle hierarchy-agreement
    gate would eventually fail on the same rename, so it is caught - by
    a different gate, for a different reason, and only because check ids
    happen to carry the collection segment.

    Everywhere else in these twelve an unknown id raises
    (`hierarchy.dataset`, `schedule.calendar`). This one is the
    exception, and it is the false-green direction.

    **Cost:** small. **Recommendation: fix** - it is the same
    "no permissive fallback" stance `CLAUDE.md` takes elsewhere.

42. **[todo, 2026-09-24]** **[Pipeline & publishing]** **[B6] The claim
    window is not effective-dated, so a new calendar version moves
    history.**

    **Verified** at `qa_tools/common/schedule.py:611` -
    `return calendar_for_dataset(dataset_id).current.claim_window`.
    `claim_window` is a per-VERSION field, and `slots_for_dataset`
    applies the CURRENT version's value to every slot it derives,
    including slots for periods years in the past. Author a new version
    changing `14d` to `7d` and every historical slot's
    `claim_opens_at` moves.

    That is the retroactivity `REQ-PIPE-051` built `_effect_windows()`
    to prevent for dates, arriving by a different door:
    `periods_for_calendar()` got this right and `claim_window()` did
    not.

    **Cost:** moderate - it needs the same effect-window resolution the
    dates already have. **Recommendation: fix**, and it is a real
    correctness bug rather than a polish item, so a failing test first.

43. **[todo, 2026-09-24]** **[Testing & dev tooling]** **[C1/C3/C4] Two
    gates claimed to catch "a throw reaching a viewer" do not, and the
    gate's own three reporting criteria have no test at all.**

    **Verified, with one correction to the critic.**

    - **The e2e exhausted test misses uncaught exceptions.**
      `tests/test_dashboard_e2e.py:1329` registers only a `console`
      handler. The suite's own `clean_page` fixture (lines 58-68)
      registers **both** `console` and `pageerror` and asserts in
      teardown - this test uses plain `page` instead. So
      `TestAnExhaustedScheduleIsLoud` passes while the very dataset page
      it navigates to throws (#5).
    - **`dashboard/check_dashboard_renders.py` only ever loads the
      landing page.** `_check_render()` does one `page.goto()` per file
      and asserts `#view` is non-empty; it never navigates to a Tier-2
      or Tier-3 route. **The critic's wording implies this gate lacks a
      pageerror handler - it does not** (line 108 registers one). The
      gap is navigation coverage, not the handler, and that distinction
      matters for the fix: adding a handler would change nothing.
    - **`REQ-PIPE-050`'s criteria 19, 21 and the second half of 22 live
      entirely in `_report()`, and `_report()` has no test.** The only
      gate-level assertion in the suite is
      `tests/test_validate_schedule.py:372`, `assert
      validate_schedule.main() == 0` - the happy path. **Criterion 1**
      ("SHALL exit non-zero on any error") is never exercised: the tests
      assert `validate()` returns a non-empty list, not that the gate
      exits 1. Four smaller branches are uncovered too (missing asset
      file, a collection with no `contract:` key, a non-numeric
      `latency`, an unparseable previous-commit version).

    `REQ-QAC-047`'s own evidence says the render check "holds the built
    page to zero console errors and so is what would catch a throw
    reaching a viewer". #5 is a throw reaching a viewer on three of
    seven dataset pages, and the gate is green.

    **Recommendation: fix all three**, and take the cheap one first -
    switching that one e2e test to `clean_page` is a one-word change
    that would have caught #5.

44. **[todo, 2026-09-24]** **[Pipeline & publishing]** **[D3] The
    retrospective-edit guard is narrower than its prose reads.**

    **Verified.** `validate_schedule.py:597` defaults to
    `ref="HEAD~1"`, and both workflows check out at `fetch-depth: 2`. A
    push containing two or more commits is therefore only ever checked
    against its last one - move a past date in commit A, land commit B
    on top, and it passes. Separately, lines 655-656 clear the finding
    if the version's changelog differs from the previous commit's **in
    any way**, so an unrelated changelog line added to the same version
    in the same commit silently licenses a past-date move.

    Both are reasonable simplifications for a "say what you did" gate.
    Neither is written down, and the requirement's decision prose reads
    as though the guard is complete.

    **Cost:** small to document, larger to close. **Recommendation:**
    decide which, and write down whichever is chosen - an
    under-documented guard is one a future session will trust further
    than it goes.

45. **[investigate, 2026-09-24]** **[QA checks & contract]** **[B5] One
    pinned false green, flagged only so the pin stays visible.**
    `status-cases.json`'s case
    `nodata-alone-is-green-and-that-is-a-known-false-green` has
    `worst_of(["nodata"]) === "green"` in both implementations, by
    agreement, as a parity case rather than a parity bug, with sprint
    17 named as the structural fix. The critic flags it because it is
    the one place in this batch where the shared table's authority is
    used to bless a false green, and because
    `ds.status = worstOf(ds.columns.map(c=>c.status))` (template:1841)
    would carry it straight to the dataset tile. **Unreachable today**
    (per-check `nodata` does not exist yet) - which is precisely the
    condition sprint 17 changes. No action; the pin is correct.

46. **[investigate, 2026-09-24]** **[Docs & process]** **What the
    functional critic deliberately did NOT verify**, recorded so
    nothing here reads as a clean bill:

    - Generator determinism and byte-identity (`REQ-GEN-040` criteria 7
      and 8, `REQ-GEN-042` criteria 6-8). It did not re-run the
      generator; it confirmed `anchor_date.py` is pinned and no
      `date.today()`/`datetime.now()` exists in the generator, which
      makes the claims plausible but unmeasured.
    - `REQ-GEN-043` criteria 8-10 (emitting a split extract, a
      non-matching file, an unparseable one) - read, not driven.
    - `REQ-QAC-047` criterion 1 at full breadth - it did not re-run the
      ~30k-status browser comparison.
    - `REQ-PIPE-049` criteria 12, 15 and 16 - read, not driven.
    - The per-element `expectedTime`/`latency` fix - parser read, the
      150-arrival verdict pin not re-run.
    - Branch coverage: not measured in this project at all
      (`[tool.coverage.run]` does not set `branch = true`) - a known,
      parked gap. Every coverage number in these findings is line
      coverage.

47. **[todo, 2026-09-24]** **[Docs & process]** **A critic reading a
    requirement's `evidence:` and `decisions:` is reading the builder's
    own account of the work, in the same file as the criteria.** The
    functional critic disclosed this itself, unprompted, and mitigated
    by checking every load-bearing claim independently - which is the
    only reason #35, #36 and #39's overstatements surfaced rather than
    being confirmed back.

    Its own question, and a fair one: should a future post-build critic
    get **criteria-only extracts** rather than the whole register entry?
    Against that - `decisions:` is exactly where a rejected alternative
    lives, and a critic that cannot see one will re-propose it.

    **Keith's call.** Recorded here rather than decided.

### From `delivery-dashboard-visual-critic` (2026-09-24)

**This critic's measurements reproduce exactly.** Every contrast ratio
it reported was recomputed here from the real token values in the
template, and all eight came back to the second decimal place - 2.81,
1.51, 3.55, 1.51, 13.22, 5.35, 12.78, 6.54. Every CSS rule it cited is
at the line it named. Nothing in its report needed correcting, which is
not true of the other three.

Its **V1** is #1 (the exec green counter, reached by a third
independent route and measured in three separate as-of states) and its
**V15**'s terminator half is #15; both are recorded above rather than
twice. It deliberately did not re-find the `TypeError`.

48. **[todo, 2026-09-24]** **[Dashboard UI]** **[V2] Hovering a dataset
    row makes the "No data" pill's fill vanish into the row.**

    **Verified - the two rules are the same token.**
    `.dataset-table tbody tr:hover{background:var(--surface-alt);}`
    (template:243) and `.pill.nodata{background:var(--surface-alt); …}`
    (:152). The critic measured the hovered result: pill background and
    row background both `rgb(238,234,221)`, a contrast of **1.00:1**.
    Unhovered it is already only 1.20:1.

    What is left under the cursor is the 1px dashed border, which is
    itself invisible (#49). So at any past or future as-of - where
    "No data" is the most common row state - the status token
    disappears when a reader points at it. `.pill.exhausted` loses its
    fill the same way but survives on its dark border and dark text.

    **Only findable by hovering.** Neither rule is wrong on its own.

    **Cost:** trivial. **Recommendation: fix.**

49. **[todo, 2026-09-24]** **[Dashboard UI]** **[V3/V5] The `nodata`
    pill fails WCAG AA in both themes, and its dashed border is not
    visible at all.**

    **Recomputed here from the real tokens:**

    | | text on own fill | border on own fill |
    |---|---|---|
    | `nodata`, light | **2.81:1** | **1.51:1** |
    | `nodata`, dark | **3.55:1** | **1.51:1** |
    | `exhausted`, light | 13.22:1 | 5.35:1 |
    | `exhausted`, dark | 12.78:1 | 6.54:1 |

    At 12.5px/700 the WCAG bar is 4.5:1, not the large-text 3:1 - so
    both `nodata` readings fail. A **4.7× gap** separates two states
    that sit side by side.

    **The border number is the more interesting one.** `REQ-PIPE-053`'s
    own CSS comment says the exhausted pill is "deliberately unlike the
    other four: a solid border and a square marker". In practice the
    distinction is not dashed-versus-solid - it is *no visible border*
    versus *a visible one*. It happens to work, but not for the reason
    the code gives.

    **And the marker does nothing.** `.pill.nodata .ico` is
    `border-radius:2px`, `.pill.exhausted .ico` is `1px` (:153, :159).
    At 9px those are both squares - the critic checked at device scale
    and they are indistinguishable. So of the three devices meant to
    separate the two quiet states, the background is identical, the
    marker is imperceptible, and **all the work is done by text
    contrast** - which is the token that fails AA.

    **Keith's call, and the critic's Q3 frames the real tension:**
    fixing the contrast means making the quiet state louder, which is
    the opposite of what "quiet" was for. Its three options: raise both
    tokens (clears AA, narrows the 4.7× gap doing the actual work); fix
    only the border (makes dashed-vs-solid real, leaves the text
    failing); or log it as a standing accessibility item across every
    muted token, since the footer (#54) and `--ink-faint` generally
    have the same problem and fixing one pill leaves the pattern.

50. **[todo, 2026-09-24]** **[Dashboard UI]** **[V4] `1.5px` borders
    render as `1px`, so the intended weight difference does not exist.**

    **Verified in source** - `.pill.exhausted` (:158) and
    `.notice-exhausted` (:160) both declare `border:1.5px solid`. The
    critic measured computed `borderTopWidth` in a real browser at
    DPR 1: **`1px`**, both. Chrome floors 1.5 device-independent px to
    1 device px at 1×.

    So the exhausted pill's border is the same weight as the nodata
    pill's; only style and colour differ. It renders at 1.5px on a 2×
    display and 1px on the 1× displays most government desktops use, so
    it is also **inconsistent between machines**.

    Exactly the case where reading the source gives the wrong answer -
    worth keeping as an example, not just as a fix.

51. **[todo, 2026-09-24]** **[Dashboard UI]** **[V8/V9] `REQ-PIPE-048`'s
    stored offsets reach two render sites, and neither handles them.**

    **Verified in the real built data and the real template, and this
    resolves a puzzle the two dashboard critics each saw half of.** One
    field, `arrivedAt`, formatted at one site and not the other:

    - **The SLA tile** (template:1239) builds it as
      `d.lastArrival.arrivedAt.slice(11,16)+" UTC (earliest extract,
      latest run)"` - character-slicing the wall clock out of the string
      and labelling it UTC unconditionally. Correct today only because
      every stored value is `+00:00`, which is the thing `REQ-PIPE-048`
      changed. (This is #14 from the other direction.)
    - **The supply-history table** (:2690) renders `e.arrivedAt`
      **raw**. Confirmed in `reports/birth_registrations_dashboard.json`:
      **43 values, every one of the form
      `2026-09-16T05:17:30.280161+00:00`** - ISO-8601 with microseconds
      and an explicit offset, straight into a user-facing TIMING column.

    The critic's screenshot shows the column going, in three consecutive
    rows, from `1 day since previous` to `0 days since previous` to an
    amber pill plus that raw string.

    **A stale comment sits right above it.** Template:767-769 says
    "`lastArrival.arrivedAt` on its own is only ever a time
    (`05:07 local`, `14:32 UTC …`)". The data no longer has that shape;
    :1239 manufactures it, and `fmtArrival()` interpolates whatever it
    is given.

    **The tile is also the timezone problem made concrete.** In one
    four-across strip the SLA tile reads `Daily, by 14:00 AWST` and the
    arrival tile reads `05:29 UTC`, and a reader must add eight in their
    head, across two tiles, to judge the "Early" verdict sitting in the
    same cell. The one place the asset clock is visible is in the wrong
    clock - against a requirement whose story is "so that a supply that
    arrived at 10pm in Perth is not read as having arrived the following
    afternoon".

    **Keith's call, the critic's Q4:** render every user-facing instant
    in the asset timezone (matches the story, one formatter, changes
    several existing views so it wants its own requirement); keep UTC
    but format it properly; or split - format the supply-history
    timestamps now as a plain rendering defect, and scope the
    UTC-vs-AWST question separately. **This is the same subject as #3,
    #14 and road-testing item 5**, arriving from a fourth direction.

52. **[todo, 2026-09-24]** **[Dashboard UI]** **[V6/V7] The mobile
    overflow's widest driver is the badge row, not the table - a
    different fix from the one #16 implies.**

    The dashboard UX critic measured `scrollWidth` 537 against 390 and
    attributed it to `TABLE.dataset-table` at 539px. On the agency page
    at `?asof=2027-09-01` the visual critic measures `scrollWidth`
    **613**, and the widest overflowing element is the **badge row**
    (`display:flex; flex-wrap:nowrap`) at **597px** - its
    `Owned by Brian (qa), Reg (peer_review), Arthur (manager)` pill
    alone is **336px**, `white-space:nowrap` inherited from `.pill`
    (:138). The table's right edge is 561, second.

    Different fix - `flex-wrap:wrap` on the badge row - so worth
    separating from #16 rather than folding in.

    **Separately, `REQ-PIPE-053`'s own collection-level count marker is
    clipped at 390px.** `.collection-title` (:233) is a flex row with no
    `flex-wrap`: container `clientWidth` 358 against `scrollWidth` 368,
    and the `1 schedule ended` pill's right edge sits 10px past the
    container's. The new marker is the thing cut off.

53. **[todo, 2026-09-24]** **[Dashboard UI]** **[V11/V12/V13] The two
    new quiet-state branches were written with a different markup shape
    from the branch beside them.**

    Three separate consequences, all measured:

    - **Four column headers hang over nothing.** At `?asof=2027-09-01`
      all six Tier-2 rows use a `colspan="4"` message cell, so
      `LATEST ARRIVAL`, `ROWS`, `LAST QA RUN` and `TREND` have zero
      content in every row - **579 of 1179px (49%) of the table** at
      1440, and 37% at 390 where they are what pushes it past the
      viewport. Worse, the message starts *under* `LATEST ARRIVAL`, so
      "No QA run within tolerance as of the selected date" reads as a
      value in that column.
    - **The status pill moves 630px.** On a normal dataset page the
      pill sits at x=922 in its own right-hand cluster; on the
      exhausted and no-data branches it is **inline inside the `<h2>`**
      at x≈295 and x≈360, sized and shaped like the "View on GitHub"
      and "Owned by …" utility chips. A reader who has learned
      "status is top-right" finds it top-left.
    - **The same condition is a bordered box at Tier 1 and unstyled
      body text at Tier 3.** The exec notice has a border, a fill, a
      radius and `<code>` chips; the dataset-level message measures
      `background: rgba(0,0,0,0)`, `border: 0px none` - bare text on
      `--paper` on a page where everything else is a card. **Verified
      in source:** `.notice-exhausted code` (:163) is scoped to the
      notice, so the same two strings get a chip at Tier 1 and nothing
      at Tier 3. Two smaller ones in the same pair: `max-width` is
      `60ch` on one body and `56ch` on the other - two measures for two
      sibling states written the same day - and both `<code>`s fall
      back to the browser's `monospace` while every other code-ish
      string on the page uses `.mono`/IBM Plex Mono with tabular
      numerals.

54. **[todo, 2026-09-24]** **[Dashboard UI]** **[V10/V14/V15] Layout
    measure: the notice is 2.4× the page's own, the footer fails AA, and
    the exec grid is half empty.**

    - **The exec notice is 1180px wide over 583px of cards**, and its
      body measures **146 characters per line** at 13px - against
      `.view-sub`'s declared `max-width:62ch` sitting 20px above it.
      Nothing else on the page is that wide except the footer.
    - **The footer measures 162 characters per line, `max-width: none`,
      at 12px, with contrast 3.03:1 light / 4.16:1 dark** - both under
      4.5:1. `REQ-DASH-055` appended a sentence to it that reads as a
      changelog entry become permanent page furniture, and pushed the
      block to four lines. (#15 is the missing terminator in the same
      sentence.)
    - **`.grid` uses `auto-fill`** (:217, **verified in source**), so at
      1180px it computes four 284.5px tracks and fills two: **exactly
      half the executive tier is empty**, held open by phantom tracks
      `auto-fit` would collapse. The direct visual consequence of
      `REQ-DASH-055` removing three invented agencies from a grid tuned
      for five. The two real cards also **do not align internally** -
      `.card` is plain block flow with `.card-meta` unpinned, so a
      1-line title and a 3-line title put the sparkline and the meta row
      50px apart, leaving 69px of dead space under one card and 19px
      under the other (155px at the 2027 as-of).

    **The grid one is explicitly a judgment call, not a defect** - the
    critic says so - because `auto-fit` would stretch two cards to 583px
    each, which may read worse. **Keith's call, its Q1:** collapse the
    tracks, cap the grid to its content, or leave it on the grounds that
    it self-corrects as the asset grows.

55. **[todo, 2026-09-24]** **[Dashboard UI]** **[V17] Seven of eleven
    focusable element types fall back to Chrome's default focus ring.**

    **Verified in source:** `grep` finds `:focus-visible` rules at
    template lines 106, 224, 346, 347, 353, 354 **and nowhere else** -
    four elements (`.wordmark`, `.card`, `.scope-check`, `.check-card`)
    got a deliberate `2px solid var(--accent)` ring with
    per-element offsets, and everything else did not.

    What did not: **`.col-tile`** (the primary interactive surface of
    the dataset page), all nine masthead chips including **the As-of
    chip** - which is `REQ-PIPE-048`'s own control and the thing *both*
    quiet-state messages instruct the reader to go and use - plus
    `.crumb`, `.pill.tag.sm`, `.link-btn`, `.drawer-close` and `INPUT`.

    **The problem is coverage, not craft** - the four that exist are
    properly designed. Belongs with #8/#9/#10 as one accessibility pass.

56. **[todo, 2026-09-24]** **[Dashboard UI, QA checks & contract]**
    **[V16/V18/V23] The page's own statement of its colour language is
    out of date, and the language is reused for something else.**

    - **The legend names three statuses; the vocabulary has five.**
      `.legend-key` hardcodes Green / Amber / Red at both the exec
      (:2524) and dataset (:2838) tiers, while `REQ-QAC-047`'s
      `statusVocabulary()` carries `nodata` and `exhausted` too with
      `STATUS_LABEL` supplying their names. At `?asof=2027-09-01` the
      page renders a legend naming three statuses directly above two
      cards carrying the two it omits.
    - **The MoSCoW pills reuse the status palette.** **Verified in
      source:** `MOSCOW_CLASS = {must:"red", should:"amber",
      could:"green", wont:"nodata"}` (:3818) and
      `REQ_STATUS_CLASS = {built:"green", …}` (:3822) - so a
      requirement renders `● Must` in exactly the pill a failing
      dataset uses, and the critic captured one viewport with `● Red`
      agency pills on the left and `● Must` requirement pills on the
      right. Outside these four requirements' build scope, but squarely
      inside the status vocabulary `REQ-QAC-047` owns.
    - **Three visually identical check cards** in one column drawer,
      same title, same description, same Red pill - distinguishable
      only by 12px grey monospace (`dbt:multiple_birth_sibling` /
      `soda:sibling_match` / `datacontract:sibling_match`). They read as
      a rendering bug at a glance, and the threshold line carries
      **two formats for the same fact** - `REQ-QAC-047`'s
      no-threshold-fallback rule surfacing as the prose "no
      single-sided threshold — status is this tool's own verdict",
      which wraps mid-sentence and reads as debug output.

57. **[investigate, 2026-09-24]** **[Dashboard UI]** **[V19/V20/V21/
    V22/V24] Five smaller visual findings, recorded together.**

    - **`exhaustedMarker()` produces duplicate-looking pill pairs at
      today's scale** - three `.pill.exhausted` within 40px vertically
      on the Tier-2 page, the last two adjacent and identically styled.
      **This is the one finding that gets BETTER at 30 datasets** ("17
      schedules ended" is genuinely useful), which is why it is a
      judgment call. **Keith's call, its Q2:** keep as built, suppress
      the marker at count 1, or merge the pair into one pill.
    - **`box-decoration-break: slice` splits the command chip on
      mobile** - `<code>mothman schedule candidate-dates</code>`
      returns 2 client rects at 390px, rendering as two separate
      rounded boxes and reading as two commands.
    - **All nine masthead chips are 28px tall** at 390px, below both
      the iOS (44) and Android (48) tap minimums - including the As-of
      chip, which both quiet-state messages tell the reader to use.
    - **"No data" is two visual states, and one contradicts itself.**
      At `?asof=2022-01-01` (no history at all) the card has no
      sparkline - honest. At `?asof=2027-09-01` (history exists, none
      current) the card shows the **full 19-cycle sparkline ending in a
      red endpoint dot** under a "No data" pill - the only red pixel in
      that viewport, 130px under a pill saying there is no data.
    - **`.crumb` breaks mid-token at 390px** - "TIER 2" wraps to
      "TIER" / "2" on every mobile view. One `white-space:nowrap`.

### What the visual critic found genuinely working

- **`.pill.exhausted` survives dark mode properly** - 12.78:1 text,
  6.54:1 border, unambiguously the most prominent thing in its card.
  `REQ-PIPE-053`'s "never distinguished by colour alone" holds: the
  label says "Schedule ended" in words and the state is legible with
  colour removed. The other quiet state does not clear that bar (#49).
- **The exec notice earns its place in the squint test** - blurred, the
  page still resolves to "a bordered announcement at the top, two quiet
  cards below".
- **Tier-2 row messages are differentiated by weight, not just
  wording** - the exhausted row's message renders in `--ink`, the
  no-data rows' in muted. A real distinction doing real work.
- **The exhausted dataset page at 390px is the best-laid-out view in
  the whole pass** - pills wrap cleanly onto their own lines, measure
  lands around 42 characters, hierarchy holds.
- **No horizontal overflow at the exec tier at 390px** in either quiet
  state.
- **The drawer scrim is real** - checked because it looked absent.
- **Card and check-card focus rings are properly designed** (#55 is
  coverage, not craft).
- **`REQ-DASH-055`'s removal is visually clean where it matters** - no
  orphaned "illustrative mock data" chrome anywhere, in any state or
  theme.

### What the visual critic says breaks at ~30 datasets

58. **[investigate, 2026-09-24]** **[Dashboard UI]** **Visual scale
    findings, collected.** Each belongs to a finding above.

    - The legend arithmetic gets wronger: at 30 datasets some dataset
      is nearly always quiet, so the green number is nearly always
      inflated (#1).
    - The legend is nearly always incomplete - three named statuses out
      of five is survivable while quiet states are rare (#56).
    - Card misalignment goes from two ragged cards to eight ragged
      rows, with the last row always partly empty (#54).
    - The four dead columns multiply: 30 rows eating 49% of desktop
      width and forcing a 545px table into a 390px viewport (#53).
    - **The exec notice's scale risk is its calendar list, not its
      dataset count.** The heading aggregates correctly ("N datasets");
      the body inlines every unique calendar name in bold via
      `${which}`. Six calendars in a 146-character line is already at
      the limit - the heading scales, the body does not.
    - **The drawer's run-history squares do not scale at all** - 31
      runs already renders as 24 + 7, ragged, with no time axis and no
      grouping. A year of daily runs is ~365 16px squares, roughly 15
      ragged rows of full-saturation colour, sitting *above* the check
      list it is meant to introduce.
    - The duplicate check cards compound: four tools × one logical
      check is already three or four identical cards, and tool identity
      is the smallest, lowest-contrast text on each (#56).
