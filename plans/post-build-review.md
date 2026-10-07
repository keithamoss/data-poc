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

### AMENDED 2026-09-25 - the gate now applies to what is significant, not to everything

Keith's own words, after the first thirteen findings had been walked
through one at a time: "I don't actually care about reviewing all of
them. I just want to know the ones that are significant or really
require my decision as a product owner. I'm happy for you to fix minor
bugs or do bits and pieces of polish."

So step 4 above is narrowed, and steps 1-3 and 5 are unchanged.

**Still needs his sign-off:**
- A **significant defect** - one whose consequence is a wrong answer,
  lost work, silently broken behaviour, or a false green. Flagged
  before it is fixed, even when the fix itself is obvious, because he
  is entitled to know the system did that.
- Anything that is a **product decision**: what the dashboard should
  say, what a state should mean, what is worth building.
- Anything that **changes agreed behaviour or design**, including a
  palette or layout change visible across the page, and anything that
  reopens a decision already recorded.
- Anything touching `requirements.yaml`'s own claims, since the
  register is the permanent artefact.

**Does not need it any more:** minor defects with one obvious right
answer, wording, spacing, test coverage, and polish.

**Two things that do NOT relax**, because they are what makes the
narrower gate safe:
1. **Everything still gets written up here**, fixed or not, with its
   evidence. Delegating the decision is not delegating the record - he
   must be able to find out afterwards what was changed and why.
2. **A defect fix still gets a failing test first.** That is
   `CLAUDE.md`'s rule and it never depended on who signed the finding
   off.

**And the judgement call is deliberately mine to make wrong in one
direction only.** Where it is unclear whether something is minor, it
gets flagged. Over-reporting costs him a sentence; under-reporting
means shipped code changed on a judgement he never saw, which is the
thing the original rule existed to prevent.

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

**BOTH OF THESE WERE SETTLED LATER THE SAME EVENING** - see the
"Punctuation" and "The CLI matches" paragraphs at the end of the
relative-time pass below. Punctuation became one date string with an
optional time in front of it; config-echoing CLI output IS covered,
Keith's own call, with the consequence recorded there.

**This line said "Still open" until 2026-09-25 and cost something.**
A session preparing the six open items read it, did not read the
resolution two sections further down, and put the CLI question to
Keith as though it were undecided - with a lean OPPOSITE to the
decision he had already made. He agreed with the lean, so the record
briefly held two contradictory answers.

Left here rather than deleted, because it is the third time this
project has watched a decision get missed by a reader who stopped one
level above it (`plans/tooling.md` #17 is the other). A stale "still
open" is worse than no note at all: it does not merely fail to inform,
it actively asserts the wrong thing.

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

**The CLI matches** - his own call, 2026-09-24, closing the fifth open
point. Worth recording the consequence once, since it was the reason
for asking: `mothman schedule show`'s date columns will read
`Monday, 1 November 2027` rather than `2027-11-01`, so they no longer
match the `data-asset.yaml` a reader may have open beside them.

**SUPERSEDED 2026-09-25. Config-echoing output is EXEMPT.** Keith's
own call, put to him a second time and answered the other way: prose
and anything read AS A TIME follows the standard; a column that echoes
a configured value keeps its ISO form, so a reader can diff the table
against the file by eye.

**The second asking was an accident and is recorded as one**, because
the accident is the interesting part. A stale "Still open" line two
sections above this one (now corrected, see it for the full note) sent
a session to Keith with the question presented as undecided and a lean
OPPOSITE to the decision he had already made. He agreed with the lean.
The contradiction was caught by reading this paragraph while drafting
the requirement, and put back to him rather than resolved by picking
the newer answer or the better-informed one.

**Which is current: the 2026-09-25 exemption.** The 2026-09-24
paragraph above is left standing rather than rewritten, so the earlier
reasoning survives - it is a real argument for one rule with no
exemptions, and whoever revisits this should see it.

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

1. **[done, 2026-09-24]** **[Dashboard UI]** **[F1] The executive tier
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

   **SIGNED OFF AND FIXED, 2026-09-25 - Keith chose option (b)**, giving
   the quiet states their own counters rather than dropping them from
   the totals. Every figure is now COUNTED (`agencyCount(status)`)
   rather than derived by subtracting two of them from the total, and
   `No data` / `Schedule ended` appear with their own swatch and count
   whenever an agency is in that state - so the legend also stops
   naming three statuses when `statusVocabulary()` has five (#56's exec
   half).

   They appear only when real: two permanent `(0)` counters would be
   furniture on the ordinary page.

   **Failing tests first**, `tests/test_dashboard_e2e.py::
   TestTheExecutiveLegendCountsWhatIsActuallyThere`, in a real browser
   against the real built page. Three of four failed before. The one
   that matters most is not about any single number - it asserts **the
   figures sum to the number of agencies**, at a normal as-of, at
   `2028-01-01` and at `2022-01-01`. A subtraction cannot be checked
   against anything; a count can, and that is the property that makes
   this class of bug impossible rather than merely fixed.

   **#6 is NOT covered by this and still needs its own sign-off** - the
   view-sub sentence above the legend still says "worst-of, so nothing
   silently hides behind a healthy average" while two statuses are
   deliberately excluded from that rollup. It is less misleading now
   that the quiet ones are visibly counted, and still not true.

2. **[done, 2026-09-25]** **[Dashboard UI, Pipeline & publishing]**
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

   **SIGNED OFF 2026-09-25** - "we should rectify that, yep, definitely
   actually build that." To build, as the missed criterion it is rather
   than as a new feature.

   **DONE 2026-09-25.** `lowRunwayNotice()` renders on the landing
   view, above the fold, and is verified against the REAL built page
   rather than a fixture - the live config has 2 quarterly slots
   against a threshold of 4, so the warning is due right now.

   Three decisions the criteria needed and did not state:
   - **It names the dataset the number belongs to**, carried on the
     runway itself as `drivingDataset`/`drivingLastPeriod` - the same
     correction #22 needed on the CLI side, for the same reason:
     `remaining` is a minimum across datasets, so naming only the
     calendar pairs a number and a date belonging to different objects.
   - **It says in WORDS that nothing has failed**, which is the
     criterion about distinguishing a warning from a failure. Colour
     alone cannot do it on a page already using red and amber for data
     verdicts.
   - **It goes silent once a calendar is actually exhausted.** "Running
     low" stops being the news the moment it has run out, and two
     notices about one calendar is the repetition the once-per-calendar
     rule exists to prevent.

3. **[done, 2026-09-25]** **[Dashboard UI]** **[F3] Every date on the
   page renders in the VIEWER's timezone, not the asset's.** For any
   viewer west of UTC the displayed date is a day early, silently.

   **BUILT by `REQ-DASH-071`, 2026-09-25**, together with #51 and #60 -
   they are one subject arriving from four directions, and the
   requirement's own `decisions:` is where the thinking now lives.

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

4. **[done, 2026-09-25]** **[Dashboard UI, QA checks & contract]**
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

   **SIGNED OFF 2026-09-25, with a design direction from Keith**: "yes,
   we should definitely flag clearly that the column has no checks. I
   feel like maybe a grey, as in like a disabled kind of grey colour is
   the one to go for there - kind of speaks to it's inactive."

   So the answer is NOT amber or red. A column nobody checks is not
   failing and not warning - it is **inactive**, and disabled-grey is a
   vocabulary a reader already has for that. It also cannot be mistaken
   for a verdict, which is exactly what green was being mistaken for.

   **That makes it a sixth status rather than a colour swap**, and
   `REQ-QAC-047` owns the status vocabulary - so it lands in
   `statusVocabulary()`, `STATUS_LABEL`, the pill CSS, the legend
   (which #56 already says names three of five) and the Python twin in
   `dataset_status.py`, held to the same `status-cases.json` table.

   **The question the build has to answer**, noted now rather than
   discovered later: what a column whose only check is inactive ROLLS
   UP to. It must not win a `worstOf()` against a real verdict, and it
   must not silently vanish either - which is precisely the shape
   already settled for `nodata`.

   **DONE 2026-09-25, and here is the answer to that question.**

   `inactive` is **outside the ordering**, with `exhausted`, rather
   than given a number. Both available numbers are wrong: low and it
   loses every rollup and vanishes; high and an unasked question
   outranks a real failure. So `worstOf`/`worst_of` REFUSE it, and the
   filtering rollup handles it explicitly - a status carrying no
   verdict never competes with one that does, and never disappears
   either. Quiet-state precedence is `exhausted` > `inactive` >
   `nodata`, ordered by what a reader can act on: an ended schedule is
   why nothing is happening at all; "nobody wrote a rule" is a standing
   fact; "no run within tolerance as of this date" is temporal and may
   resolve itself tomorrow.

   **The Python twin had no filtering rollup at all** - `dataset_status()`
   called `worst_of()` directly, so the first check carrying `inactive`
   would have raised inside the GitHub Issues automation. It has
   `rollup_statuses()` now, held to a new `dataset_rollup_cases`
   section of the shared table, because that behaviour is genuinely
   different from ordering and both sides need it.

   **Three consumers, found the hard way and worth recording** - this
   is `CLAUDE.md`'s own "enumerate every consumer mechanically" lesson
   arriving again:
   - `pipeline/dashboard_check_labels.py`'s `status_rank()` indexed
     `STATUS_ORDER` directly and took the whole dashboard build down
     with a `KeyError`. That was the RIGHT failure - loud, at build
     time - and it now ranks an unorderable status below everything,
     locally, for headline sorting only.
   - Three `worstOf()` call sites in the template (`buildRealDataset`,
     `rollup`, and the exec-tier dataset loop) could all now receive
     one. All three roll rather than order.

   **My first attempt at the shared table was wrong and the harness
   caught it**: I wrote the filtering behaviour as `rollup_cases`,
   which drive `worstOf` - the ordering function - so they asserted
   that an unorderable status returns a value. The cases are split
   correctly now.

   **A reporting gap found alongside**, not fixed: Vitest's own
   stack-trace reader hits an `EISDIR` and the remaining tests in that
   file never report. It surfaced as "35 passed (42)" with one failure
   and seven tests unaccounted for.

   **CORRECTED 2026-09-25, having hit it again on #57 and diagnosed it
   properly.** This said the trigger was a test FAILING. It is not:
   the trigger is an EXCEPTION THROWN INSIDE THE JSDOM PAGE SCRIPT.
   Vitest tries to source-map a stack frame whose "file" is the
   directory the template was loaded from, gets `EISDIR`, and abandons
   the rest of that file - with or without any test failing. On #57 it
   hid five PASSING tests behind a fixture of mine that threw inside
   `aggregateFailureSeries()`.

   That makes it a useful diagnostic rather than only a nuisance: **a
   jsdom test file that stops partway means something in the page
   threw**, and the fastest way to find it is to re-run that file with
   `--reporter=verbose` and look at the last test that reported.

   **Verified against the real built page**, not a fixture: all eleven
   placeholders now read `inactive`, both table-scope sections roll up
   `inactive` rather than green, and the inactive columns provably do
   not change their dataset's own status in either direction.

   **What this does NOT fix, stated plainly:** a dataset whose columns
   are ALL inactive still rolls up `inactive`, which is right - but the
   sibling case `worst_of(["nodata"]) === "green"` remains the pinned
   false green of #45, and sprint 17 still owns it. Adding a third
   quiet state does not change that, and deliberately did not try to.

5. **[done, 2026-09-24]** **[Dashboard UI]** **[F5] An uncaught
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

   **IT IS WORSE THAN EITHER CRITIC FOUND, measured 2026-09-25 while
   building the accessibility cluster.** `navigate()` calls `render()`
   BEFORE `history.pushState`, so the throw aborts the navigation
   itself: clicking a row for `cp-clients`, `cp-carers` or
   `cp-case-workers` leaves **the URL completely unchanged**. Verified
   in a real browser - clicked the row, `url changed: False`, the
   address still reading `/agency/child-protection-family-support`
   while the page shows a half-drawn dataset view.

   So on three of seven datasets the address bar disagrees with the
   screen, Back goes somewhere else than the reader expects, a copied
   link returns to the agency, and a reload loses the drill-down. The
   critics reported a missing Supply History panel; the navigation
   being silently broken is the larger half, and neither saw it.

   **Still awaiting sign-off.** It is named here rather than fixed
   because it is not in the accessibility cluster Keith approved -
   though it is now the strongest candidate for the next one.

   **The part that matters beyond the bug:**
   `dashboard/check_dashboard_renders.py` holds the built page to zero
   console errors and this is shipping, so that gate is evidently not
   exercising a Tier-3 drill-down. Same "verify at the LAST transform
   before the user" lesson `CLAUDE.md` already records from
   `plans/qa-pipeline.md` item 74, recurring.

   **Cost:** the crash itself is small. The gate gap is the real work.

   **SIGNED OFF AND FIXED, 2026-09-25, in two places.**

   **The data.** The synthesised placeholder gets a real
   `key: "no_rule_defined"` in both build modules - unique within its
   column, which is the scope `/check/<key>` resolves in, and this
   placeholder is by definition the only check on its column.

   **The render.** The scope-check loop no longer dereferences whatever
   `find()` returned. A key that does not resolve is a real data bug
   and must not pass quietly, so it logs `console.error` - which fails
   `check_dashboard_renders.py`, exactly the gate that should catch it
   - removes the row, and lets the rest of the page render.

   **"Fail loudly" needs a different shape in a browser**, and that is
   the reasoning worth keeping. On a server it means a stack trace
   somebody reads. Here it meant a silently half-drawn page and a lost
   navigation, which is the opposite of loud. Loud to the GATE, not
   fatal to the READER.

   **Tests, at the render layer:** every one of the six CP datasets is
   loaded in a real browser under the fixture that asserts no console
   error and no uncaught exception; the three that threw are
   additionally asserted to still render everything after the scope
   sections; and a third test clicks the row and asserts **the URL
   actually changes**, which is the half neither critic found. Seven
   failed before the fix.

6. **[done, 2026-09-25]** **[Dashboard UI]** **[F6] The executive
   tier's own explanatory sentence is now false.** It reads "worst-of,
   so nothing silently hides behind a healthy average" (template:2521)
   directly above the legend counter that is doing precisely that (#1).
   Two statuses are now deliberately excluded from the rollup, by design
   and correctly, and the copy was never updated.

   **Verified** by reading the line. **Cost:** one sentence.
   **Recommendation: fix alongside #1** - they are the same paragraph.

   **SIGNED OFF AND FIXED, 2026-09-25**, one commit after the Tier 1
   rename rather than alongside #1 - Keith declined to fold it into the
   rename and then approved it on its own, which is the right order for
   a claim about behaviour rather than a label.

   It now reads: "...worst-of, so a failure cannot hide behind a
   healthy average. A dataset with no data, or whose schedule has
   ended, sits outside that comparison rather than losing to it, and is
   counted separately below."

   **The distinction the new wording carries** is the one the old
   sentence blurred: those two states are not losing to a healthy
   average, they are **not in the comparison at all** - and now that #1
   gives them their own counters, "counted separately below" points at
   something the reader can actually see three lines down.

   **No new test**, deliberately, and the reasoning is recorded rather
   than assumed: the behaviour this sentence describes is already
   pinned - `rollup()`/`rollupStatuses()` by `status-cases.json` on
   both sides, and the legend's own arithmetic by #1's
   figures-sum-to-the-agency-count test. A test asserting particular
   prose would pin the wording rather than the property, and would fail
   the next time somebody improved the sentence.

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

8. **[done, 2026-09-24]** **[Dashboard UI]** **[U1] You cannot reach a
   dataset from an agency page by keyboard at all.**

   **Verified.** The Tier-2 dataset rows - the primary drill-down, the
   thing this dashboard exists for - are bare `<tr data-nav='…'>`
   (template:2599, 2607, 2619) with no `tabindex`, no `role` and no
   `href`; `grep` finds no `tabindex` anywhere in the file. The critic
   captured the real Tab sequence and not one of the six rows appears
   in it.

   Tier 1 agency cards and Tier 3 column tiles ARE real `<button>`s, so
   keyboard navigation dead-ends at exactly one level above the data.

   **SIGNED OFF AND FIXED, 2026-09-25**, as one pass with #9, #10 and
   #55. Every `tr[data-nav]` now carries `tabindex="0"` and answers
   Enter and Space.

   **On the row rather than a control inside the first cell**,
   deliberately: the whole row has been the target since it was
   written, and moving the affordance into one cell would change what a
   MOUSE user clicks in order to fix what a keyboard user cannot reach.

   **Tests:** `TestTheKeyboardCanReachTheData` asserts every row is in
   the tab order, and separately that a focused row actually navigates
   on Enter - the attribute and the behaviour, because the attribute
   alone is a tab stop that does nothing.

9. **[done, 2026-09-24]** **[Dashboard UI]** **[U2] Nine focusable
   controls live inside closed, `aria-hidden="true"` drawers.** After
   the last on-screen control, focus disappears into invisible widgets
   with no focus indicator anywhere. A WCAG 4.1.2 violation, and
   practically it reads as "Tab stopped working".

   **VERIFIED and SIGNED OFF AND FIXED, 2026-09-25.** Confirmed in a
   real browser rather than taken from the critic's trace: focusing
   each control inside a closed drawer and checking whether
   `document.activeElement` actually became it.

   Every drawer now carries `inert` as well as `aria-hidden`, set
   through one helper (`setDrawerHidden`) rather than at each of the
   eight call sites - **the two attributes drifting apart is exactly
   the bug being fixed**, so one place sets both. `inert` is the
   purpose-built answer: it removes the subtree from the tab order AND
   the accessibility tree, where the previous `transform:translateX`
   removed it only from the eye. Support confirmed in the pinned
   Chromium before it was relied on.

   **Tests:** one asserts nothing inside a closed drawer can take
   focus; its sibling asserts an OPEN drawer's controls still can,
   because the cheapest wrong fix here hides everything.

   **A test bug worth recording, since it is this file's own subject.**
   The open-drawer test first clicked `.snapshots-btn`, which is the
   class on every masthead chip - `.first` is "Dark mode", which opens
   no drawer at all. It passed without ever opening one. Now it opens
   the panel by its label and asserts a drawer is open before testing
   anything, which is the same "check the precondition actually held"
   discipline the rest of this pass has needed.

10. **[done, 2026-09-25]** **[Dashboard UI]** **[U3] `plans/dashboard.md`
    #15 confirmed still present, both halves**, checked across four
    distinct views: `document.title` never updates, focus never moves on
    route change, no ARIA live region announces one, and there are **2
    real anchors in the entire rendered page** - so middle-click,
    Ctrl-click and "copy link address" do nothing on breadcrumbs,
    agency cards, dataset rows or column tiles. A confirmation of an
    existing entry rather than a new finding; belongs with #8/#9.

    **THREE OF THE FOUR HALVES FIXED, 2026-09-25.**

    - **`document.title`** now names the view: `Registry Services ·
      Data Asset QA Register`. Read off the view's own `<h2>` rather
      than switched on `STATE.tier` - the heading is already the
      answer, a per-tier lookup would be a second thing to keep in
      step, and a tier added later gets this for free. Status pills are
      stripped, since "Real pipeline data — 42 computed runs" is a
      badge, not the view's name.
    - **A live region** (`#route-announcer`, `aria-live="polite"`)
      announces the same string, so a route change is spoken rather
      than silent.
    - **Focus moves** to the new view's heading - but only on a real
      `navigate()`, NOT on every `render()`. `render()` also runs when
      the as-of date changes, and stealing focus out of the date picker
      mid-adjustment would be its own bug.

    **THE FOURTH HALF IS STILL OPEN AND NEEDS A DECISION: real
    anchors.** Breadcrumbs, agency cards, dataset rows and column tiles
    are `<button>`/`<tr>` with `data-nav`, so middle-click, Ctrl-click
    and "copy link address" still do nothing. Fixing it means every
    navigable thing becomes an `<a href>` carrying the hash route it
    already knows how to build - real work across five render
    functions, and a change to what a click does at every tier, rather
    than a patch. Worth its own conversation.

    **SIGNED OFF 2026-09-25, and stated as a principle rather than a
    fix.** Keith's own words: "yes, there should be links everywhere.
    Everything should be an actual link. Nothing should be a magic
    JavaScript link or magic JavaScript button."

    That is wider than this finding, so it is recorded as the rule it
    is: **anything that navigates is an `<a href>` carrying the route
    it goes to.** Breadcrumbs, agency cards, dataset rows, column
    tiles, check rows. A `<button>` stays a button only where it
    performs an ACTION rather than a navigation - opening a panel,
    toggling the theme, picking a date.

    **What it buys beyond the middle-click:** the browser gets to do
    its own job. Ctrl-click, open-in-new-tab, copy-link-address,
    hover-to-see-the-target, and a real link for anything that scrapes
    or archives the page. It also removes the keyboard question - a
    link is focusable and Enter-able with no `tabindex` and no keydown
    handler, so #8's row fix becomes a simpler thing rather than a
    cleverer one.

    **The thing to get right in the build:** a real `<a href>` is still
    intercepted for the SPA route, and the interception must let the
    browser win when the user asks it to - never `preventDefault` on a
    middle click or a Ctrl/Cmd/Shift click. Intercepting
    unconditionally is how a link becomes a magic JavaScript button
    wearing an `<a>`, which is the thing this decision is against.

    **DONE 2026-09-25, the fourth half.** Breadcrumbs and agency cards
    are `<a href>` carrying the route they go to; dataset rows carry a
    real link on the dataset NAME. One shared `wireNavLinks()` does the
    interception and bails on any modifier, and on any button but the
    primary - so Ctrl-click, middle-click, Cmd-click and Shift-click
    all reach the browser untouched, which is asserted four ways rather
    than assumed.

    **A `<tr>` cannot be an `<a>`**, which is the one place the
    principle needed a judgement rather than a substitution. The link
    sits on the dataset name - what a reader aims at anyway, and what
    "copy link address" should be offered on - and the row stays
    clickable as a convenience. The row handler now bails when the
    click came from inside an anchor, without which a Ctrl-click on the
    name would open a new tab AND navigate this one, which is worse
    than the magic button it replaced.

    **Buttons that ACT are still buttons**, asserted explicitly in both
    suites: the theme toggle, the as-of picker and the panel controls
    are not navigations and did not become links.

    Verified in a real browser as well as jsdom, because the jsdom half
    cannot show that an ordinary click still routes instead of
    reloading the page - which is the way this change could have
    silently cost the SPA.

11. **[done, 2026-09-25]** **[Dashboard UI]** **[U4] A stale column or
    check deep link fails silently** - lands on the dataset page with no
    message, `STATE.columnName` still set to the bad value, and the
    broken segment still in the URL, so re-sharing propagates it.
    `REQ-DASH-055`'s evidence records a not-found state added for agency
    and dataset after exactly this class of bug; it was not extended to
    column or check. At 30 datasets with evolving schemas, stale column
    bookmarks are the common case, not the edge.

    **DONE 2026-09-25.** A dead column or check segment now repairs the
    URL (`replaceState`, so Back still goes where the reader came from
    rather than through the broken link they just arrived on), clears
    it out of `STATE`, and says what happened.

    **NOT a full-page not-found, deliberately**, which is where it
    differs from the agency/dataset case it is modelled on: everything
    the reader asked for except the column resolved, and is worth
    showing. So the dataset page renders and the notice sits above it.

    **A test-harness bug found while writing the tests, and worth its
    own line** because it is the same shape as #43: `_state_to_path()`
    in `tests/test_dashboard_e2e.py` emitted no `/column/` or `/check/`
    segment at all. Any test passing a `columnName` was silently
    driving a plain dataset URL, so the assertion measured the dataset
    page and said nothing whatever about the column. Fixed alongside.

    The must-not-change half - a real column link still opens its
    drawer - is in the Playwright suite rather than the jsdom one, and
    deliberately: that harness carries only a hierarchy, so every
    dataset in it has zero columns and every column name is stale.

12. **[done, 2026-09-24]** **[Dashboard UI]** **[U5] The placeholder
    check is not deep-linkable and Back cannot close its panel.** A real
    keyed check behaves perfectly (URL gains `/check/<key>`, Back closes
    the panel and restores the drawer, Escape does the same and syncs
    the URL - the critic verified all of it). The keyless placeholder
    from #4/#5 opens a panel with no URL change: not shareable, and Back
    skips past it. **Same root cause as #5** - fix the key and this goes
    with it.

    **FIXED as a consequence, 2026-09-25**, exactly as predicted. The
    placeholder now carries a key, so its panel deep-links and Back
    closes it like any other check. A test asserts no check anywhere in
    the embedded data is missing a key, rather than asserting this one
    placeholder has one - the property is "every check is addressable",
    not "we remembered this case".

13. **[done, 2026-09-25]** **[Dashboard UI]** **[U6] The
    exhausted dataset page is a dead end that hides real history.** It
    replaces the ENTIRE dataset page - columns, checks, arrival history,
    trends - with the exhausted message. `cp-case-workers` has 18 real
    committed runs behind that message and no affordance to reach them.
    Also: the two quiet states share one background
    (`rgb(238,234,221)`), differing only in dashed-vs-solid border and
    text colour, so "Schedule ended" and "No data" read the same at a
    glance. The visual critic is looking at that half in both colour
    schemes.

    **DECIDED 2026-09-25**: keep the message prominent, **and show the
    last known results below it**. Keith agreed the lean.

    The reasoning to build against: **"nothing is expected" and
    "nothing ever happened" are different statements**, and replacing
    the whole page conflates them. `cp-case-workers` has 18 real
    committed runs behind that message; a reader who drilled in to see
    the last known state currently gets nothing and no way to ask for
    it. The message stays first and stays loud - this is not a demotion
    of it, it is putting history back underneath it.

    **DONE 2026-09-25.** The early `return` is gone: the message is
    built as a banner and the ORDINARY renderer runs, so the page
    carries its columns, checks, arrival history and trends underneath
    it. The heading keeps the `exhausted` pill, so the page does not
    read as ordinary at a glance, and the banner ends by saying in
    words that what follows is the last known state rather than a
    current reading.

    **A side benefit worth naming:** this path now exercises the same
    renderer as every other dataset instead of being a second, quietly
    diverging one. It had never run `renderDataset()`'s real body at
    all, which is its own latent risk - the first test written here
    asserts it renders with no console error for exactly that reason.

14. **[done, 2026-09-25]** **[Dashboard UI]** **[U7] The asset's own
    timezone is configured, and the page still shows two zones side by
    side.**

    **BUILT by `REQ-DASH-071`, 2026-09-25.** Both halves: the arrival is
    now a real instant on the asset's clock, and the hardcoded `" AWST"`
    is gone from `cadenceLabel()` - it was the last thing on the page
    naming a clock. `expected_time` keeps its written `14:00` form,
    because it is a deadline echoed out of `contract/*.yaml` rather than
    an instant (criterion 8).
 A dataset page reads `SLA: … by 09:00 AWST` next to
    `Latest arrival: 01:00 UTC`, leaving the reader to convert in their
    head to answer "did it meet the deadline". Both strings are
    hardcoded: `cadenceLabel()` writes `"AWST"` literally, and
    `arrivedAt` is `…slice(11,16) + " UTC"`, which takes the wall-clock
    characters and labels them UTC **regardless of the stored offset**.
    Correct today only because every stored value is `+00:00` - and
    making other offsets storable was `REQ-PIPE-048`'s entire point.
    **Same family as #3**; worth fixing together.

15. **[done, 2026-09-25]** **[Dashboard UI]** **[U8] A broken sentence
    in the footer, on every page.**

    **Verified** at template:554: "…not just single-column rules Every
    dataset on this page is real, computed the same way…" - no sentence
    terminator where the mock-data sentence was removed by
    `REQ-DASH-055`, and "computed the same way" now appears three times
    in one paragraph.

    **Cost:** trivial. **Recommendation: fix** - it is visible on every
    page of the dashboard and it is one edit.

    **DONE 2026-09-25.** The missing terminator, and the third
    "computed the same way" went with it - it was the stranded half of
    the removed mock-data sentence, not a clause the paragraph needed.

16. **[done, 2026-09-25]** **[Dashboard UI]** **[U9] The agency page
    overflows horizontally on a phone.** `scrollWidth` 537 against a
    390px viewport, driven by `TABLE.dataset-table` at 539px: "Rows,
    latest run" is clipped mid-word and "Last QA run" / "Trend" are
    entirely off-screen. Before the first dataset row a reader scrolls
    past roughly two screenfuls of chrome. The exec page and the
    exhausted notice both render cleanly at that width.

    **Recorded as reported** - the visual critic has this one in scope
    and may add measurements.

    **CLOSED 2026-09-25 as an ACCEPTED LIMITATION, not a fix.** The
    phone is not a target (Keith's standing decision below), so the
    Tier-2 table's own responsive strategy is deliberately not
    attempted. The cheap half of his instruction IS done: the three
    badge rows and the collection title now carry `flex-wrap`, so a
    status marker wraps instead of being clipped. Desktop width is
    untouched - they wrap only when they would otherwise overflow.

### A standing decision that closes several findings at once

**THE PHONE IS NOT A TARGET. Decided 2026-09-25, Keith's own words:**
"no, it's not critical that it works on the phone. Shave off some of
the rough edges, but I'm happy to accept a substandard experience
there. Everyone will be using it on desktop screens or on laptop
screens."

**What that settles**, so the mobile findings stop being re-raised as
though nobody had looked at them:

- **#16** (the agency page overflowing at 390px), **#52** (the badge
  row as the real widest element, and the collection count marker
  clipped by 10px) and the tap-target half of **#57** are all accepted
  as known, deliberate limitations rather than defects to fix.
- **"Shave off some of the rough edges" is still a real instruction**,
  not a dismissal. The cheap ones that cost nothing at desktop width -
  a `flex-wrap` on the badge row, a `white-space` fix on the
  breadcrumb, not clipping a status marker - are worth doing because
  they are one line each and make the phone view untidy rather than
  broken. What is NOT worth doing is a responsive strategy for the
  Tier-2 table, which is the expensive half.
- **It does not license regressions at desktop width**, and it does not
  touch accessibility: keyboard, focus and screen-reader work
  (#8/#9/#10/#55) was about operability on the machines people
  actually use.

### From `delivery-cli-ux-critic` (2026-09-24)

All of these were verified by this session running the real commands
just now, not by reading the critic's transcript.

17. **[done, 2026-09-24]** **[Testing & dev tooling, Pipeline & publishing]** **[A1] The gate's success line asserts the exact
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

18. **[done, 2026-09-25]** **[Testing & dev tooling]** **[A2] The
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

    **DONE 2026-09-25.** `ConfigError` grew an `affects` tuple - the
    datasets an error actually breaks - filled in by one resolver,
    `_attribute()`, rather than parsed at the point of use. A
    calendar-scoped error fans out to every dataset naming that
    calendar; a dataset-scoped one is itself; an error about the
    asset's own top-level configuration stays empty and keeps its
    existing "the asset's own configuration" wording, which is truer
    than fanning a missing key out to all thirty.

    **What "affected" means, settled:** a dataset is affected when an
    error names it, or when an error names a calendar it uses. The
    renamed-calendar case the critic reproduced now reads "6 error(s)
    affecting 6 dataset(s)" where it read "affecting 1 dataset(s)".

    One place reads a scope string back, deliberately - `scope` is a
    display string this module builds in two shapes, and a single
    resolver owning both readings beats threading a dataset list
    through twenty construction sites where the missed one would
    silently under-count.

19. **[done, 2026-09-24]** **[Testing & dev tooling]** **[A3] Every
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

    **STILL OPEN.** Keith asked on 2026-09-25 whether a pre-commit hook
    would solve this instead. **It does not, and the reason is the
    finding itself:** the harmful path ends in a VALID configuration.
    Point the six datasets at `quarterley` as the text instructs and
    the gate goes GREEN - so running the same validator sooner, or on
    every commit, is still green. A hook changes WHEN you see the
    message, not what it says, and arguably makes the bad instruction
    more likely to be followed, since you are mid-commit and want to
    move on.

    **The hook was worth adding on its own merits and has been**, as a
    separate thing (`mothman-check-schedule` in
    `.pre-commit-config.yaml`, 2026-09-25): the gate is config-only and
    runs in ~1.2s, and finding a calendar mistake at commit rather than
    after a push is a real improvement to the loop. It is deliberately
    documented in that file as NOT covering this item, so a later
    reader does not take it for more than it is.

    **SIGNED OFF AND FIXED, 2026-09-25 - Keith chose option (c)**, both
    halves. The real output now reads:

    ```
    schedule validation FAILED - 6 error(s) affecting 6 dataset(s):

      6 datasets name calendar 'quarterly', which this asset does not
      define. The calendar 'quarterley' is defined and no dataset names
      it - if that is the typo, one edit there fixes them all.

      data-asset.yaml
        dataset 'cp-carers'
          - names calendar 'quarterly', which this asset does not define.
            Use one of: daily, or add that calendar. ...
    ```

    **The cause line** is emitted only when at least two errors share a
    root - a single error is not a shared cause, and a line restating it
    would be noise. `ConfigError` grew a `cause` key and a `cause_hint`,
    so the grouping is structural rather than string-matched on the
    message text.

    **Nothing is suppressed, and Keith's 2026-09-23 rule is intact**:
    all six datasets are still printed individually and the header count
    is unchanged. This adds a line above the detail; it removes none.
    There is a test asserting exactly that, because "add a cause line"
    is one refactor away from becoming the cause suppression he
    rejected.

    **The suggestions now list only calendars a dataset already uses**,
    which is what stops `quarterley` being offered. A calendar nothing
    references is either brand new or a typo, and neither is safe to
    steer a broken dataset at. It falls back to listing everything when
    nothing is referenced at all - a first dataset on a fresh asset -
    since there is then no usage signal and an empty list helps nobody.

    **The typo guess is claimed only when it is safe to claim**: exactly
    one defined calendar unreferenced. Two or more and there is nothing
    to point at, so nothing is said - covered by its own test, which
    points a dataset at a name nobody ever defined and asserts no guess
    appears.

20. **[done, 2026-09-25]** **[Testing & dev tooling]** **[A4/A5] One
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

    **DONE 2026-09-25, both halves.**

    The wording: a `_SHAPES` map gives every key in this schema an
    expected form, and the generated fixes now read "Add it: a list of
    lines saying what changed, like ['2027-01-01: authored 2027
    dates']." rather than "Add it." Where a key is not in the map the
    fallback points at the neighbouring entries rather than saying
    nothing.

    The double-fire: `ConfigError` grew a `field` path and a `layer`
    tag, and one report about one value survives - the SEMANTIC one,
    because it names the unit, gives two examples and says why it is
    never guessed at, where the schema layer's generic message named
    nothing. Tagged explicitly rather than inferred from the message
    text, same reasoning as `cause` in #19.

    Measured on the real config with `claim_window: 14` and a removed
    `changelog`: three errors before, two after, and the header count
    is no longer inflated by the duplicate (which was #18's other
    half).

21. **[done, 2026-09-24]** **[Testing & dev tooling, Pipeline & publishing]** **[A6] The exhausted schedule wears the warning's
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

    **SIGNED OFF AND FIXED, 2026-09-25 - Keith chose option (a)**,
    changing the words now rather than waiting for the filing layer.

    The exhausted line now opens `EXHAUSTED (not failing the build,
    yet):` instead of `WARNING (not failing the build):`, and
    `summary()` no longer describes a calendar with no future dates at
    all as "low on runway" - it says that calendar is `EXHAUSTED`, and
    counts any merely-low ones after it, so the worse fact is never the
    parenthetical. **The promise that nothing is failing the build
    stays**, in both states: a non-fatal warning that starts failing
    builds is one somebody turns off, and then it is not there for the
    one that mattered.

    **Failing tests first**, `tests/test_runway.py::
    TestExhaustedDoesNotWearTheMildStatesWords`, including one that
    pins the unchanged half - today's real config is low, not
    exhausted, and must keep reading exactly as it did.

    **It turned up a fixture that had been quietly wrong.**
    `test_the_summary_counts_calendars_when_more_than_one_is_low` builds
    a second calendar its own comment calls "also nearly out" and gave
    it a single 2023 date - which is EXHAUSTED at that test's own as-of,
    not nearly out. Nothing noticed while both states shared one
    sentence. Extended to 2028 so the fixture matches its comment and
    the assertion is about counting LOW calendars, which is what its
    name says.

22. **[done, 2026-09-25]** **[Testing & dev tooling]** **[A7] The
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

    **DONE 2026-09-25.** `CalendarRunway` now carries
    `driving_dataset`, `driving_last_period` and `driving_last_date` -
    as fields, not only inside the sentence, because the dashboard
    renders its own message and should not parse one back out. The
    warning reads:

    ```
    WARNING (not failing the build): calendar 'quarterly' runs out
    first for 'cp-case-workers', which has only 2 future supply slot(s)
    left - its own last is 2027-Q3 on 2027-08-01. 6 datasets name this
    calendar. The calendar itself runs to 2027-Q4 on 2027-11-01.
    ```

    Every number in it can now be checked against the file. The
    calendar's own horizon is kept as a separate clause, and only when
    it differs from the driving dataset's.

    **One existing rule was refined rather than broken**, and it is
    worth being precise: `test_the_line_says_how_many_datasets_without_
    listing_them` asserted that NO dataset is named. The thing that
    rule exists to prevent is one fact repeated thirty times, not
    naming a dataset - so it is now "name the one the number belongs
    to, and none of the others", asserted exactly that way. The
    minimum is taken with the dataset id as a tie-break, so the same
    configuration always names the same dataset.

23. **[done, 2026-09-25]** **[Testing & dev tooling]** **[A8] The
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

    **DECIDED 2026-09-25: yes, `mothman check` should be able to report
    a warning.** Keith's own call.

    The argument recorded for the build: **a gate that can only shout
    or stay silent gets ignored for shouting.** Today the low-runway
    warning prints, the row reads green `passed`, and the closing line
    says "Every gate passed" - so the only way to make it visible is to
    make it fail, which is precisely what `REQ-PIPE-053` forbids
    ("a non-fatal warning that fails a build gets disabled, and then it
    is not there for the one that mattered").

    **What the build has to settle:** a warning must not change the
    exit code - the fourth outcome is a REPORTING state, not a new
    failure - and every gate needs a way to say "passed, with
    something to know", which today they cannot express through a
    return code alone.

    **DONE 2026-09-25.** `mothman check` has a fourth outcome, "passed,
    with a warning", and the closing line no longer says "Every gate
    passed" over the top of one.

    **How a gate says it, and why not the obvious way.** Reading the
    gate's output for a marker was rejected: `_run` streams rather than
    captures on purpose, and capturing means piping, and a gate whose
    stdout is a pipe stops colouring it. So the channel is an exit
    code - but a gate cannot simply start returning non-zero, because
    CI runs these same commands as their own workflow steps where any
    non-zero exit is a failed step. The runner therefore OPTS THE GATE
    IN through `MOTHMAN_GATE_WARNING_EXIT`, and CI simply does not set
    it. `mothman schedule validate` exits 0 for CI and 78 for
    `mothman check`, from the same code path.

    **The sentinel is interpreted per gate, not globally** - a fourth
    field on `_GATES`. A real failure that happened to exit 78 would
    otherwise be re-read as a warning, turning red into yellow, which
    is the false-green direction.

    **A bug found by driving it rather than reading it:** the first
    build worked at the gate and still rendered red, because
    `cli/schedule.py`'s wrapper turned every non-zero return into the
    same `ClickException`. The warning arrived as a plain exit 1. It
    has its own test now - a wrapper that flattens exit codes reads as
    correct and nothing else in the chain would notice.

    Verified end to end on the real config: `mothman check --only
    schedule` exits 0 and shows the yellow row; `mothman schedule
    validate` exits 0.

24. **[done, 2026-09-25]** **[Testing & dev tooling]** **[B1/B2/B3]
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

    **DONE 2026-09-25.** `--until` is a real `click.DateTime`, so a bad
    date now gets Click's own convention - "Invalid value for
    '--until': 'notadate' does not match the format '%Y-%m-%d'" - like
    every other flag in the tool. `--dataset` and `--calendar` are a
    lazily-resolved choice type, so `--help` lists the real values and
    a wrong one names them all. The two known config errors
    (`UnknownDatasetError`, `ScheduleConfigError`) are wrapped in a
    `ClickException` with the error's own message intact - unwrapped
    from `KeyError`'s repr, which would otherwise print the message
    inside escaped quotes and show the traceback through the thing
    meant to replace it.

    The fourth case, a daily calendar with no `--until`, is gone
    entirely rather than caught: #29's window means the command no
    longer needs the reader to supply a horizon.

    **The choice type resolves LAZILY**, which is the one decision
    worth keeping: the values come from `contract/data-asset.yaml`, and
    reading it at import would make every `mothman --help` depend on
    that file parsing. A gate exists to say whether it does; the help
    should not be the thing that breaks first.

    **`mothman supply` does not exist yet** - when it does, this is the
    shape to copy.

25. **[done, 2026-09-25]** **[Testing & dev tooling]** **[B4] On a
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

    **DONE 2026-09-25.** The report colours its headline, the shared
    cause, each filename, each scope and each error's bullet - with raw
    ANSI and only when `sys.stderr.isatty()`, honouring `NO_COLOR`.
    Rich was deliberately not used: this module also runs bare as a CI
    step, where colour is stripped anyway, and importing a rendering
    library to print eight lines buys a dependency for the case that
    does not need it.

    The closing panel's "see output above" is answered from the other
    end: when there are more than three errors the headline is
    repeated at the FOOT, where the eye already is. Thirty datasets is
    sixty lines, and pointing a reader back past all of them to a line
    they have already scrolled off is the thing that made the panel
    useless.

26. **[done, 2026-09-25]** **[Testing & dev tooling]** **[B5] The
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

    **DONE 2026-09-25** - the flush, keeping the stream split. One
    `sys.stdout.flush()` before the first write to stderr, with a test
    that asserts the ORDER of the two rather than their content, since
    the bug is invisible in this sandbox (which sets
    `PYTHONUNBUFFERED`) and would come straight back otherwise.

27. **[done, 2026-09-25]** **[Testing & dev tooling]** **[B6] The claim
    window renders as a raw `timedelta`.** `cli/schedule.py:71` prints
    `schedule.claim_window(dataset)` directly, giving `14 days, 0:00:00`
    and `4:00:00`. The config is authored `14d` and `4h`, and
    `REQ-PIPE-050` rejects any other form on purpose - "four ways to
    write one duration is four ways for thirty datasets' config to read
    differently". The one surface that displays it invents a fifth.
    `4:00:00` reads as a time of day, in a table whose neighbouring
    columns are literally times (`09:00 +0800`).

    **DONE 2026-09-25.** A new `schedule.format_duration()`, the
    inverse of `parse_duration`, used at both display sites - the
    per-dataset view and the calendar list. It RAISES rather than
    falling back to the timedelta's repr for a duration with no
    authored form, because showing something nobody could type back in
    is the whole problem.

28. **[done, 2026-09-25]** **[Testing & dev tooling]** **[B8/B9]
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

    **DONE 2026-09-25.** The command proposes only the year actually
    next in line, and refuses the other three cases by name: a year
    already authored (naming the duplicate problem and the right year),
    a year in the past, and a year that would skip one - which names
    every year it would leave unauthored, since that is the silent
    hole. It reads the last authored period from the calendar, which it
    could always have done: the runway warning prints it one screen
    earlier.

    `--yaml` emits the version block its own help tells you to copy -
    `effective_from`, a `changelog` line and the dates - printed bare
    so it can be piped, with any weekend notes as a trailing comment
    rather than inside the YAML.

    Two existing tests used years the guard now refuses (2029 skips
    2028; 2026 is authored). Both were rewritten to ask the calendar
    which year is next rather than hard-coding one, so they do not go
    stale the day somebody authors 2028. The weekend RULE stays covered
    where it lives, in `tests/test_schedule.py`, against a year that
    actually has one.

29. **[done, 2026-09-25]** **[Testing & dev tooling]** **[B10] At daily
    cadence there is no way to ask "what's next?"**
    `schedule show --dataset birth-registrations --until 2026-09-24`
    prints **1370 lines** (counted just now), no pager, no `--from`, no
    `--limit`, no marker for today or the next due slot - and for a
    daily calendar `Period` and `Date` are the same string in all 1363
    data rows. The data team leader's actual question - *is my next
    supply due today, and am I past it?* - has no answer short of
    dumping three years. `slots.is_overdue()` and
    `next_unfilled_claimable()` exist in the model with no CLI surface.

    **DECIDED 2026-09-25**: default to a **window** - the last few and
    the next few - with `--all` for the full dump. Keith agreed the
    lean.

    So `--until` stops being required for a daily calendar, which also
    removes the traceback in #24 that a missing `--until` produces. The
    reader's actual question - *is my next supply due, and am I past
    it?* - becomes the default answer rather than something to be
    extracted from 1370 lines.

    **DONE 2026-09-25.** A single dataset shows three periods before
    today and five after, with `->` against the next one actually
    owed, and a footer saying how many were left out and how to see
    them. `--all` is a real escape hatch - there is a test asserting it
    genuinely prints everything, because a default that quietly becomes
    a cap is a worse problem than the one this fixes. `--until` implies
    the full list up to that date.

    For a cadence rule the window also supplies the horizon the
    calendar cannot, which is what removes #24's traceback: the bound
    no longer has to come from the reader.

30. **[done, 2026-09-25]** **[Testing & dev tooling, Docs & process]**
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

    **DONE 2026-09-25.** The requirement id and the siting rationale
    are comments now, which is who they were written for; the help text
    says what the command does. Every command in the group carries
    examples. `--dataset` and `--calendar` enumerate their real values
    in `--help`. `--until` no longer claims to be needed for a daily
    calendar, because it is not any more (#29).

    The footer answers the question a reader actually has: "10
    period(s), 10 slot(s). The calendar has 20; this dataset takes
    delivery in February, August only." The period/slot distinction is
    still shown when a config genuinely exercises it, rather than
    explained when it does not.

31. **[done, 2026-09-24]** **[Testing & dev tooling]** **[B13]
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

    **SIGNED OFF AND DONE, 2026-09-25 - Keith chose option (c)**: one
    corrective rename, now, while there are six command groups and one
    user. His own "renames are how a CLI surface rots" is about
    REPEATED renames; this is the one that stops them.

    **Checked before renaming, and it settled the noun.** Both
    shorthands map one-to-one onto a real collection -
    `bdm` -> `civil-registration`, `cp` -> `child-protection` - verified
    against `hierarchy.all_datasets()` rather than assumed. `bdm` is not
    a dataset shorthand; its collection simply holds one dataset today.
    So the OLDER sites had the wrong noun and `schedule`'s was right all
    along.

    `--collection bdm|cp|all` on `mothman pipeline run` and the five
    `mothman debug run-*`/`build-warehouses` commands. `--dataset` stays
    exactly where it already meant a dataset id: `schedule show` and
    `debug changelog`. **No deprecated alias** - keeping both spellings
    is the fork, not the fix, and `mothman` is this repo's only
    programmatic access point, so every caller is in the tree and was
    updated in the same change (README, `CLAUDE.md`, the CLI tests).
    The short VALUES stay as they are; the noun was the question, and
    each flag's help now names the collection it stands for.

    **Failing tests first**, and deliberately not a list of known call
    sites: `tests/test_cli_app.py::TestOneNounPerThing` walks the whole
    Click tree and asserts no command takes a collection shorthand under
    a flag named `--dataset`, that the shorthands live under exactly one
    flag name, and that `--dataset` still exists where it really means a
    dataset. A future command cannot reintroduce the fork somewhere
    nobody thought to look.

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

33. **[done, 2026-09-25]** **[Docs & process]** **`REQ-PIPE-053` is
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

    **Keith, 2026-09-25: "I'm open to that. Give me a proposal."** The
    proposal is summarised here so it does not live only in a chat log:
    add an optional `unmet_criteria:` list to a requirement - each
    entry naming the criterion, why it is unmet and who owns it next -
    rather than adding a third status.

    **SIGNED OFF AND BUILT 2026-09-25** ("ship it").

    **Why a field and not a third status**, recorded because it is the
    part a future session would otherwise re-litigate: `status` is what
    the register is indexed and filtered by, so a third value would
    make every consumer of it decide what "partly built" means - and
    the honest answer for the requirement that prompted this is that it
    IS built and has a hole in it. A hole is a property of the record,
    not a different kind of record.

    **All three sub-fields are required**, which is the point rather
    than strictness: "some criteria are unmet" is exactly what the
    prose already said, and a record that cannot name WHICH, WHY and
    WHO NEXT is the same sentence in a different place. `owner` is free
    text because the next owner is as often a sprint or a finding as a
    person.

    **It cannot appear on a `not_started` requirement** - nothing is
    built, so nothing is unmet, and allowing it would make the field
    mean two different things.

    **Applied to `REQ-PIPE-053`**, which now carries its six
    filing-layer criteria as structured records rather than as a
    `decisions:` note: the four dashboard criteria (#2) are genuinely
    met as of today, so what remains is the staging work that honestly
    belongs to batch 3, sprint 8. Criterion 9 is #7, which resolves the
    same way.

    **And it reaches a reader**, which was the actual complaint - the
    requirements panel renders the block above `decisions:` and the
    evidence, because "this is not all there" changes how everything
    below it should be read.

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

34. **[done, 2026-09-25]** **[Pipeline & publishing]** **[A3] Month
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

    **DONE 2026-09-25, and not with a `.lower()`.** The gate's
    `_month_number()` now DELEGATES to `schedule.parse_month_name()`
    rather than mirroring its reading, so there is one implementation
    of the rule instead of two that agree until they do not. A gate's
    job is to refuse what the runtime cannot read, which is only true
    if it asks the runtime.

    The parity test the finding asked for, holding the two to each
    other across twelve spellings rather than each to its own
    expectation, plus the end-to-end case (`february` is month 2, not
    "not a month") and the must-not-change half (`Febuary` and `Feb`
    are still refused - case-insensitive is not lenient). Confirmed
    failing first.

35. **[done, 2026-09-25]** **[Pipeline & publishing]** **[A4] Two
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

    **First residue FIXED 2026-09-25**, as part of #44's cheap
    hardening - Keith folded the two together ("happy for you to put it
    in item 44 and then address it there"), same guard, one fix. The
    boundary now reads `asset_time.local_date(asset_time.now())`, with
    a regression test that can only pass on the asset's clock. The
    SECOND residue - `assetTodayDateStr()`'s silent UTC fallback in the
    browser - is still open and still Keith's, for the reason recorded
    above: it is the "how loudly should a browser fail" question, not a
    one-line fix.

    **SPLIT 2026-09-25, at Keith's direction.** The guard's
    `date.today()` half moves to **#44**, which is the same guard and
    the same conversation - "sure, happy for you to put it in 44 and
    then address it there".

    **THE DASHBOARD HALF IS BUILT, 2026-09-25**, as `REQ-DASH-071`
    criterion 14 - Keith's own answer to the "how loudly should a
    browser fail" question below was "I think I should just probably
    fail quite loudly. No need for a graceful fallback." Absent or
    unresolvable now throws, naming the zone, and both ends are
    asserted. That closes this entry.

    **What stayed here was the dashboard half**: `assetTodayDateStr()`
    falling back silently to UTC when `ASSET_TIMEZONE` is null or the
    zone name does not resolve. Still open, still mine, and still the
    smaller of the two.

36. **[in-progress, 2026-09-25]** **[QA checks & contract, Pipeline & publishing]** **[A5] Hierarchy identifiers are still restated inline
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

    **ONE OF THE TWO STRUCTURAL NEIGHBOURS IS DONE, 2026-09-25.**
    `validate_hierarchy.py`'s hand-maintained `CONTRACTS` tuple is now a
    derived `contracts()`: every dataset already declares its own
    `contract:`, and which one a file describes falls out of how many
    datasets name it - shared by several means their collection, named
    by exactly one means that dataset.

    **The failure mode it removes was silent**, which is what made it
    worth doing rather than tidy: a third collection meant editing two
    places, and forgetting the second one meant the new contract simply
    never got checked - by the gate whose whole job is noticing that a
    contract and the tree disagree.

    **The comment it replaces is not overruled.** That said the list was
    written out rather than "inferred from the filename, because a
    filename is not a declaration". True, and unchanged: nothing reads a
    filename to decide anything. It reads the hierarchy's own
    declarations, which is the opposite of assuming.

    **It also gained coverage the hand-written list never had**: a
    contract file no dataset names is now reported. Deriving could have
    lost that case - except it was never checked before either, because
    nobody had added such a file to the tuple.

    **THE EVIDENCE LINE IS CORRECTED, 2026-09-25, Keith's own yes.** It
    claimed "the count is now zero"; the assertion is gone, and a
    second entry records WHY it was wrong rather than quietly amending
    it - an overstated evidence line is exactly what a future session
    trusts instead of re-checking, which is the same failure
    `CLAUDE.md` records about a fabricated test count.

    **`REQ-QAC-039` now carries criterion 1 in `unmet_criteria:`** (the
    field built for this, #33), owned by this finding. The register no
    longer says the criterion is met.

    **STILL OPEN:** the 17 literals themselves, and
    `qa_tools/bdm/evidently_check_lifecycle.py`'s literal check_id
    string - left alone because the literals are the substance of the
    criterion and moving one of them is not the fix.

    **SURVEY, 2026-10-06 (Keith's queue, "survey first").** The count
    has grown, not shrunk: **~70 inline literals across 23 files**
    (`grep` for every collection, agency and dataset id in `qa_tools/`,
    `pipeline/`, `cli/`, `generator/`, `dashboard/`, `aws/`, excluding
    `hierarchy.py` and comments). They fall into five kinds, and only
    two of them are the defect the criterion names:

    1. **A COLLECTION REGISTRY, STATED FOUR TIMES - the real defect.**
       `processing_pass.COLLECTIONS`, `recheck._ORCHESTRATORS`, and
       `cli/supply.py`'s `_SHORT_COLLECTION` and its `known` map each
       say, per collection: its orchestrator module, its warehouse
       builder, its run-id prefix (`run_`/`cp_run_`) and its short CLI
       name (`bdm`/`cp`). `github_links.AGENCY_QA_FOLDER` says the
       short name a fifth time, keyed by agency. A third collection
       means editing five places, and forgetting one is silent in the
       same way the old `CONTRACTS` tuple was. None of this is in the
       hierarchy, and arguably should not be - a module path is code
       layout, which is `AGENCY_QA_FOLDER`'s own stated reason.
    2. **Per-collection code re-spelling its OWN collection** - ~35 of
       the ~70. `qa_tools/bdm/*`, `cli/bdm.py`, `cli/cp.py`, the
       `arrivals_for("civil-registration", "run_")` calls, and
       `pipeline/build_dashboard_data.py`'s 14 `"birth-registrations"`.
       Each module is about one collection by construction; the fault
       is that it spells it rather than importing the one constant its
       package already has (`bdm_common`/`cp_common`), and
       `build_per_run_warehouses.DATASET_ID` and
       `generate_runs.DATASET_ID` are second and third copies of
       `bdm_common.DATASET_ID`.
    3. **The Evidently check ids** - the whole tree spelled into two
       constants. Derivable from the hierarchy plus a suffix.
    4. **Scenario definitions** - `generator/scenario_injection.py`'s
       six `dataset_id=` values. These are scenario CONFIGURATION, the
       same kind of thing REQ-GEN-045's map is, and naming a dataset is
       what a scenario is for. Not a defect if validated against the
       hierarchy.
    5. **Comments** that use an id as an example. Not code.

    **The forks, for Keith before building** (asked 2026-10-06): where
    the one collection registry (kind 1) lives, and whether kind 2 is
    satisfied by "one constant per collection package, imported
    everywhere" or needs every per-collection module to resolve through
    `hierarchy.py` at runtime.

    **KEITH'S ANSWERS SO FAR, 2026-10-06 - HELD, "talk it through
    first".**
    - **Registry: SPLIT, config plus code.** Each collection's short name
      (`bdm`/`cp`) and run-id prefix become collection attributes in
      `contract/data-asset.yaml`. Module paths go in ONE Python registry,
      checked against the config.
    - **Own-id: his question back was "why can't they read that from the
      data?"** The answer given: mostly they can. Records carry their
      collection and dataset, and a builder can iterate
      `hierarchy.datasets_in_collection()` rather than naming its
      dataset. The one fact a module cannot read from data is which
      collection IT is, because `mothman bdm qa` runs before any record
      exists. Proposed anchor: the package's own folder name
      (`qa_tools/bdm` -> `bdm`) looked up against the config's `short:`,
      so no id is spelled in code at all. A gate fails if a folder and the
      config disagree in either direction, and a test refuses a new
      inline id.
    - The alternative put to him and not chosen yet: fold the
      per-collection packages into one generic orchestrator, so there is
      no `bdm`/`cp` folder to anchor. That is
      `plans/publishing-and-history.md` item 6's code-architecture
      question and a much bigger piece, to be scoped separately if
      wanted.

    Nothing is built until he has talked it through.

    **KEITH, 2026-10-06 13:47, deferring it deliberately:** "why can't they
    read that information in the data asset YAML file?" - and the thing he
    wants to talk through is the larger aim behind it: **everything in
    configuration and no custom code per dataset, if we can.** Parked to be
    discussed alongside the calendar group (plans/wider.md #11, item 9), not
    before. `plans/running-thoughts.md` #68 carries the aim itself.

37. **[done, 2026-09-24]** **[Data generation]** **[A6/B3] Three
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

    **SIGNED OFF AND DONE, 2026-09-25 - Keith chose option (b)**: keep
    the capability library-only until the staging overlay lands, and
    fix the register rather than the code. A `mothman` flag would create
    a way to write a partial CP delivery into `data/deliveries/` that
    today's warehouse builder crashes on, which is exactly what the
    off-by-default guards against.

    **A correction to the critic, found while doing it.** It reported
    criteria 1, 4 and 5 as sharing the defect. **Only 1 and 2 did.**
    Criteria 3, 4 and 5 already say "SHALL be able to" and are met by
    the library capability. The reachability finding is real for all of
    them; the PHRASING finding applied to two criteria, not four - the
    fifth such correction in this pass.

    So criteria 1 and 2 were reworded from "SHALL generate" to "SHALL be
    able to generate", **matching the shape criteria 3, 4 and 5 already
    used** - which makes the requirement internally consistent rather
    than inventing an escape hatch for it.

    **The original wording is quoted verbatim in `REQ-GEN-040`'s own
    `decisions:`, on purpose.** Rewording a signed criterion is exactly
    how a gap gets made to disappear, and this one has not: the
    capability is still unreachable by any operator, that is still
    recorded, and Keith still chose to defer it. What changed is the
    register's CLAIM, not the scope - and a reader who suspects
    otherwise can see both versions without going to git.

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

    **RE-SCOPED 2026-10-06 (delivery-scoper) AND ANSWERED (Keith).** The stop
    this entry warned about was settled differently: REQ-PIPE-131 c16 holds a
    post-schedule supply rather than failing the dataset. Scoper also found
    the hold's reason claims a next period opened (an exhausted calendar has
    none), and `runway.exhausted_datasets` fires about a period before the
    last slot closes. Keith's answers: (1) the hold IS the hard failure -
    staged, checked, held, labelled schedule-ended with an honest reason and
    the fix; (2) once dates are added, held supplies are RE-FILED
    AUTOMATICALLY by the next pass in receipt order; (3) the dashboard says
    exhausted when the last slot CLOSES, agreeing with the pipeline. Retention
    of held supplies was not asked. Drafts (REQ-PIPE-154, REQ-DASH-155, and
    053 c4-6 restated) are to be revised for (2) and (3) and brought for
    sign-off.

    **A WRONG PREMISE WENT TO KEITH, AND WAS CAUGHT BUILDING, 2026-10-06.**
    The scoper reported that a held supply "is still staged and checked,
    because arrival_lifecycle.process always runs the checks", and Keith
    signed REQ-PIPE-154 criterion 5 on that. It is false: a held supply's
    view is withheld (REQ-PIPE-078 criterion 9), so it gets its file checks
    and no data checks - all 9 holds in the sandbox read 6 and 0. Caught
    when the criterion was about to be marked met against
    `tests/test_held_not_checked.py`, which says the opposite. Told him; he
    kept today's behaviour and c5 is amended. The lesson is CLAUDE.md's own:
    a critic's or scoper's claim about the code is a claim to verify against
    the code BEFORE it goes to Keith, not after he has signed it.

39. **[done, 2026-09-25]** **[Pipeline & publishing]** **[B1/B2] Three
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

40. **[done, 2026-09-25]** **[Data generation, Pipeline & publishing]**
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

    **RECONCILED 2026-09-25, Keith's own yes**, by narrowing 040 rather
    than loosening 043. Criterion 6 was "SHALL NOT decide, record or
    emit which slot a generated supply fills"; it now forbids EMITTING
    one inside any delivery, and forbids the pipeline reading one from
    the generator's bookkeeping, while leaving the generator free to
    record what it knows.

    **That is the rule the firewall actually enforces**, and stating it
    that way is what makes `tests/test_arrivals.py`'s static check the
    guard for a written criterion rather than for an unwritten
    convention: the concern was never that the generator knows which
    slot it built for - it must, to build a realistic supply - but that
    a filing decision could be made from a declaration rather than
    from arrival plus slot state.

41. **[done, 2026-09-25]** **[Pipeline & publishing]** **[D2]
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

    **SIGNED OFF 2026-09-25** - "yep, we should definitely raise on
    unknown collection id."

    **DONE 2026-09-25.** `arrivals_for()` now calls
    `hierarchy.datasets_in_collection(collection_id)` first, which
    already raised the right error naming the real collections - the
    function simply never asked it. Three tests, the first two
    confirmed failing first: a renamed collection raises, the error
    names what does exist, and the must-not-change half - a real
    collection with nothing delivered yet still answers `[]`, because
    empty is an ordinary state and only an undefined id is not.

42. **[done, 2026-09-25]** **[Pipeline & publishing]** **[B6] The claim
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

    **ANSWERED 2026-09-25 - Keith asked whether `REQ-PIPE-051` fixes
    this once built, or whether Thread E already has a solution.**

    **051 is already built, and it does not fix this - deliberately.**
    Its criterion 5 says the system "SHALL NOT attach a due instant, a
    grace allowance or a CLAIM WINDOW to a period". Scoping the claim
    window out of periods is correct: it belongs to the slot, not the
    period. So this is not an oversight in 051, it is a boundary 051
    drew on purpose.

    **But 051 states the principle this needs, in its own criterion 9**
    - "SHALL evaluate each period against the version of its own
    calendar in force on that period's own date" - and BUILT the
    mechanism, `_effect_windows()`. `periods_for_calendar()`'s own
    docstring describes an identical bug it already fixed for dates:
    reading `calendar.current` for the whole sequence, so adding a 2027
    version did not move the earlier periods, it REPLACED them, and
    four years of history ceased to exist.

    **`claim_window()` is that same bug in the layer 051 handed to
    052.** `REQ-PIPE-052` criterion 10 says a slot takes its claim
    window "from its dataset's own contract where one is declared and
    from its calendar's default otherwise" - and is silent on WHICH
    VERSION. Today's code satisfies it by reading `.current`, so the
    criterion is not broken, it is underspecified.

    **Thread E does not solve it either - it RAISES THE STAKES.** Its
    settled assignment rule is "assign to the oldest slot whose CLAIM
    WINDOW is open and which is unfilled", so the claim window is not a
    display detail, it is the input to slot assignment. A claim window
    that moves retroactively means re-deriving a past assignment can
    give a different answer than the one history was filed under - the
    cascading misassignment Thread E exists to prevent, arriving
    through configuration rather than through the rule.

    **So: no existing requirement fixes it, the mechanism is already
    built, and the fix is to apply `_effect_windows()` to the claim
    window as well as to the dates** - plus tightening 052's criterion
    10 to name the version, which touches `requirements.yaml`'s own
    claims and so is Keith's.

    **CRITERION 10 AMENDED 2026-09-25, Keith's own yes.** It read
    "from its calendar's default otherwise" and now reads "from the
    version of its calendar in force on that period's own date
    otherwise". The code already did this; the criterion was
    underspecified rather than wrong, which is the worse shape - it
    was satisfied by the buggy reading and by the correct one alike.

    **DONE 2026-09-25** (the code half; the criterion-10 wording is
    still Keith's and is listed with the other register items).
    `schedule.claim_window()` takes an optional `on:` date and resolves
    the default through a new `_version_in_force()`, built on
    `_effect_windows()` - the same mechanism the dates already use.
    `slots_for_dataset()` now asks per period, on that period's own
    date, instead of hoisting one value out of the loop.

    Two decisions worth keeping. **The contract override stays
    unversioned**: it is declared in the dataset's own ODCS contract,
    which has no `effective_from` and no version sequence, so there is
    no date at which one of its values was in force rather than
    another - only the calendar default can move under history.
    **A date before the first version's `effective_from` takes that
    first version** rather than raising, which is what
    `periods_for_calendar` already does implicitly by never generating
    such a period; raising would turn "this calendar was authored later
    than its own earliest data" into an error nobody can act on.

    Three tests, the first confirmed failing first against a real
    two-version calendar whose versions differ in claim window rather
    than in dates: the 2024 slot opened seven days before its due
    instant instead of fourteen, taking the 2027 version's value. The
    other two are the halves that must not change - a current slot
    still takes the current version, and a contract override still wins
    at every date.

43. **[done, 2026-09-24]** **[Testing & dev tooling]** **[C1/C3/C4] Two
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

    **SIGNED OFF AND FIXED, 2026-09-25, all three halves.**

    **The e2e fixture.** `TestAnExhaustedScheduleIsLoud::
    test_the_page_still_has_zero_console_errors` now takes `clean_page`
    instead of `page`. One word, and it is the one that would have
    caught #5 months earlier.

    **The render gate.** `check_dashboard_renders.py` now visits every
    agency and dataset route, enumerated from the page's own `DATA` and
    built with the page's own `stateToHash()` - so a dataset added
    later is covered without anybody remembering, and the gate can
    never visit a route the app would not build.

    **PROVEN BLIND FIRST, AND PROVEN SIGHTED AFTER.** The bug was
    reintroduced into a built copy (11 keys stripped) and the old gate
    still reported "zero console errors"; with the extension it names
    the three affected datasets and fails. Both directions checked,
    because a gate that passes everything and a gate that works look
    identical from one run.

    **Two no-ops were found doing it, and they are the point.** The
    first version assigned `window.location.hash` - the app listens for
    `popstate`, which a programmatic hash assignment does not fire, so
    it "visited" nine routes without re-rendering once. The second
    tested `window.DATA` - a top-level `const` creates a global
    BINDING but not a window property, so it enumerated zero routes.
    **Both reported success.** Neither would have been caught by
    anything except re-proving against the reintroduced bug, which is
    the same a-check-that-never-runs-looks-like-success shape the gate
    was being extended to close, hit twice in twenty minutes while
    closing it.

    **Criterion 1's own test.** `TestTheGateActuallyFailsTheBuild`
    asserts `main()` returns 1 on a broken configuration and 0 on the
    real one. Not a defect - it always did - but every other test in
    that module asserts `validate()` returns a non-empty list, which is
    a different claim from the gate failing. A validator whose exit
    code nobody checks is one CI can stop honouring with no test
    noticing.

    **`_report()` itself is now covered** by #19's own tests, which
    drive `main()` and read its real stderr - criteria 19, 21 and 22
    went from untested to asserted as a side effect of that work.

    **Recommendation: fix all three**, and take the cheap one first -
    switching that one e2e test to `clean_page` is a one-word change
    that would have caught #5.

44. **[done, 2026-09-25]** **[Pipeline & publishing]** **[D3] The
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

    **Keith, 2026-09-25: "that's a pretty weak guard there, we can't
    really rely on that. What are the options?"** Three, in the reply
    of the same date and summarised here:

    - **(a) Widen the diff.** Check the whole push range rather than
      `HEAD~1`, and stop letting any changelog edit clear the finding.
      Cheapest; still depends on how CI happens to be checked out.
    - **(b) Compare against the base branch** so the unit is the whole
      change rather than one commit. Catches a date moved and
      "un-moved" across commits.
    - **(c) Seal elapsed versions.** Commit a fingerprint of each
      calendar version's authored dates once its window has elapsed;
      the gate compares the file against the seal and never reads git
      history at all. Works at any fetch depth, in any push shape, on
      any checkout.

    **#35 IS FOLDED IN HERE**, at Keith's own direction the same day -
    the guard's `date.today()` reads the RUNNER's clock, so for about a
    third of each Perth day it classifies a date on the wrong side of
    "today". Same guard, same conversation, one fix.

    **ANSWERED 2026-09-25, and the answer escalates this.** Keith asked
    the right question - "don't we have a solid way for people to not
    be able to retroactively change CHECKS? Why don't we just apply
    that?" - and the honest answer is **no, we do not. It is the same
    mechanism with the same hole.**

    `qa_tools/common/validate_check_lifecycle.py` compares the working
    tree against `collect_checks("HEAD~1")`. One job in
    `deploy-pages.yml` runs both gates at `fetch-depth: 2`, and that
    workflow's own comment says so: "Needs HEAD~1 for its past-date
    guard - the same fetch-depth: 2 this job already sets for the
    check-lifecycle diff below". So a push of two or more commits is
    only ever checked on its last one, **for the 257 hand-authored
    checks as much as for the calendars.** Change a check's threshold
    in commit A, land commit B on top, and the gate protecting Thread
    D never sees it.

    **So this is not a schedule finding. It is a finding about the one
    mechanism both gates share**, and it is worse where it was not
    being looked at: the check gate is what stands between a quietly
    edited threshold and a QA history that no longer means what it
    said.

    **The RULES should stay different, though, and that is worth being
    precise about** - applying the check gate's contract wholesale to
    calendars would be weaker than what calendars need:

    - **A check's config changing is LEGITIMATE.** The rule is "say
      what you did", so a changelog entry is the right escape hatch and
      the gate is a documentation gate.
    - **A past calendar date moving is NOT legitimate**, at any level
      of documentation. It changes what already-filed history was
      judged against - a supply that was late becomes on time. A
      changelog entry does not make that acceptable, so the escape
      hatch that clears the finding on ANY changelog difference is
      wrong twice over: too loose, and conceptually the wrong shape.

    **Which points at option (c) for both.** Sealing - a committed
    fingerprint of what has already elapsed - fixes the shared hole
    without depending on fetch depth, push shape or checkout, and it
    lets each gate keep its own rule about what a seal MEANS: for
    checks, "changed, and here is the changelog entry"; for past dates,
    "cannot change".

    **Still Keith's call**, since it is now a bigger change than the
    schedule guard alone. Recorded here because the discovery belongs
    with the finding that prompted it.

    **AND THE SEAL FOR CHECKS ALREADY EXISTS** - found 2026-09-25 while
    working out what option (c) would actually look like, and it
    changes the shape of the answer.

    Every committed `qa_results/*/verified[]` record already carries
    `check_id`, `warn_threshold`, `fail_threshold`, `on_fail_action`,
    `dimension` and `label` - what each check WAS at the moment it was
    used to judge real data. Measured: **257 check_ids across 60
    committed runs, and not one has ever had more than one threshold
    pair.** So the baseline exists, is committed, is years-deep, and
    agrees with today's configuration everywhere.

    That means the checks half of option (c) is not a new artefact at
    all - it is changing the baseline from `HEAD~1` to committed QA
    history. It also asks a strictly better question: not "did this
    change since the previous commit" but **"did this change since it
    was last used to judge data"**, which is the thing that actually
    must not move quietly.

    **CORRECTION, 2026-09-25, found while building it: the seal in
    committed history is NOT the thing this gate compares.**

    `find_undocumented_changes()` compares `config_hash` - a SHA-256 of
    a check's WHOLE config dict from its definition file. The committed
    `verified` records carry the RESOLVED thresholds and nothing else;
    `config_hash` appears nowhere in `qa_results/` (grepped, zero
    hits).

    **The gap is not cosmetic, and one example settles it.** Changing a
    dbt `accepted_values` list from `[M, F, X]` to `[M, F, X, U]`
    changes the config hash and changes NO threshold. Comparing on the
    projection history carries would miss exactly the class of change
    that matters most - what a check actually tests - while catching
    only the thresholds. So "compare on what history already has" is
    not a weaker version of the gate, it is a different and worse one.

    **What I told Keith was right about thresholds and wrong about the
    comparison**, and the difference is load-bearing, so it is recorded
    here rather than quietly worked around.

    **The obvious repair is the wrong shape, and its own numbers say
    so.** Writing `config_hash` into each verified record costs ~35
    bytes x 257 checks = **8.8 KB per run**, 2.9% of a measured 300 KB
    run - which is **63 MB a year, 313 MB over five**, at the 20
    datasets-daily figure Keith gave the same day. That is a lot of
    repetition for a value that changes perhaps once a year per check,
    and it walks directly INTO the problem
    `plans/running-thoughts.md` #44 was opened to walk out of.

    **An append-only record of check-config changes is the same
    artefact as the seal, and costs ~30 KB a YEAR in total.** It is
    what the gate wants to read, it is what makes the history
    immutable, and it is what #44 already names as a thread to pull.
    Building a per-run hash now would be building the throwaway version
    of it.

    **So the recommendation changed while building**, and it is Keith's
    to take or leave:
    - **Now:** the cheap hardening only - widen `HEAD~1` to the whole
      push range, drop the changelog escape hatch, fix the runner clock
      (#35). Closes the multi-commit hole in both gates, adds no bytes.
    - **Then:** the real seal arrives as part of #44's redesign, where
      it is a few KB rather than a few hundred MB.

    **The calendars half has no such record, and building one now may
    be throwaway.** Nothing committed carries a period's date, a due
    instant or a claim window - `dataset_stats.json`'s arrival record
    is `run_id`/`run_index`/`received_at`/`delivery` and nothing more,
    deliberately (`REQ-GEN-043` criterion 7). Once sprint 8/9 files
    supplies against slots, the filing record will carry the due
    instant and claim window each was judged under, and the calendar
    seal becomes the same shape as the check one for free.

    **Cost:** small to document, larger to close. **Recommendation:**
    decide which, and write down whichever is chosen - an
    under-documented guard is one a future session will trust further
    than it goes.

    **DONE 2026-09-25 - the cheap hardening, on Keith's own call ("yep,
    do the cheap hardening now and leave the seal for 44").** Three
    changes, no new bytes in `qa_results/`:

    - **`qa_tools/common/diff_base.py`**, new: one function answering
      "which commit do the immutability gates compare against". CI sets
      `MOTHMAN_DIFF_BASE` to `github.event.before` - the commit the
      PUSH started from - and `deploy-pages.yml` now checks out at
      `fetch-depth: 0` rather than 2. Every commit in a push is read,
      for the calendars and for every hand-authored check alike. It
      falls back to `HEAD~1` when the ref is unset or unreachable,
      because a branch's first push reports an all-zeros before-SHA and
      a shallow checkout cannot reach past its depth - neither is a
      finding, and neither should take a gate down. Its own module
      because BOTH gates need it and neither should own it; they had
      already drifted into two spellings of one decision.
    - **The changelog escape now needs a LONGER changelog**, not a
      different one. Rewording an existing entry - or deleting one -
      used to license moving a past date. Same rule the sibling check
      gate's `find_undocumented_changes()` has always had.
    - **The past/future boundary reads the ASSET's clock** (#35's first
      residue, folded in here as agreed). It was `date.today()`, the
      runner's, and the two are different calendar dates for about a
      third of every day - on a function whose whole job is deciding
      whether a date is in the past.

    **Tests, all confirmed failing against the real pre-fix code
    first** - `TestTheGuardIsNotAsNarrowAsItLooked` (the changelog
    escape, the asset clock, plus the must-not-change half: a
    genuinely new entry still clears the finding) and `TestTheDiffBase`
    (the fallbacks, plus two that assert the WIRING - the defect was
    that each gate named its own ref, so a test of `diff_base()` alone
    would not have caught it). The clock test is built so it can only
    pass on an asset-clock reading: it moves a date that is past in
    Perth and future anywhere UTC-ish.

    **One of those tests would itself have gone red in CI**, caught
    before pushing and recorded because it is the same shape CLAUDE.md
    already names: it set the configured ref to `HEAD~2`, which
    resolves in a full local clone and not under `actions/checkout@v4`,
    whose default fetch-depth is 1. Reproduced with a real `git clone
    --depth 1` rather than reasoned about, fixed by asserting on `HEAD`
    - which resolves at any depth and proves the same thing - and the
    whole file re-run inside that shallow clone to confirm it.

    **What is deliberately NOT closed:** the seal itself. Sealing what
    has elapsed needs no git history at all and is the right answer,
    but the obvious build of it costs ~63 MB a year in repeated hashes
    and the elegant build is the same artefact `plans/running-thoughts.md`
    #44 exists to design. This closes the multi-commit hole today; that
    item owns the rest.

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

48. **[done, 2026-09-25]** **[Dashboard UI]** **[V2] Hovering a dataset
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

    **DONE 2026-09-25**, scoped to hover and to `--surface` rather than
    a new darker token. That restores the pill to exactly the contrast
    it has UNHOVERED (1.20:1) rather than making the quiet state
    louder, which is what Keith declined in #49 - and it RAISES the
    label's own contrast as a side effect (2.81 -> 3.39 light, 4.62 ->
    5.05 dark) without touching `--ink-faint`, the token he declined to
    change.

    **A darker fill was tried first and backed out**, because measuring
    it showed it dropped the label to 2.76 - making worse the very
    number he agreed to take a hit on, which is not the same as taking
    the hit.

    **The first test passed for the wrong reason** and is worth
    recording: it hovered a real row and compared the row's background
    with its own pill's, and at the as-of it chose that pill was GREEN.
    It measured a state that was never in question. It now hovers a row
    for the real hovered colour and compares it against what
    `.pill.nodata` and `.pill.inactive` actually paint, so it measures
    the RULES rather than whichever pill a row happens to show.

49. **[done, 2026-09-25]** **[Dashboard UI]** **[V3/V5] The `nodata`
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

    **DECIDED 2026-09-25: NOT FIXING the text contrast.** Keith's own
    words: "let's not fix that, I'm happy to take the hit to
    accessibility." The border half was fixed on 2026-09-24 and stays
    fixed, so what is declined is specifically raising `--ink-faint` -
    the `nodata` label at 2.81:1 light / 3.55:1 dark, and the footer at
    3.03:1 / 4.16:1 (#54), against a 4.5:1 bar.

    **One factual point was put to him once and is recorded rather than
    re-argued**, because it is a fact about the destination rather than
    an opinion about the design: Australian government digital services
    are generally held to WCAG 2.1 AA, so if this PoC becomes something
    an agency publishes, this stops being a taste question and becomes
    a compliance one. He has that and it is his call.

    **Recorded as deliberate debt, not as an open finding**, so nobody
    re-raises it as though it were new. What it does NOT touch: the
    keyboard and focus work (#8/#9/#10/#55) was operability rather than
    contrast, and is unaffected.

50. **[done, 2026-09-25]** **[Dashboard UI]** **[V4] `1.5px` borders
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

    **DONE 2026-09-25** - 2px, which is a width every display actually
    has. The test measures computed `borderTopWidth` on probe elements
    rather than reading the declaration, for the reason this finding
    exists.

51. **[done, 2026-09-25]** **[Dashboard UI]** **[V8/V9] `REQ-PIPE-048`'s
    stored offsets reach two render sites, and neither handles them.**

    **BUILT by `REQ-DASH-071`, 2026-09-25.** Keith took the first of the
    three options below - one formatter, every user-facing instant on the
    asset's clock, its own requirement. Both sites now call it, the stale
    comment is rewritten, and a real-browser test walks all seven dataset
    pages looking for exactly the raw shape this entry counted 43 of.

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

52. **[done, 2026-09-25]** **[Dashboard UI]** **[V6/V7] The mobile
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

    **CLOSED 2026-09-25, the cheap half only.** `flex-wrap:wrap` is on
    `.collection-title` and on the three badge rows this entry measured,
    which is one line each and is what stops the marker being clipped.
    The badge row's own 336px owner pill still wraps rather than
    shrinking, and that is accepted - the phone is not a target, and
    "untidy" was the bar Keith set for it.

53. **[parked, 2026-09-25]** **[Dashboard UI]** **[V11/V12/V13] The two
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

    **MOSTLY DONE 2026-09-25**, and two of the three fell out of #13's
    fix rather than needing their own:

    - **The status pill is back where readers expect it.** The
      exhausted branch now runs the ordinary renderer (#13), which puts
      the pill in the right-hand cluster every other dataset page uses.
      The first draft of that fix ADDED a second pill inline in the
      `<h2>` - exactly the shape this finding complains about - caught
      by counting pills on the real page. The no-data branch got the
      same treatment by hand.
    - **Both quiet states are bordered notices now**, sharing one
      shape, one measure and one set of `<code>` chips. That chip rule
      was scoped to `.notice-exhausted` alone, so the SAME two strings
      got a chip at Tier 1 and the browser's default `monospace` at
      Tier 3. It now covers every notice and uses the page's own IBM
      Plex Mono with tabular numerals.

    **PARKED 2026-09-25, Keith's own call ("park it").** The
    `colspan="4"` headers stay as they are: at a quiet as-of, four
    Tier-2 column headers hang over nothing - 49% of the table at 1440
    - and the message starts under `LATEST ARRIVAL`, so it reads as a
    value in that column. Collapsing the header set when every row in a
    collection is quiet is a real conditional-table change rather than
    a CSS fix, and it was not worth the work today. Recorded as
    deliberate debt rather than left as an open finding, so nobody
    re-raises it as though it were new.

54. **[in-progress, 2026-09-24]** **[Dashboard UI]** **[V10/V14/V15] Layout
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

    **THE TWO MEASURES ARE DONE 2026-09-25** - the exec notice is capped
    at 80ch and the footer at 90ch, against the 146 and 162 characters
    per line the critic measured. MEASURE ONLY: the footer's contrast
    is the `--ink-faint` question Keith declined in #49, and neither
    change touches it.

    **The grid one is explicitly a judgment call, not a defect** - the
    critic says so - because `auto-fit` would stretch two cards to 583px
    each, which may read worse. **Keith's call, its Q1:** collapse the
    tracks, cap the grid to its content, or leave it on the grounds that
    it self-corrects as the asset grows.

55. **[done, 2026-09-24]** **[Dashboard UI]** **[V17] Seven of eleven
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
    properly designed.

    **SIGNED OFF AND FIXED, 2026-09-25.** One rule naming the
    CATEGORY rather than a fifth, sixth and seventh naming elements:
    `:where(a, button, input, select, textarea, summary,
    [tabindex]):focus-visible`. `:where()` keeps its specificity at
    zero so the four bespoke rules, which come after it, keep their own
    deliberate offsets.

    **A rule per element is how the gap happened**, and a rule that
    names the category cannot miss the next element somebody adds.

    **Tests:** four representative types (`.crumb`, `.col-tile`,
    `.snapshots-btn`, `.drawer-close`) are focused in a real browser
    and asserted to have a solid, non-zero outline rather than the
    browser's default. One real gotcha is recorded in the test itself:
    Chrome decides `:focus-visible` from how the LAST interaction
    arrived, so a programmatic `.focus()` after a mouse click gets no
    ring however the CSS is written - the test presses Tab first to put
    the browser back in the mode the test is actually about.

56. **[in-progress, 2026-09-25]** **[Dashboard UI, QA checks & contract]**
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

      **DONE 2026-09-25.** MoSCoW has its own ramp - one hue at four
      weights, reading as a scale rather than a verdict - so nothing
      borrows the status palette any more. The legend half is done too:
      it names every quiet state actually present, `inactive` included
      (#4), rather than three of five.
    - **Three visually identical check cards** in one column drawer,
      same title, same description, same Red pill - distinguishable
      only by 12px grey monospace (`dbt:multiple_birth_sibling` /
      `soda:sibling_match` / `datacontract:sibling_match`). They read as
      a rendering bug at a glance, and the threshold line carries
      **two formats for the same fact** - `REQ-QAC-047`'s
      no-threshold-fallback rule surfacing as the prose "no
      single-sided threshold — status is this tool's own verdict",
      which wraps mid-sentence and reads as debug output.

57. **[done, 2026-09-25]** **[Dashboard UI]** **[V19/V20/V21/
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

    **FOUR OF THE FIVE DONE 2026-09-25**, the first having been settled
    as Q2 the day before: the command chip gets `box-decoration-break:
    clone`; the masthead chips and breadcrumbs get `min-height:44px`
    below 480px - the minimum that makes them pressable, not a
    responsive redesign, per Keith's own call on mobile ("shave off
    some of the rough edges... everyone will be using it on desktop
    screens"); and `.crumb .tier` gets `white-space:nowrap`.

    **THE RED ENDPOINT IS FIXED, 2026-09-25** (Keith: "yep, fix it").
    Where history exists but none is current, the card painted the full
    series ending in a red dot - the only red pixel in that viewport,
    under a pill saying there is no data.

    **The LINE is untouched and deliberately so.** Keith's own words on
    the quiet states generally: "no red amber and greens... but I
    should still be able to see the historical graphs and comparison
    stuff." Only the ENDPOINT asserts "and this is where it stands
    now", which is the one thing a quiet state means nobody can say -
    so only the endpoint goes quiet. A test asserts the two paths are
    identical with and without a quiet status.

    **A SECOND BUG IN THE SAME FUNCTION, found writing the tests, and
    the more dangerous one.** `statusColorVar()` was a two-branch
    ternary falling through to `var(--good)`, so EVERY status it did
    not recognise - `nodata`, `exhausted`, `inactive`, and anything
    added later - painted green. A colour function whose default is
    "healthy" is the same false-green shape this project keeps finding.
    It names the three verdicts explicitly now and everything else is
    quiet, and `quietOf()` derives the quiet set from the vocabulary
    rather than listing it again, so a sixth status added later is
    quiet by default instead of silently green.

    Verified on the real built page at `?asof=2027-09-01`: both exec
    cards read `var(--ink-faint)` where one had been red.

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

### Found by this session, not by a critic

60. **[done, 2026-09-25]** **[Dashboard UI]** **The masthead's
    "Live" clock measures nothing at all, and says the data was updated
    when it was not.**

    **BUILT by `REQ-DASH-071` criterion 13, 2026-09-25.** The masthead
    now reads `Built <instant>` from a `BUILT_AT` const the embed step
    writes, the `setInterval` is gone, and the dot no longer pulses -
    a pulse says a feed is arriving, and nothing arrives after a static
    file is opened. A real-browser test reads the stamp, waits fifteen
    seconds - long enough to have caught the old clock twice - and
    asserts it has not moved.

    **Found by Keith, 2026-09-25**, reading the requirement draft's
    first open question: "I'm not sure that masthead is working... it
    should kind of be baked in when the dashboard gets rebuilt, right?
    Because otherwise it doesn't have any updated information in it."

    **Verified, and the code says so itself.** The section header is
    literally `Boot + fake "live" clock`:

    ```js
    let secondsAgo = 4;
    setInterval(()=>{ secondsAgo += 7; ... }, 7000);
    ```

    It is a counter starting at 4 that adds 7 every 7 seconds. It reads
    no build time, no page-load time and no data timestamp. It counts
    up from whenever the tab was opened, for as long as the tab stays
    open, beside a pulsing green "live" dot - on a page that is a
    STATIC FILE built by CI, possibly days earlier. Leave it open an
    hour and it reads "Live - updated 51m ago", which is a statement
    about the reader's browser session presented as a statement about
    data freshness.

    **This is the same family as the false greens, not a cosmetic
    one.** On a dashboard whose whole job is saying whether data is
    stale, a freshness indicator that asserts currency it cannot know
    is the dangerous direction - and it is the ONE element on the page
    a reader would trust for that question without drilling in.

    **The honest fact exists and is not embedded.** Nothing carries a
    build time today (grepped: no `generated_at`, `BUILT_AT` or
    `build_time` in the template or `embed_dashboard_data.py`), but
    `reports/results_bdm.json`/`results_cp.json` each carry a real
    `generated_at`, and CI rebuilds the whole dashboard from committed
    history on every relevant push - so "when this page was built" is a
    real, knowable fact.

    **Keith's own direction**, same message: bake it in at rebuild
    time. That also removes the `setInterval` entirely, which is the
    second-implementation problem `REQ-DASH-071` forbids - the masthead
    does its own inline arithmetic rather than calling
    `fmtRelativeTime()`.

    **Scoped into `REQ-DASH-071` rather than fixed loose**, since it is
    the same subject as that requirement and the requirement is not
    signed off yet. Recorded here because the finding is about shipped
    code and stands whatever happens to the requirement.

59. **[done, 2026-09-25]** **[Testing & dev tooling, Pipeline & publishing]** **A test computed "today" on the container's clock
    while the page computed it on the asset's, and failed for eight
    hours out of every twenty-four.**

    Found by a real full-suite run at 06:12 Perth / 22:12 UTC on
    2026-09-25 - the window where the two calendars disagree - while
    gating the work above. **Not caused by any of it**: the same run
    passed the evening before, at 22:5x Perth, when both clocks read
    the same day.

    `tests/test_dashboard_e2e.py::TestSupplyHistoryDrillDown` picked a
    supply-history row whose date was not `date.today()`, clicked it,
    and asserted the URL gained `asof=<that date>`. `date.today()` is
    the CONTAINER's date; `DEFAULT_AS_OF` is the asset's
    (`Australia/Perth`, REQ-PIPE-048). Between 16:00 and 24:00 UTC the
    page's default is already tomorrow, so the test picked a row dated
    on that default, `setAsOfInUrl()` correctly dropped the parameter -
    "a plain shared link never implies someone deliberately chose a
    date", its own comment - and the assertion failed against a
    completely healthy page.

    **Fixed by reading the page's own `DEFAULT_AS_OF`** rather than any
    clock of the test's own. The authoritative value is the one the code
    under test uses, so this cannot drift again; picking a better
    hardcoded date, or the asset clock in Python, would both have left a
    second implementation to keep in step.

    **Worth keeping visible for two reasons.** It is exactly the class
    of bug `REQ-PIPE-048` exists to prevent, living in the test suite
    rather than the code - the third place this session found it, after
    #3 (every date rendered on the viewer's clock) and #51 (the sliced
    "UTC" label). And it is a real instance of `CLAUDE.md`'s own rule
    about tests that assert against ambient state: it was green locally
    and in CI for days, and would have gone red in CI on any push made
    in that eight-hour window, looking exactly like a regression in
    whatever that push happened to touch.

61. **[done, 2026-09-26]** **[Dashboard UI]** **A scope section whose
    only check is the "no rule defined" placeholder claimed GREEN - the
    exact false green #4 closed, in a second renderer that never picked
    the fix up.**

    **Found by this session, 2026-09-26**, while building
    `REQ-QAC-037`. Moving cp-placements' two table-level business rules
    into the new cross-table section left its Table-level section
    holding nothing but the synthesized placeholder - and the page drew
    a green pill over the words "No automated quality rule defined".

    **Verified, and the code had already written the finding down.**
    `rollupStatuses()` carries this comment, added by #4's own fix:

    ```js
    // post-build-review #4. Without this line a section whose only
    // check is a placeholder rolls up GREEN - which is precisely the
    // false green that finding is about ...
    if(statuses.includes("inactive")) return "inactive";
    ```

    The section renderer did not call it. It kept its own reduce:

    ```js
    const worst = checks.reduce((acc, ck)=>
      STATUS_ORDER[checkStatus(ck)] > STATUS_ORDER[acc] ? checkStatus(ck) : acc, "green");
    ```

    `STATUS_ORDER` has no entry for `inactive` - deliberately, it is
    one of the `UNORDERED_STATUSES` - so `undefined > 0` is false and
    the seed `"green"` survives untouched. A status the ordering
    excludes on purpose reads, to a reduce seeded with green, exactly
    like a status that lost.

    **This was already live for five of the six CP datasets**, which is
    the part worth keeping visible: `REQ-QAC-037` did not introduce it,
    it moved it onto the one dataset the tests happened to drive. The
    finding sat behind a page nobody had opened rather than behind a
    condition nobody had hit.

    **Fixed** by calling `rollupStatuses()` in both section renderers -
    the dataset page's and the collection page's. The collection one
    cannot hold a placeholder today, and was changed anyway: a seeded
    reduce over `STATUS_ORDER` is now a known-bad shape in this
    codebase, not a stylistic choice. A real-browser test asserts the
    pill reads "No rule defined", and asserts first that the section
    really does hold only the placeholder, so it fails loudly rather
    than passing vacuously if a real table-level check is ever added
    to cp-placements.

    **The standing lesson is `CLAUDE.md`'s own, arriving from a new
    direction.** That rule says to enumerate every consumer when a
    VALUE's shape changes. Here the value did not change - the
    VOCABULARY did, when `inactive` was added to a status set two
    functions already reduced over. `grep`ping for `STATUS_ORDER[`
    after the fact found six call sites, of which two were sections.
    A new member of a closed set is a shape change, and the same
    enumeration applies.

62. **[done, 2026-09-26]** **[Testing & dev tooling]** **Ten tests
    were silently skipping in CI, including the whole data-layer
    coverage for cross-table checks - shipped that same morning.**

    **Found while waiting on a subagent**, from Keith's own question
    "anything small we can do while we wait", by auditing what the
    suite asserts against real trees rather than fixtures. The audit
    was prompted by `CLAUDE.md`'s own standing warning about tests
    that pass locally and fail on a fresh clone; this turned out to
    be the OTHER half of that warning, which that bullet does not
    cover: a test that neither passes nor fails, and reports green.

    **The shape.** `reports/*.json` is gitignored build output. Ten
    tests across three files guard on it and call `pytest.skip` when
    it is absent:

    - `tests/test_cross_table_scope.py` - 6 (four tests, one
      parametrised ×3). This is `REQ-QAC-037`'s entire data-layer
      coverage.
    - `tests/test_asset_time_semantics.py` - 3, through a fixture.
    - `tests/test_history_rekey.py` - 1, `REQ-PIPE-038`'s
      duplicate-key guard.

    `.github/workflows/test.yml` had no build step, so a freshly
    cloned runner has no `reports/` and every one of them skipped.

    **Why it was invisible, and why it is worse than a red test.**
    Locally they run, because a developer has built. In CI they
    reported green while proving nothing, and a skip does not fail a
    build or show up in a summary anybody reads. Nondeterministically,
    too: `tests/test_dashboard_e2e.py`'s session fixture DOES build
    `reports/`, so whether these tests execute depended on whether
    that module's worker happened to get there first - and under
    `--dist loadfile` it is a different worker.

    **Verified by reproducing the runner's condition** rather than
    reasoned about: move `reports/` aside, run the three files, watch
    ten skip. Then with the fix in place, from the same reports-less
    tree, all 59 pass and nothing skips.

    **Fixed** by running the same CI-safe chain `deploy-pages.yml`
    already runs - `mothman dashboard rebuild-results` then `mothman
    dashboard build-data` - as a step in the test job before pytest.
    Both read committed `qa_results/` history only and never open
    `data/` or a warehouse, so the standing rule holds. Chosen over a
    shared session fixture in `conftest.py`, which would have to
    survive several workers racing to write the same real files - the
    race `plans/tooling.md` #10 already recorded and `--dist loadfile`
    only avoids because each file's tests stay on one worker. A CI
    step has no such problem.

    **Two smaller findings from the same audit, neither fixed:**

    - `tests/test_run_id_guard.py:111` skips when no deliveries are on
      disk. CI must never build data, so that test gives ZERO CI
      coverage by design. Defensible, but it should be known rather
      than assumed - noted here rather than changed.
    - `tests/test_history_rekey.py:310,328` guard on `qa_results/`,
      which is committed and therefore always present. The skip can
      never fire. Harmless, but it reads as a real precondition and is
      not one.

    **The standing lesson**, and it is a genuine addition to the fresh-
    clone rule `CLAUDE.md` already carries: when a test guards on a
    build artifact, ask what it does on a runner that has never built
    one. "Fails" is the answer that rule anticipates and is the SAFE
    one - somebody sees it. "Skips" is the dangerous one, because the
    suite stays green and the coverage quietly leaves.

63. **[done, 2026-09-28]** **[Pipeline & publishing, Dashboard UI]**
    **Three defects that had been unreachable, all reached on the same
    night by the same change.** Not found by a critic - found by
    promotion starting to work, which turned on a code path nothing had
    ever executed.

    `outstanding._from_closed_slots()` reports REQ-PIPE-063's slot
    closed by monotonic filling. It returns early for a dataset with no
    FILLED slots, and only a promotion fills one, so while promotion did
    not exist the rest of the function was dead. Its own docstring said
    so - "structurally empty today". Behind that guard sat two real
    faults:

    - it asked `slots_for_dataset(dataset_id)` with no `until`, which a
      DAILY calendar refuses because it generates periods without end.
      This is what actually broke: 153 errors in
      `tests/test_dashboard_e2e.py`, every one of them a fixture error
      naming a subprocess rather than a calendar.
    - `closed_by_monotonic_filling()` returns a set of slot NAMES and
      the loop read `slot.name` off each. That one would not have shown
      as a crash in the survey - it needed a slot to actually be closed,
      which is one step further in again.

    **The third was visible rather than fatal, and is the one worth
    remembering.** With the function working, the Birth Registrations
    dataset page rendered **seventeen raw ISO dates** - "Birth
    Registrations has no supply for 2026-08-27" - which is exactly what
    REQ-DASH-071's display standard exists to prevent. Nothing was wrong
    with that requirement's work: a period NAME is an identifier, a
    DAILY calendar names its periods by the day, and no period name had
    ever reached a reader as prose before. Fixed with
    `display_time.format_period()` and `format_periods_in()`, the second
    because a filing's `ambiguity` sentence is composed once and STORED,
    so formatting at composition time would leave every earlier filing
    showing raw dates forever.

    Verified in a real browser against the rebuilt dashboard: 37 raw
    dates before, zero after. All three carry failing-first tests
    (`tests/test_outstanding.py`'s own
    `TestADatasetOnAnEndlessCalendarDoesNotTakeTheSurveyDown`, and four
    in `tests/test_display_time.py`), confirmed failing against the
    unfixed module by reverting just that file.

    **The standing lesson, and it is not "test more".** A guard that
    makes a code path unreachable also makes it untested, and the path
    runs for the first time on the day the guard stops holding - which
    is the day somebody is shipping the feature that removes the guard,
    with the least attention to spare. Worth asking, of any "this is
    structurally empty today" comment: what runs the first time it is
    not?

64. **[done, 2026-09-29]** **[Pipeline & publishing, Testing & dev tooling]**
    **A test that conflated two identifiers hid a defect that would have
    broken the first real substitution anybody made.**
    Found hours after the code shipped, by writing a DIFFERENT test
    that happened not to conflate them.

    A supply has two names. `cp-carers@202605010100000000` is how a
    filing and a decision name it; `cp_carers__202605010100000000` is
    what the warehouse can call a table, because dbt and Soda write the
    name into their own SQL unquoted and PostgreSQL folds an unquoted
    identifier to lower case. `promote()` takes both - the id for the
    log, the tables to move.

    `substitution.substitute()` took one `supply` argument and used it
    for BOTH: it judged the decision against the log, where the value is
    an id, and then built the view with it as a table name. The two
    cannot both be right.

    **WHY NOTHING CAUGHT IT, and this is the part worth keeping.**
    `tests/test_substitution.py`'s own helper promoted with
    `supply=physical, physical_tables=[physical]` - one string playing
    both parts. Twenty-six tests passed, including ones that read real
    rows through the substituted view, because within the test the two
    names genuinely were the same. The fixture was not lazy; it was
    UNDER-SPECIFIED, and an under-specified fixture makes a whole class
    of confusion invisible rather than merely untested.

    Fixed in `substitution.py` by resolving the physical table from the
    period schema (`period_schema.promoted_in`), which is where the
    warehouse actually keeps the answer, and refusing loudly where the
    period holds no such table or several. Three test helpers were
    rewritten to mint the two names differently, and one of them -
    `tests/test_drift_reference.py`'s - turned up the same latent
    conflation in a module written the same night.

    **The standing lesson is about fixtures rather than about
    identifiers.** Where a system carries two values that are usually
    derived from each other, a test that makes them EQUAL proves
    nothing about the code that tells them apart. Mint them differently
    in the fixture, even when it costs a line - the cost is one line
    and the saving is the first real user finding it.

65. **[done, 2026-09-29]** **[Dashboard UI]** **Repairing a stale link
    broke it, whenever an as-of date was set.**
    Found while building REQ-DASH-085's drill-through, by reading every
    place this page writes a URL rather than by a critic.

    `forgetStaleSegment()` is the repair for a URL naming a column or a
    check the dataset no longer has (#11): it renders the dataset page,
    drops the dead segment from STATE, rewrites the address and puts a
    notice above the page. It built the new address as
    `stateToHash(STATE) + location.search`.

    That concatenation puts the query string INSIDE the hash. With an
    as-of date set, the repaired URL reads
    `#/.../dataset/birth-registrations?asof=2026-05-01`, so on the next
    load `pathToState()` takes the dataset id to be
    `birth-registrations?asof=2026-05-01`, finds nothing, and renders
    not-found. The repair whose whole purpose was to stop a broken
    segment being re-shared produced a URL that was broken outright.

    **WHY NOTHING CAUGHT IT.** `location.search` is empty in every
    existing test of this path, and empty concatenates harmlessly. The
    bug needed one more thing to be true at the same time - a filter
    the tests had no reason to set - which is the shape of most things
    that survive a suite.

    Fixed by building the address with `URL` rather than by
    concatenation, in the same `navUrl()` the drill-through needed
    anyway. A repair of the page the reader is already on keeps the
    arrival framing, because they have not gone anywhere.
    Reproduced first, in `tests-js/navigation.test.js`.

66. **[done, 2026-09-29]** **[Pipeline & publishing, Testing & dev tooling]**
    **The same supply-id-as-table-name conflation as #64, in the module
    written the same night, found the same way.**
    Found by a test in a DIFFERENT module that happened to mint the two
    names differently.

    `inheritance.inherit_into()` - the RULE's own pass, which runs at
    every period's birth in the real pipeline - took the supply id
    straight out of the decision log and built
    `CREATE VIEW ... AS SELECT * FROM "<period>"."<supply id>"`. A
    supply has two names: `cp-carers@202605010100000000` is how a filing
    and a decision name it, and `cp_carers__202605010100000000` is what
    the warehouse can call a table. The first is not an identifier
    PostgreSQL will take unquoted, which is why supply_db refuses it.

    **WHY #64's FIX DID NOT REACH IT.** #64 was fixed on 2026-09-29 by
    adding `substitution._physical_in()`, which resolves the physical
    table from the period schema, and the write-up said the same
    conflation had turned up in a third module the same night. It did
    not say to go and look at the fourth. Substitution and inheritance
    are deliberately kept apart - they mean opposite things - and that
    separation is exactly what let one be fixed while the other was
    not.

    **WHY NOTHING CAUGHT IT, and it is #64's lesson word for word.**
    `tests/test_inheritance.py`'s own `_promote_into()` promoted with
    `supply=physical, physical_tables=[physical]` - one string playing
    both parts - so every one of the module's thirty-five tests passed
    and the real system, where the two differ, would have failed at the
    first period birth after a real promotion.

    Fixed with an `inheritance._physical_in()` of its own, and the rule's
    pass now records a missing table as a REFUSAL rather than raising,
    on criterion 10's own terms: one dataset's problem must not stop the
    rest of the period being born. Three tests pin it at the path that
    actually runs.

    **The standing lesson is about the SWEEP, not the identifiers.**
    When a fixture-shaped defect is found, the fix is not done until
    every module that could hold the same one has been looked at. #64
    named a third module and stopped; the fourth cost a second night's
    finding. `grep` for the shape - here, a period schema and a name
    from the decision log in one f-string - not for the module.

67. **[done, 2026-09-29]** **[Pipeline & publishing]**
    **A route was built whose entry point does not exist, and only an
    audit for callers found it.**
    Found by grepping for callers of the two modules shipped in the
    preceding two commits, not by anything failing.

    `qa_tools/common/filing_from_github.py` reads a filing decision out
    of a ticket comment and raises it. Nothing reads ticket comments.
    The workflow that would - `.github/workflows/ticket-sync.yml` - is
    disabled and cannot run at all: it needs the recorded QA results,
    those are rows in a PostgreSQL database since REQ-PIPE-089, and a
    GitHub runner has no route to one. Its replacement inverts the
    integration's direction, which is `plans/running-thoughts.md` #53
    and is not scoped.

    So REQ-GHUB-082's criterion 1 - "accept ... filing decisions raised
    on the GitHub ticket" - is met as far as an entry point allows, and
    that is now what the requirement says. It said "criterion 1" flatly
    for about twenty minutes, which is the part worth correcting: a
    criterion is not met because the code that would satisfy it exists
    somewhere unreachable.

    `filing_decisions.py`, shipped the commit before, has the same
    property and it is fine: its caller is the TUI adapter, which is
    the one phase of that requirement deliberately left for a session
    with Keith awake. The difference is that its caller is SCOPED and
    the GitHub one is not.

    **The standing lesson is a question, and it costs one grep.** After
    building a module, ask what calls it - in production, not in its
    tests. This project has now paid three times for code that had
    never executed outside a test: #63's guard that made a path
    unreachable, #64/#66's fixture that made two names one string, and
    this. The first two were found by accident weeks later; this one
    was found the same hour, by asking.

    Nothing was changed in the code. What changed is that the
    requirement and this file now say where the gap is, so whoever
    scopes #53 knows the adapter is already there and needs only a
    caller.

68. **[done, 2026-09-29]** **[GitHub workflow & people]**
    **The commoner way the ticket service is absent got the thinner
    message, and CI had been red on it for a run of commits nobody
    checked.**

    `ticket_github._gh()` raises `TicketServiceUnavailable` two ways. A
    MISSING BINARY got the sentence criterion 17 is actually for - "The
    change stands on its durable record and the next pass will bring
    the ticket up to date." A binary that RAN AND EXITED NON-ZERO got
    `` `gh issue list` failed: <stderr>`` and nothing else.

    The second is the commoner case in the environments this is really
    for: an unauthenticated CLI, an expired token, a network that
    cannot reach github.com. It is also the case where a person reading
    a pipeline run is most likely to conclude the promotion did not
    happen. The behaviour was always right - the reconciler records a
    failure per slot and carries on either way - but the message is the
    only part of criterion 17 a human ever meets.

    **This container cannot see it, and that is why it survived.** `gh`
    is not installed here, so every test of an absent service takes the
    first branch. A GitHub Actions runner HAS `gh` and no `GH_TOKEN`,
    so it takes the second. Both branches are now driven explicitly
    with a monkeypatched `subprocess.run`, because a test that passes
    for a reason about the machine is a test that stops covering the
    other reason.

    **The worse half of this is the process failure, not the message.**
    `tests/test_ticket_github.py::TestAnAbsentServiceRefusesCleanly::
    test_it_says_the_change_still_stands` had been failing in CI since
    that module landed, across a long run of commits - several of whose
    own messages reported a green local `mothman check` and said
    nothing about CI. CLAUDE.md has a standing rule for exactly this
    ("a passing local `uv run pytest` is NOT evidence CI is green"),
    amended to "don't block on it, but check at the next natural
    pause". The pauses happened; the check did not.

    **The standing lesson, and it is narrower than "check CI".** The
    amendment that says not to block is the one that made this easy to
    drop, because "the next natural pause" has no edge. An overnight
    run has no pauses a person would notice. So: check the real run
    BEFORE starting the next requirement, not at a pause - that is a
    boundary something actually happens at. One `actions_list` call
    against the branch answers it, and a red one found at the next
    commit costs a commit rather than nine.

    A second, cheaper lesson while reading those logs: the MCP tool's
    `get_job_logs` returns a TAIL, and a job with a PostgreSQL service
    container ends with hundreds of lines of "there is no transaction
    in progress" from the container's own log. A short tail shows none
    of pytest's output and reads as though the log is empty. Ask for
    thousands of lines and grep for `short test summary`. That is
    already in CLAUDE.md's blocked-host note; it is repeated here
    because it cost time again.

69. **[done, 2026-09-29]** **[Testing & dev tooling]** **CI was red all
    day, I told Keith it was green, and the cause was one defect shape
    that four different tests carried.** He had to say "it's been firing
    red all day" before anybody looked again.

    **THE DEFECT, which is the smaller half.**
    `decisions_for(conn, dataset_id)[-1]` reads as "the decision I just
    recorded" and means "the newest decision ANYBODY recorded for this
    dataset". These tests act on a REAL dataset id - `cp-carers`,
    because the fixtures need a real table and agency - while minting
    periods of their own, so several modules write cp-carers entries
    into one worker's log. Which module shares a worker depends on how
    pytest-xdist distributed the files, so the same code went green once
    and red twice.

    Three failed on the runner and a fourth had already been fixed that
    morning:
    - `test_filing_decisions.py` x3 - `assert 'promote' == 'reject'`, and
      an assertion that read another test's reason verbatim
      (`'read them'`, typed in `test_cli_filing_tui.py`)
    - `test_inheritance.py` - `assert 'inheritance rule' == 'Keith'`,
      where a promotion's own `inherit-refused` entries landed after the
      person's inheritance
    - `test_cli_filing_tui.py` - the same, found and fixed the same
      morning without recognising it as a class

    **Two of the three were caused by tests written that morning**, whose
    cp-carers decisions pushed the existing ones off the end.

    **THE FIX IS STRUCTURAL, so ordering stops mattering**: select by the
    period under test, which each of these mints uniquely.
    `tests/test_filing_decisions.py::_entry_for()` is the one place that
    says why. And a guard in `test_decision_log.py` walks every test
    module with `ast` and refuses the spelling outright - verified by
    reintroducing it and watching it fire. It reads the AST rather than
    the text because the first version matched its own docstring and the
    helper written to replace it, both of which quote the bad spelling
    in order to warn about it. A guard that fires on its own explanation
    is one somebody deletes.

    **THE REPORTING FAILURE IS THE BIGGER HALF, and it is mine.** At
    00:55 I checked run `3b2b53c`, found it green, and said "CI is
    green". I then pushed twice more and never looked again. Both went
    red. Keith found out by watching the Actions tab, which is exactly
    how the 2026-09-18 incident this project already has a rule for was
    found.

    **The rule existed and I had just written a sharper version of it**
    (#68, the same morning: "check the real run BEFORE starting the next
    requirement"). I followed it once and stopped. So the lesson is not
    another rule, it is what the existing one actually means:

    **A GREEN RUN IS A FACT ABOUT ONE COMMIT, NOT A STATE.** "CI is
    green" is a claim about a SHA. The moment anything is pushed on top
    of it, the claim is about a tree nobody has tested - which is the
    same reasoning `CLAUDE.md` already applies to a gate run that
    predates its last edit, arriving one layer out. So the honest
    sentence is "CI was green on `<sha>`", and if a later push has gone
    out, that sentence has no bearing on now.

    **And a flaky green is worse than a red**, which is the part that
    made this expensive rather than merely wrong: `3b2b53c` passed with
    the defect present. Reporting it as green was true of that run and
    false about the code. Where a failure is ordering-dependent, one
    green proves nothing - the fix has to make the ordering irrelevant,
    which is what selecting by period does and what `[-1]` never could.


70. **[done, 2026-09-29]** **[Testing & dev tooling]** **Splitting CI
    exposed three more tests that only ever passed because something
    else had run first - and the fast half was silently skipping three
    more on top.** Found by reproducing the runner's exact condition
    locally rather than by reading the failures twice.

    **THE REPRODUCTION IS THE REUSABLE PART.** CI's fast half has an
    EMPTY deployment database, no `data/` and no `reports/`. Recreating
    all three locally - a scratch database, both trees moved aside -
    reproduced all ten failures exactly, in 2m44 rather than a
    nineteen-minute round trip. `CLAUDE.md` already recommends this for
    the `data/` half; the database half is new and matters more now
    that the suite's source is one.

    **WHAT IT FOUND, in three groups.**

    - **`test_outstanding.py`, nine tests.** It asserts on a GLOBAL
      queue total, in a database shared with whatever else
      `--dist loadfile` put on its worker. Its own docstring already
      recorded the previous version of this - the deployment's 84
      promotions arriving mid-test - and the fix then was a database
      per WORKER, which isolates it from the deployment and from other
      workers but not from its worker-mates. Removing 270 tests
      redistributed the rest and nine tests began reporting 28
      `closed-unfilled-slot` items where they expected none. Now on a
      database per TEST (`private_supply_dsn`), which nothing else can
      write into. Per test rather than per module because the decision
      log is append-only by a database trigger, so a module cannot
      clean up between its own tests either.
    - **`test_scenario_map.py`, one test.** It rebuilds `SCENARIOS.md`
      from `read_placements()`, which reads the GENERATED
      `data/scenario_placements.json`. It passed in CI only because the
      single job bootstrapped before running anything. Marked
      `needs_deployment`.
    - **Three tests that SKIPPED rather than failed** - `test_run_id_guard.py`
      and `test_scenario_injection.py`, both on "no deliveries on
      disk". Green, and proving nothing. This is the exact silent-green
      the workflow's own bootstrap comment records having hit in 2026-09-18,
      arriving again by a new route. Both marked; the skips stay as the
      guard for a developer's own fresh checkout, where they are
      correct.

    **THE FAST HALF NOW REPORTS 2,622 PASSED AND ZERO SKIPPED** under
    the runner's real condition, which is the number worth checking
    rather than the pass count: a skip there is coverage that has gone
    quiet.

    **AND THE GUARD WAS TOO NARROW**, which is worth admitting rather
    than just widening. `tests/test_publish.py` checked for modules
    reading `reports/` and nothing else, so it missed
    `scenario_placements.json`. It now checks a LIST OF KNOWN
    ARTEFACTS, and says in its own docstring that it is not a general
    proof - nothing static can tell whether a path is read from the
    real tree or a redirected one. CI running the fast half against an
    empty deployment is the real check; the guard is the cheap one that
    catches the known shapes before a push.

    **The standing lesson, which is not "test in CI conditions".** It
    is that every one of these had been passing for a reason unrelated
    to what it asserts - a bootstrap that ran first, a worker-mate that
    wrote nothing, a tree that happened to be there. None of that is
    visible from reading the test. What made them findable in one
    afternoon rather than one at a time was reproducing the condition
    that removes all three supports at once.


71. **[done, 2026-09-29]** **[Testing & dev tooling]** **A generator
    test had been rewriting the real `data/scenario_placements.json` on
    every run, and the bootstrap was hiding it by overwriting the damage
    each time.**

    `tests/generator_isolation.py` redirects a generator's outputs to a
    tmp tree, and its own docstring promises "one obvious place" for the
    next output somebody adds. A fourth output was added and not added
    there: both generators call
    `scenario_injection.write_placements()` at the end of a run, which
    defaults to the REAL file. So `test_generate_runs.py` rewrote it
    with Birth Registrations' scenarios alone - while asserting, two
    lines further down, that the real tree was untouched.

    **IT WAS INVISIBLE BECAUSE SOMETHING ALWAYS REPAIRED IT.** The
    single CI job bootstrapped before every run, overwriting the partial
    file with a complete one. Splitting CI removed that, and the fast
    half started reading whatever a test had last written:
    `KeyError: 'TS-4'` - a Child Protection scenario missing from a file
    a Birth Registrations test had truncated.

    **WHY IT HANGS OFF A DIFFERENT MODULE**, which is the reusable part:
    the other three redirected paths are attributes of the generator
    being redirected, and this one belongs to `scenario_injection`. A
    helper that loops over `hasattr(module, name)` cannot see it, so it
    was skipped silently rather than failing. The redirect now sets it
    explicitly, and `test_generating_never_touches_the_real_delivery_tree`
    - the test that should have caught this - now fingerprints the
    placements file alongside the other three.

    **AND THE GUARD FROM #70 FALSELY ACCUSED THE FIX.** Teaching
    `test_generate_runs.py` to redirect the path made it mention the
    path, which is what that guard looks for - so it demanded a
    `needs_deployment` mark on a module that needs the opposite. The
    wrong fix was available and tempting: add the mark, quiet the
    check, and push a fast test into the slow half for no reason. The
    right one was to teach the guard that REDIRECTING an artefact is a
    stronger form of covered than any mark.

    Worth keeping as a caution about this kind of guard generally: a
    static check on "does this module mention X" will accuse the code
    written to handle X properly, and each false positive is pressure to
    satisfy the checker rather than the requirement.

72. **[in-progress, 2026-09-30]** **[Pipeline & publishing]** **A held
    supply would have taken the whole collection's run down, which is
    the exact opposite of what three separate places promise. Found by
    running the path for the first time, while building REQ-PIPE-078
    criteria 9 and 10.**

    **THE PROMISE.** REQ-PIPE-059 criterion 7, `holds.py`'s own
    docstring and `supply_holds.py`'s "every other dataset in the
    delivery is processed normally" all say the same thing: one dataset
    nobody could place must not cost the others their QA. It is this
    area's standing blast-radius rule, stated in the requirement and
    twice in the code.

    **WHAT ACTUALLY HAPPENS.** A held supply gets no view in the run's
    schema - that is how "a held supply is not checked" has been
    enforced by construction rather than by remembering, and it is
    correct as far as it goes. But every tool is then pointed at a
    FIXED set of things to check. dbt is asked to build six named
    models, so the model over the missing view does not fail, it
    ERRORS - and an errored node is not a test result, it raises
    through the orchestrator's `_run_step` and abandons the run.
    Measured against a real Child Protection arrival with `cp-clients`
    held, on a scratch database:

        dbt could not run 1 node(s): model.birth_registrations.stg_cp_clients
          relation "qa_trial_...z.cp_clients" does not exist

    Five healthy datasets lost their QA for one held supply.

    **WHY IT WAS NEVER SEEN.** The corpus holds ZERO holds of either
    kind - no filing with `branch='held'`, no delivery with a `held`
    entry - so the path had never run. `tests/test_holds.py`'s own
    `TestBothFilesAreStagedAndNeitherIsReadable` covers the VIEW layer
    and stops there, which is exactly the shape CLAUDE.md's own
    shape-change lesson warns about: a green data layer says nothing
    about the layer that consumes it.

    **IT IS NOT SPECIFIC TO THE NEW KIND OF HOLD.** Verified rather
    than assumed: building the run views with an ambiguous candidate
    set - REQ-PIPE-059's own delivery-level hold - leaves the run
    schema byte-identically empty. The same crash, by the same route,
    in code shipped weeks ago.

    **FIXED FOR dbt, both collections**, with the failing test first
    (`tests/test_run_dbt_cp.py::TestAnUnreadableTableDoesNotTakeTheRunDown`,
    confirmed red against the pre-fix code). `--exclude stg_<table>+`,
    and the `+` is the whole fix: dropping the model from `--select`
    left FOUR nodes still erroring, because `dbt build` runs every test
    DEPENDING on a selected node - three relationships tests declared
    on readable models that reference the unreadable one, plus a
    cross-table singular test. Only the downstream selector takes the
    dependents with it, and dbt is the only thing that knows what they
    are. This is the one place `run_dbt` uses a graph selector rather
    than an explicit node list, and its docstring says why.

    **THE OTHER THREE TOOLS ARE THE SAME BUG AND ARE NOT FIXED.** The
    same probe, re-run with dbt fixed, dies one tool later:

        Soda Core failed - UndefinedTable: relation "cp_clients" does not exist

    datacontract-cli and Evidently are unexamined and have no reason to
    differ. Each is pointed at its own fixed set - Soda at a whole
    checks YAML - so each needs its own way of being told what not to
    read, across two collections.

    **WITH KEITH, 2026-09-30**: whether to finish all four tools inside
    REQ-PIPE-078, or to scope the tool-blindness as its own requirement
    - the recommendation - since the defect is cross-cutting, predates
    078, and is bigger than the criterion that found it. Nothing is
    worse in the meantime: the same hold crashed at dbt before this
    change and crashes at Soda after it, and the corpus has no holds.
    **CLOSED 2026-10-06**: the other three tools were fixed by REQ-PIPE-079
    and REQ-PIPE-115 (each leaves an unreadable table's checks out and says
    so); REQ-PIPE-078 is built, with an end-to-end test through all four
    tools over a held sibling (`TestAHeldSiblingDoesNotTakeAnyToolDown`).

73. **[done, 2026-10-02]** **[Pipeline & publishing]** `EARLY`
    may be unreachable through the real assignment path, because the
    slot list is capped at the arrival date.

    **Found while building `REQ-PIPE-080`**, by writing a test against
    a REAL dataset rather than a hand-built slot map - the fictional
    fixture the sibling test file uses would have hidden it entirely.

    **The mechanism.** `filing.file_arrivals()` builds its
    candidate slots with `slots_mod.slots_for_dataset(dataset_id,
    until=arrival.received_at.date())`, and `until` stops at the
    period CONTAINING that date. So a slot whose CLAIM WINDOW has
    already opened, but whose period has not yet begun, is not in the
    list the rule chooses from. Measured directly:

        cp-clients, arrival 2023-07-25 09:00 Perth
        2023-Q3 claim opens 2023-07-18, due 2023-08-01
        slots_for_dataset(until=2023-07-25) -> ['2023-Q1', '2023-Q2']
        current_slot(...)                   -> 2023-Q2

    A supply arriving a week inside Q3's claim window is therefore
    filed to Q2 - already filled, so branch 3 records a resupply of
    the CURRENT slot - and classified against Q2, which reads LATE.
    The honest answer is EARLY for Q3. `arrival_classification` would
    give that answer correctly; it never gets the chance, because the
    slot it needs was removed before the rule saw it.

    **Which makes the claim window do nothing.** Its whole purpose is
    to let a supply arrive before its due date and still be recognised
    as that period's. Capping the slot list at the arrival date
    defeats it by construction.

    **NOT EXERCISED TODAY, checked rather than assumed**: zero of the
    150 supplies in the real corpus arrived inside a claim window that
    the cap excluded. So this is latent, and the measured
    0 early / 240 on time / 112 late is still explained by the
    generator sending nothing early (`plans/running-thoughts.md` #27)
    rather than by this. **But the two causes are indistinguishable
    from the outside, and that is the part worth flagging**: teaching
    the generator to send an early supply (`REQ-GEN-044`) would not
    produce an `early` reading, it would produce a wrong `late` one,
    and the obvious conclusion would be that the classifier is broken.

    **FIXED 2026-10-02, with Keith's sign-off** ("we should definitely
    fix that") - sought because changing which slot a supply is filed
    to is a change to agreed behaviour, which this file's standing rule
    reserves for him.

    **The fix is the bound, not the rule.** `slots.claimable_until()`
    returns the arrival date plus the dataset's claim window - the
    window's REACH rather than today - and both call sites now use it.
    Widening the list does not widen what may be CLAIMED:
    `current_slot()` and `is_claimable()` still filter on
    `claim_opens_at`, so a slot whose window is shut is offered and not
    chosen, exactly as the daily feed has always done for the current
    day. A test asserts that invariant in both directions so a careless
    later fix cannot let a supply claim forward.

    **IT IS TWO CALL SITES, NOT ONE, and the second was found by
    enumerating consumers rather than by a failing page** - CLAUDE.md's
    own shape-change rule earning its place. Once a supply can be FILED
    to a slot whose period has not begun, it can be PROMOTED into it;
    and `slot_state.states_for()` listed slots only up to `now`, so
    that filled slot would have been absent from the dashboard. The
    early supply would have been accepted, promoted, and then
    invisible - a worse failure than the one being fixed, and
    introduced BY fixing it. Both call sites now take the same
    lookahead, and a structural test fails if either stops.

    **NOTHING ALREADY RECORDED MOVES, measured rather than argued**: 0
    of the real corpus's 150 supplies file to a different current slot
    under the new bound, which is the same zero that made this latent
    in the first place. Filings are write-once in any case, so only new
    arrivals could differ.

    Covered by `tests/test_claim_window_lookahead.py` (8 tests, 5
    confirmed failing against the pre-fix code; the 3 that passed
    before and after are the negative cases, there precisely to catch
    an over-broad fix). One of them was wrong when first written - it
    asserted that `slots_for_dataset()` never returns a slot before its
    window opens, which the design has never promised and the daily
    feed breaks every morning. Corrected to assert the real invariant,
    about what `current_slot()` CHOOSES, rather than changing the code
    to match a rule it never had.

    `REQ-PIPE-080`'s own resolver already avoided the same cap
    (`filing._slot_named()`), because a supply re-filed FORWARD by a
    person would otherwise lose its verdict.

74. **[done, 2026-10-02]** **[Pipeline & publishing]** `REQ-PIPE-098`:
    **a dataset subsetting its calendar by `delivery_months` never
    inherited, and an inherited view was invisible to the overlay.**

    Found by Keith, not by a critic, asking why Case Workers had no
    inherited entry for the quarters it does not deliver in - after
    REQ-PIPE-105's new "could not be evaluated" records showed 19 reds
    naming `cp_case_workers` as a missing table in Q2 and Q4. Two
    defects, both against criteria already marked built:

    - **Criterion 5** (non-participation "from the schedule alone"):
      `inheritance._does_not_participate()` read only explicit
      `not_expected` entries. A schedule also says it through
      `delivery_months` - Case Workers is February and August only -
      which the slot builder honoured and inheritance ignored. So Q2 and
      Q4 opened with no Case Workers at all; the decision log held not
      one `inherit` for it across the whole corpus.
    - **Criterion 16** (the inherited view visible "by the table's
      logical name"): it was visible to a query, but the period overlay
      chose among a period's versions with `period_schema.newest()`,
      which rightly refuses to order a name with no arrival key - and an
      inherited view is named just `cp_case_workers`. The overlay found
      it and read nothing.

    Neither showed until now because nothing read a sibling table from a
    period before today's overlay, and the false reds it produced were
    about the model rather than the data - the class Keith keeps
    flagging as how people learn to ignore red. They also refused
    promotion to cp-notifications and cp-investigations, whose checks
    read Case Workers.

    Fixed in both places, each with a test confirmed failing on the old
    code first: `tests/test_inheritance.py`'s
    `TestDeliveryMonthsAreNonParticipationToo` (the reason recorded is
    the schedule's own: "delivered in February and August only") and
    `tests/test_period_overlay.py`'s `TestAnInheritedTableIsRead`.
    Classed as a bug against agreed behaviour rather than a change to
    it, so fixed without separate sign-off under the 2026-09-25 rule.

    **And the first fix was itself wrong, caught by the regenerate that
    measured it.** It asked "is this period one of my slots?" of EVERY
    period in the asset, so each Birth Registrations daily period
    (`2026-08-24` and sixteen more) read as Case Workers declining it,
    and was recorded as a refused inheritance. Restricted to periods of
    the dataset's own calendar, with
    `test_another_calendars_period_is_not_its_business` confirmed failing
    first.

75. **[investigate, 2026-10-04]** **[Pipeline & publishing]** **A
    `promotion-withheld` note makes a filled slot read as empty.** Found
    by `delivery-architect`'s pre-build review of the option A batch, and
    PROVEN, not just read: `tests/test_withheld_does_not_empty_a_slot.py`
    (written first on Keith's instruction) fails on the current code -
    `decision_log.promoted_into()` returns `None` and
    `promotion.filled_slots()` is empty after a withheld note lands on a
    slot holding a promoted supply.

    Cause: every "what does this slot hold" reader takes the LATEST
    decision naming the slot, and `promotion.after_run()` writes the
    withheld note whenever an arrival is off-cycle - even when the gate's
    real refusal was that the slot was already filled. Real case:
    cp-case-workers' Q3 promoted; a resend arriving in Q4 (which it
    skips) files to Q3, is withheld, and Q3 then reads unfilled, so the
    next Q3 arrival would auto-promote over the accepted supply.

    NOT YET SEEN IN DATA: the sandbox database held no withheld entries
    when checked. A significant defect against agreed behaviour (a filled
    slot must block automatic promotion), so the fix waits on Keith. The
    fix is the resolving/annotating split now written into REQ-PIPE-132,
    and REQ-PIPE-077 itself is retired by REQ-PIPE-131.

    **Decided, 2026-10-04 (Keith):** fixed by construction, not patched -
    "what does this slot hold" becomes ONE metadata-schema view built only
    from slot-changing decisions (REQ-PIPE-130), built straight after
    REQ-DOCS-143 and ahead of the rest of the batch, with this entry's
    test going in alongside it, failing first.

    **CLOSED 2026-10-04 overnight (sprint 2).** The test went in
    (`tests/test_withheld_does_not_empty_a_slot.py`). It no longer failed
    by the time it landed - #84's fix had already made `promoted_into`
    skip refusals - and the fix by construction is in: `qa.slot_holds`
    (REQ-PIPE-130 criterion 8) reads no refusal at all.

76. **[blocked, 2026-10-04]** **[Dashboard UI]** **The arrival history labels
    an arrival with its DELIVERY's receipt time, not the file's own.**
    Spotted by `delivery-architect` reviewing REQ-PIPE-144:
    `arrival_history._arrivals_in` takes the delivery's instant, while a
    filing (and the dashboard's own `arrivedAt`) uses the file's. They
    differ whenever a delivery's files land at different times, which the
    synthetic generator already does for ~20% of multi-file deliveries
    (`generator/receipt_instants.py`, up to ten minutes apart). Keith,
    2026-10-04: fix it. A minor bug against agreed behaviour (REQ-PIPE-105:
    every file is its own arrival with its own receipt), so it gets a
    failing test first and needs no further sign-off.

    **WORSE THAN A LABEL, AND FOLDED INTO REQ-PIPE-144 (Keith,
    2026-10-04).** It is `mothman supply history` (and the delivery
    companions beside it), and the same code builds each arrival's SUPPLY
    ID from the delivery's time - so for a spread delivery the id matches
    no filing. The database holds no per-file receipt until 144 adds one,
    so 144 carries the fix as a criterion (the arrival history reads the
    one receipt view) rather than a stopgap now.

77. **[done, 2026-10-05]** **[Pipeline & publishing]** **An
    unreadable table no longer takes a run down - but its reds do not
    all exist, and none of them reach the dashboard.** Found by a
    verification probe Keith approved (REQ-PIPE-078 criteria 9-10 and
    the unsigned REQ-PIPE-115), run against real tools on scratch
    databases; probe and per-case output in the session scratchpad,
    nothing committed. Key claims re-checked at source by the main
    session.

    WORKS: in Child Protection, with a sibling table ABSENT, every run
    completes, all four tools run, each tool leaves out exactly the
    checks over the absent table, and each of those reappears as an
    `unrunnable` red naming the table ("did not fail - it could not be
    evaluated"). No pass for an unevaluated check anywhere.

    FOUR GAPS, the first being the most serious:
    1. **The reds never reach the dashboard.** `qa_results_reader`
       (TOOL_ORDER, ~line 67/87) and `cp/build_results_from_history.py`
       read only dbt/soda/datacontract/evidently, so `unrunnable` and
       `held` records are stored and dropped on rebuild; the template has
       no treatment for them. REQ-PIPE-105 criterion 13 ("make plain the
       check is red for want of a promoted table") is therefore met in
       the database and NOT at the layer a person sees - a claim
       `requirements.yaml` makes that the display does not bear out.
    2. **A HELD supply's own checks are evaluated in batch order** -
       views are built before filing raises the hold, so its run records
       ordinary verdicts against a supply with no period (37 in the
       probe). REQ-PIPE-078 criterion 9 is not met. Even when withheld,
       the held reds are written under the period-less held run, and the
       sibling runs report the same checks as "no filled slot" rather
       than "held" - two reds, two reasons, never one saying "held".
    3. **A CONTESTED run's own checks vanish** (40 of 43 in the probe) -
       by design under REQ-PIPE-079 criterion 13, but it is the "silently
       omitted" REQ-PIPE-115 exists to stop.
    4. **Birth Registrations emits nothing** when its one table is
       unreadable - every tool is replaced by `lambda: []`
       (`orchestrate_bdm.py` ~163-168), reason only in `tables_read`.
    Also: nothing reconciles what was withheld against what was reddened
    (115 criterion 7), and the not-yet-due / overdue / awaiting-decision
    reason branches were not exercised by the probe's fixture.

    Gap 1 is a defect against signed, built behaviour and goes to Keith
    for sign-off before any fix, failing test first. Gaps 2-4 are what is
    genuinely left of REQ-PIPE-078 and REQ-PIPE-115.

    **GAP 1 FIXED, 2026-10-04 (Keith signed the fix).** Failing tests
    first, each confirmed red against the old code: the reader
    (`tests/test_qa_results_reader.py`'s
    `TestACheckThatCouldNotRunIsReadBack`), the builder
    (`tests/test_build_cp_dashboard_data.py`'s
    `TestACheckThatCouldNotRunStaysOnItsOwnCard`) and the page
    (`tests-js/not-evaluated.test.js`). The reader and the CP rebuild now
    walk `RESULT_TOOLS` (the four tools plus `unrunnable` and `held`),
    kept apart from `TOOL_ORDER` because a pseudo-tool is owed by no run.
    THE BUILDER WAS WORSE THAN BLIND: a not-evaluated record (value None)
    CRASHED it in the column stats - hidden only because the reader never
    passed one through; the live path, which hands the builder in-memory
    results including these records, could hit it. Each such record now
    joins the real check's card (by check_id, not by its own check_name,
    which would open a second card) as that run's red, carrying
    `not_evaluated` with the reason. The page shows "not evaluated in the
    latest run" on the card, the reason in the check panel (no invented
    difference against an earlier run), "Not evaluated" in the chart's
    table and tooltip, and a GAP in the trend line - it used to plot the
    run at ZERO, the "nothing wrong" end of the axis.
    NOT COVERED by this fix, and left to the rewritten REQ-PIPE-115:
    gaps 2-4. **REQ-PIPE-115 REDRAFTED by delivery-scoper and SIGNED 2026-10-04**:
    one dataset-level red (held reuses REQ-DASH-070's held-supply item; a
    contested dataset gets a new 'Two files, choose one' item) that rolls
    up; sibling checks reading the table say held/contested in their own
    run; 078 criterion 9 narrowed to tool verdicts; the narrow
    reconciliation stops the batch. Its CI sibling, REQ-QAC-145, is
    registered PARKED until the tool set is settled. Birth Registrations' builder needs no change yet because it
    emits no such record (gap 4). No real-browser test exercises one,
    because the bootstrapped history contains none until a scenario
    plants one - REQ-GEN-136's planted shapes are the natural place.

    **GAPS 2-4 BUILT 2026-10-05 overnight (REQ-PIPE-115, sprint 6).** Gap
    2's cause was the period overlay returning early for a supply with no
    period, leaving staging's view of a HELD table readable; it now drops
    that view and records the table held, and both orchestrators run no
    tool when their own table is held, contested or refused at load (any
    other reason raises). Tests `tests/test_unreadable_own_table.py`,
    each confirmed failing first. Gap 3 (siblings saying absent for a
    held table) and gap 4 (Birth Registrations' contested case) are its
    criteria 14-16 and 23. The dataset-level red, the reconciliation of
    what each tool left out, and the dashboard's as-of rule are the rest
    of that requirement.

78. **[investigate, 2026-10-04]** **[GitHub workflow & people]** **CI's
    bootstrap would write real GitHub tickets if it ever had a token.**
    Spotted by the agent prototyping REQ-TEST-116's equivalence test and
    confirmed at source: `ticket_reconciler.service_from_env()` treats
    `GITHUB_REPOSITORY` being set as "ticketing is configured", and
    GitHub Actions sets that variable on EVERY run - so the deployment
    half's `mothman pipeline bootstrap` reaches the reconciler with a
    real `GitHubTickets(keithamoss, data-poc)`. Checked 2026-10-04: no
    issue on the repository has been created or touched since
    2026-09-28, so in practice nothing has been written - most likely
    because the job holds no token that can write issues. LATENT, not
    live: the gate is an incidental variable, not a decision. Natural
    home: the environment-safety group (REQ-PIPE-093 refresh, in
    scoping) - ticketing switched on by the environment's own declared
    configuration. Not fixed; needs Keith.

    **DECIDED 2026-10-04 (Keith):** carried by REQ-PIPE-093, signed -
    ticketing is switched on only by the environment's declared
    configuration, and the `ci` environment declares it off.

79. **[investigate, 2026-10-04]** **[Pipeline & publishing]** **An older
    checkout can silently DOWNGRADE a database's schema marker.** Found
    by the delivery-scoper refreshing REQ-PIPE-107, not yet reproduced
    here: `qa_store.ensure_schema` only asks whether the database's
    SCHEMA_VERSION EQUALS the code's, so a checkout on an older commit
    pointed at a newer database re-runs its own older DDL and writes its
    LOWER version over the newer one. REQ-PIPE-144 refuses an older
    schema; nothing refuses a NEWER one. Is a defect claim, so a failing
    test comes before any fix and Keith signs it off; it is also the
    refresh's open question Q4 (fold the refusal into 107, or its own
    requirement).

    **DECIDED 2026-10-04 (Keith):** folded into REQ-PIPE-107, signed - a
    newer schema is refused, and the downgrade is fixed failing-test-first.

80. **[done, 2026-10-05]** **[Pipeline & publishing]** **"Reject
    the supply" is offered for a failed load, and may not work on one.**
    Raised by the delivery-scoper refreshing REQ-DASH-148, not yet
    reproduced here. The `failed-load` outstanding item
    (`qa_tools/common/outstanding.py`, `_from_loads`) offers "reject the
    supply" as a response, but `rejection.reject` works by MOVING the
    supply's physical tables to the rejected schema - and a failed load
    has no table. Two things unverified: whether rejecting a failed-load
    supply succeeds at all, and whether it clears the item, since
    `load_log.failures()` reads only load records and a rejection writes
    a decision-log entry. Matters more now: from REQ-QAC-096 (signed
    2026-10-04) every file refused by a file check takes this same path.
    A defect claim, so a failing test comes first; whether the fix is a
    sign-off item depends on what the probe shows.

    **REPRODUCED 2026-10-04**, failing test kept in the session scratchpad
    (`test_reject_failed_load.py`, a class for
    `tests/test_filing_decisions.py`): a FAILED load record for a real
    dataset, then `filing_decisions.apply(REJECT)` naming a period. The
    rejection IS ACCEPTED - `changed=True`, a decision-log entry, no table
    moved because there is none - and the failed load is STILL in
    `load_log.failures()`, so the item stays open and the person is
    offered the same decision again. `failures()` reads only load records
    and never consults the decision log. TWO THINGS STILL OPEN, which is
    why this is Keith's rather than a minor fix: which period a rejection
    of a never-filed supply names (the log refuses a decision with no
    slot), and whether the terminal's queue even reaches a failed load -
    `filing_queue.awaiting` is built from slot states, and a supply that
    never loaded may never have been filed. Both belong next to
    REQ-DASH-148, which now owns how a failed load is shown.

    **DECIDED 2026-10-04 (Keith):** amend REQ-DASH-148 to own how a
    failed load is rejected and cleared - the period, the route, and
    what clears the item. Drafting via delivery-scoper; Keith signs the
    wording.

    **SIGNED 2026-10-04:** split out as REQ-PIPE-153 (15 criteria), with
    REQ-DASH-148 criterion 3, NFR 5 and decision 8 amended to match, an
    unmet entry on REQ-PIPE-060 criterion 18, and a sentence added to
    REQ-GHUB-082 criterion 16. Not built. Two more defects found while
    drafting it are covered there: promoting a failed load records a
    promotion of nothing (153 criterion 6), and #84 below, fixed first.

    **BUILT 2026-10-05 overnight (REQ-PIPE-153, sprint 6).** The kept
    reproduction is `tests/test_filing_decisions.py::TestRejectingASupplyThatNeverLoaded`,
    confirmed failing against the pre-fix `load_log.failures()` before the
    fix: `failures()` now leaves out a failed load a PERSON has rejected,
    derived from the decision log at read time and writing nothing to the
    load record. A failed load filed to a period is listed in the
    terminal's standing queue offering reject only; one filed to no period
    is left to the held route; promoting one is refused on every route.

81. **[investigate, 2026-10-04]** **[Pipeline & publishing]** **An
    automatic promotion records the git identity that ran the pipeline as
    its actor, not the rule.** Found by delivery-scoper refreshing
    REQ-PIPE-086, verified here: both orchestrators' `promote_after()`
    pass `actor=run_by` with `actor_kind=rule`
    (`qa_tools/bdm/orchestrate_bdm.py` `promote_after`,
    `qa_tools/cp/orchestrate_cp.py` likewise), and the bootstrapped
    database holds 69 `promote` and 9 `promotion-withheld` entries whose
    actor is `noreply@anthropic.com`. REQ-PIPE-074's decision is that a
    rule's actor id is THE RULE'S NAME, and inheritance gets it right
    (`"inheritance rule"`). The KIND is correct, so the stickiness rule
    (automation defers to a person) still works; what is wrong is who a
    reader is told decided. Touches a built requirement's claim, so it is
    Keith's to sign off; a failing test comes first.

    **FIXED 2026-10-04 (Keith: fix now).** `promotion.RULE_ACTOR =
    "promotion rule"`, passed by both orchestrators' `promote_after()`
    in place of the operator's identity. `tests/test_promotion_actor.py`,
    confirmed failing first, linked to REQ-PIPE-074. Rows already in a
    database keep the old actor until the next bootstrap regenerates
    them - synthetic history, so nothing to migrate.

82. **[investigate, 2026-10-04]** **[GitHub workflow & people]**
    **REQ-GHUB-082 criterion 17 is only half wired.** Found by
    delivery-scoper refreshing REQ-PIPE-086, verified here: the offer to
    decide on a supply a run left waiting (`filing_tui.offer_after_run`)
    is called only on the synthetic route (`cli/bdm.py`, `cli/cp.py`,
    after `report_recorded`). The real hand-filed routes end in
    `_finish_supply` and never offer it. Touches a built requirement's
    claim, so it is Keith's; a failing test comes first.

    **FIXED 2026-10-04 (Keith: fix now).** Both `_finish_supply`
    functions now call `filing_tui.offer_after_run` for a KEPT run, never
    a trial. `tests/test_offer_after_hand_filed_run.py`, confirmed failing
    first for the kept case, linked to REQ-GHUB-082.

83. **[investigate, 2026-10-04]** **[Pipeline & publishing]** **The
    Birth Registrations Lambda handler would crash on its first file.**
    Found by delivery-scoper refreshing REQ-PIPE-086, verified here by
    reading: `aws/lambda_handlers/bdm_ingest_handler.py` calls
    `orchestrate_bdm.run_single(..., reference_csv=REFERENCE_CSV)`, and
    `run_single` no longer takes `reference_csv` (REQ-QAC-108 moved the
    drift reference), so it raises `TypeError`. The CP handler does not
    pass it. Nothing runs these handlers today, which is how it went
    unnoticed. Owned by the Lambda requirement split out of REQ-PIPE-086
    (REQ-PIPE-152, drafting), whose criteria move both handlers onto the
    shared lifecycle; a failing test comes first.

    **DECIDED 2026-10-04 (Keith):** left to REQ-PIPE-152 (its last
    criterion), which rewrites the handler anyway - a one-argument patch
    now would be thrown away.

84. **[investigate, 2026-10-04]** **[Pipeline & publishing]**
    **Rejecting a supply filed as a resupply of a filled period empties
    that period.** Found by delivery-scoper drafting the failed-load
    rejection (#80), confirmed here by reading the code but not yet
    reproduced: `decision_log.promoted_into` takes the LAST decision naming
    a slot (`to_slot` or `from_slot`), and a reject names its supply's
    filed slot as `from_slot`, so it returns None whichever supply it
    names. Rejecting an unpromoted resupply of a promoted period would
    therefore make the period read as unfilled while the promoted
    supply's tables still sit in the period schema; `slot_state` shows
    it REJECTED too. It touches a built requirement's claim (REQ-PIPE-074
    criterion 9, REQ-PIPE-076).

    **DECIDED 2026-10-04 (Keith):** fix FIRST, failing test first, ahead
    of the failed-load rejection requirement that depends on it.

    **FIXED 2026-10-04 (Keith: "start now"), failing tests first.**
    Reproduced as read, and it was WIDER: a `promotion-withheld` entry
    (an off-cycle resupply automation stood back from) names the period
    as `to_slot`, so it emptied a filled period the same way. Fixed in two
    places, because the rule had two copies:
    - `decision_log.promoted_into` walks the slot's entries oldest first;
      a reject, demote or re-file empties the slot only where it names the
      supply filling it, and `RECORDS_A_REFUSAL` (`promotion-withheld`,
      `inherit-refused`) never changes what fills it.
    - `slot_state.state_of` read the LAST entry too, so the queue and
      tickets showed REJECTED. Where the latest entry is about another
      supply, the slot reads as its filler's, with the filler's own
      decider and reason.
    Tests: `tests/test_decision_log.py::TestRejectingAnotherSupplyLeavesTheSlotFilled`
    (3) and `tests/test_slot_state.py::TestRejectingAnotherSupplyLeavesTheSlotPromoted`,
    each confirmed failing first. `latest_for_slot` itself is unchanged:
    it answers "what was the last decision", which substitution's refusal
    wording needs. REQ-PIPE-130's slot view (signed, build step 2) will
    replace both readers with one.

85. **[investigate, 2026-10-04]** **[QA checks & contract]** **The drift
    reference skips a promoted period when a later entry is about another
    supply - a third copy of #84's rule.** Found by delivery-architect's
    pre-build review of the file-check group, confirmed here by reading
    the code, not yet reproduced: `drift_reference.reference_for()` walks
    back through periods and accepts one only if
    `decision_log.latest_for_slot()`'s LAST entry is a promote or re-file.
    #84's fix went into `promoted_into` and `slot_state`, not here. So a
    reject or demote of a different supply, a `promotion-withheld`, an
    `inherit-refused`, and (once REQ-PIPE-151 lands) every
    `promotion-refused` make it skip a period that holds a promoted
    supply. The result today is a reference further back than it should
    be. Under REQ-QAC-108's 2026-10-04 amendment it becomes a false red
    ("no accepted earlier supply"). The architect also names `_standing_on`,
    `substitution.py` and `inheritance.py` as `latest_for_slot` readers to
    check. A defect against built code, so a failing test comes first;
    the obvious fix is to ask `promoted_into`, which #84 corrected.

    **DECIDED 2026-10-04 (Keith): wait for REQ-PIPE-130's slot view**
    (build step 2), which replaces every reader of "what a slot holds"
    with one. It must cover this reader, and the REQ-QAC-108 amendment
    must not be built before it - otherwise its false red ships. Not
    fixed.

    **FIXED 2026-10-04 overnight (sprint 2), by the slot view as Keith
    chose.** `latest_for_slot` now returns the last decision that
    CHANGED the slot, from `qa.slot_holds`, so the drift walk reads it
    and stops skipping. `tests/test_drift_reference.py::TestAnEntryAboutAnotherSupplyDoesNotHideTheReference`
    - a reject of another supply and a withheld note - both confirmed
    failing against the pre-view code first. Every other
    `latest_for_slot` reader (substitution, inheritance, promotion_state,
    `_standing_on`, filing_decisions, slot_state) reads the same answer.

86. **[investigate, 2026-10-04]** **[Pipeline & publishing]**
    **`supply_db._redact` misses a keyword-form DSN.** Found by
    delivery-architect's review of REQ-PIPE-093, confirmed by reading: the
    redaction is one regex over the URL form (`://user:pw@`), so a DSN
    written as `host=... password=secret` passes through unredacted, and
    psycopg's own parse errors can echo DSN fragments. The docstring says
    why it matters - errors reach CI logs on a public repository. Latent:
    every DSN this project sets is URL-form. Minor fix, failing test first
    (a keyword-form DSN and a malformed one); REQ-PIPE-093 criterion 3
    leans on it.

    **FIXED 2026-10-04 (Keith: "redact both forms").** `_redact` now asks
    libpq's own parser (`psycopg.conninfo.conninfo_to_dict`) which part is
    the password, so no form can be missed, and shows nothing of a string
    it cannot parse. `tests/test_redact_dsn.py` - URL, keyword, quoted,
    spaced, query-string, malformed, and end to end through `connect()` -
    6 of 8 confirmed failing first. The message now reads
    `host=... port=... dbname=... user=... password=***` rather than a URL.

87. **[investigate, 2026-10-04]** **[Testing & dev tooling]**
    **The dev-container/CI PostgreSQL pin test checks only the first CI
    service.** Found by the same review, confirmed by reading:
    `tests/test_devcontainer.py::_ci_postgres_image` returns the first job
    with a postgres service, and `.github/workflows/test.yml` has two
    (both `postgres:16` today), so the second could drift unchecked.
    Minor; REQ-PIPE-146 criterion 5 replaces this comparison with "every
    image tag equals the declaration", so fold it in there.

    **FIXED 2026-10-04 (Keith: "fix now").** `_ci_postgres_images` returns
    every job's image and the pin test compares each one;
    `test_every_ci_job_is_compared_not_only_the_first` pins it against a
    workflow where only the second job drifted, which the old first-match
    lookup was shown to miss. REQ-PIPE-146 still replaces the comparison
    with "equals the declared major".

88. **[done, 2026-10-04]** **[Dashboard UI]** **Two different cross-table
    checks sharing a name were drawn as one card.** Found overnight by the
    full suite (`tests/test_cross_table_scope.py::TestPooledChecksKeepSeparateIdentities`
    failing), and partly MY regression: this morning's gap-1 fix
    (post-build-review #77) let a can't-run record for cp-placements'
    `cp_client_id.relationships_dbt` open a card of its own under the
    same URL key as cp-investigations' check, so the section had a
    duplicate key. Underneath it was an older defect: the CP builder
    keyed a section's cards by (engine, check_name), so cp-placements'
    REAL verdicts for that check had always been merged into
    cp-investigations' card on cp-clients' cross-table section - silent
    wrong information. FIXED (minor bug and Keith's overnight permission):
    cards are keyed by check_id, and where two pooled cards share a URL
    key each is prefixed with its declaring dataset - only colliding keys
    change, so no other URL moves. `tests/test_build_cp_dashboard_data.py::TestTwoChecksThatShareANameStayTwoCards`,
    confirmed failing first.

89. **[investigate, 2026-10-04]** **[Pipeline & publishing]** **A withheld
    supply used to read as RETURNED in a slot's state; it now reads as
    awaiting a decision.** Noted overnight (sprint 2), not a defect report
    so much as a behaviour change worth a look: `slot_state` mapped any
    unrecognised latest action - `promotion-withheld` included - to
    RETURNED ("a person returned it"). With refusals no longer read as a
    slot's decision (REQ-PIPE-130), a withheld supply's slot falls through
    to its filing and reads AWAITING_DECISION, which is what REQ-PIPE-077
    meant ("a person decides whether it fills this period"). No test
    pinned the old reading. Flagged rather than assumed right.
    **MOOT since sprint 3b (REQ-PIPE-131, 2026-10-04)**: the off-cycle
    gate that wrote `promotion-withheld` is retired, so nothing produces
    a withheld supply any more - an arrival with no open period is held
    before it is filed. Left for Keith only as a record.

90. **[done, 2026-10-04]** **[Docs & process]** **The validator demanded
    that a RETIRED requirement's code still exist.** Found retiring
    REQ-PIPE-063 and REQ-PIPE-077 (overnight sprint 3b): the requirements
    gate failed on their `implemented_by`/`linked_tests`, because the
    whole point of those retirements was to REMOVE that code - and
    REQ-DOCS-143's own decision says a retired requirement "keeps whatever
    it carried as history". Satisfying the gate would have meant deleting
    the history. A minor gap in REQ-DOCS-143's build, not a design change:
    FIXED - a retired requirement's links are no longer resolved; a live
    one's still are (the control). `tests/test_validate_requirements.py::
    TestARetiredRequirement::test_its_record_of_code_since_removed_is_kept_as_history`,
    confirmed failing first.

91. **[done, 2026-10-04]** **[Pipeline & publishing]** **A check could
    get two results in one run - a `held` record and an `unrunnable`
    one.** Latent until REQ-PIPE-131 produced the first real holds: Case
    Workers' supply was held and Notifications' own table was staged
    awaiting a decision, so the notifications->case-workers check was
    explained by `held_blast_radius` AND by `unrunnable`. Caught by
    `tests/test_history_rekey.py`'s one-result-per-check invariant
    against a fresh bootstrap. FIXED: `unrunnable.results_for` leaves a
    check that reads any held table to `held_blast_radius`, and records
    one result per check where several of its tables are unreadable.
    `tests/test_unrunnable.py::TestOneRecordPerCheck`, confirmed failing
    first.

92. **[done, 2026-10-04]** **[Dashboard UI]** **A hold's reason showed a
    raw ISO instant in the queue.** My own sprint 3b text: the reason a
    held supply's closed slot was unavailable named "the next period's
    claim window opened at 2023-04-17T09:00:00+08:00", and the reason is
    stored and rendered verbatim. Caught by the display-standard e2e test
    (REQ-DASH-071). FIXED: the reason carries no instant.
    `tests/test_assignment.py::TestAHoldsReasonIsWrittenForAPerson`,
    confirmed failing first.

93. **[investigate, 2026-10-04]** **[Pipeline & publishing]** **An
    authored calendar's LAST period never closes, so a file arriving after
    the calendar runs out is filed backward into it without limit.**
    delivery-critic on REQ-PIPE-131, reproduced against the real config:
    a 2030 cp-clients file is filed `open-slot-unfilled` to 2027-Q4.
    `Slot.closes_at` is None where the calendar has no next period, and
    `is_open` reads None as open for ever. Criterion 1 is silent on it and
    no decision records the choice. **NEEDS KEITH**: keep it (the runway
    warning already says when dates run out), or hold such an arrival for
    a person (criterion 10's shape) - a product decision, so not changed
    overnight.

94. **[done, 2026-10-04]** **[Pipeline & publishing]** **REQ-PIPE-131
    delivery-critic, the findings fixed overnight** (each with a failing
    test first where it was a defect):
    - `file_arrivals` built each dataset's slots once per call, for the
      FIRST arrival's horizon; under REQ-PIPE-131 a later arrival in the
      same call fell past the list's last (now closing) slot and was HELD.
      Latent - every production caller passes one receipt instant. Keyed
      on each arrival's horizon now. `tests/test_file_arrivals_slot_horizon.py`.
    - The bisection test grepped for the word "bisect" in a docstring and
      a linear walk passed it; the code itself rebuilt an O(n) key list
      per arrival. Now `bisect(..., key=)`, and the test COUNTS slot reads
      (<= 40 of 4,096). `test_assignment.py::...reads_only_log_n_slots`.
    - An authored period just before a switch to a cadence rule had no
      closing instant when generated with `until` before the switch.
      `_calendar_periods` now reaches the next version's start.
      `tests/test_slot_closes_across_versions.py` (which also pins the
      window-version change and a dataset's own dates).
    - Wording that still stated the retired rule: TS-3a-d and TS-9 in the
      scenario register (TS-9's config was also self-contradictory - 21
      days early inside a 14-day window; corrected to 25 July, 9 days
      early); Thread H and sprint 9 in plans/supply-model.md; CLAUDE.md's
      `--sequential` note; REQ-PIPE-062 NFRs 1 and 4, REQ-PIPE-123 c10
      (routine amendments) and REQ-PIPE-151 c3 (PROVISIONAL - it kept
      `promotion-withheld` for off-cycle arrivals).
    - LEFT: **TS-4a**, which REQ-PIPE-131 criterion 15 names, does not
      exist anywhere - the criterion may mean TS-3a. Keith's or the
      scoper's.

95. **[done, 2026-10-04]** **[Pipeline & publishing]** **REQ-PIPE-144
    delivery-critic - storage change confirmed (all 150 filings, holds,
    delivery records and file identities identical between the two
    empty-database bootstraps); findings fixed overnight**, each with a
    failing test first where it was a defect:
    - SECURITY-ADJACENT: `reset-synthetic` matched schemas by NAME PREFIX
      (it reused the publisher's deny-list), so `staging_someone_elses`,
      `sample_reports` and the like were dropped too, and its CASCADE took
      views in OTHER schemas the prompt never listed. Now the fixed names
      match exactly, the per-period/run/dbt/trial schemas come from the
      modules that name them, and the reset REFUSES, naming them, if
      anything outside its drop set depends on what it would drop. It also
      resets exactly the list it showed. `tests/test_reset_synthetic.py::
      TestItTouchesOnlyWhatIsOurs`.
    - The hand-filing closing panel pointed at `mothman pipeline run
      --publish`, which now always refuses at that moment - it names
      `mothman dashboard publish`. CLAUDE.md's "regenerate via `pipeline
      run`" line updated.
    - An old-schema database gave a raw `SchemaVersionError` traceback from
      any command; the CLI root now turns it into the clean refusal it is.
    - A reset silently drops a publisher role's grants with the schema; it
      now says to re-run `mothman supply grant-publisher`.
    - Criterion 33 gaps closed: the two no-delivery refusals, a hand-filed
      filing's delivery link, and a trial writing no filing
      (`tests/test_filing_delivery_link.py`).
    - REQ-PIPE-038 criteria 4-5 and REQ-QAC-039 still named
      `regenerate-history` as current: re-worded, 038 c5's PROVISIONAL
      (its explicit stray-scope assertion went with the command; a rebuild
      from empty cannot carry one forward - a change to a built claim, for
      Keith).
    - LEFT FOR KEITH: criterion 16 says the ARRIVAL CLASSIFICATION reads
      the one receipt view, while filing.record() classifies from the
      arrival's in-memory instant, which arrivals.py derives with its own
      copy of the contested-pair earlier-file rule. The two agree today
      (verified for a contested pair at one instant and at two); they are
      two definitions. Also, until REQ-PIPE-151, no batch command
      processes new arrivals in a populated database (consequence of
      criteria 38-39). And the criterion 30 proof's CLI capture was 80
      columns wide, and the synthetic corpus has no contested delivery, so
      the contested view is covered by tests rather than by the proof.

96. **[in-progress, 2026-10-05]** **[Pipeline & publishing]** **delivery-critic
    on REQ-PIPE-103 criteria 9-20 and REQ-PIPE-147 (commit e01c1fd).** Core
    sound: criterion 11 holds - the stated arrival is display-only, verified
    by reading every reader and by a live run. Findings, each verified
    before being written here:
    - FIXED - **prompts were drawn under the live progress bar**
      (`cli/common.py`): "Keep this check?" appeared only once answered, the
      file-names-become-public warning was never visible, and a typed
      original-arrival time was not echoed. The bar now stops while a
      person is asked anything (`paused_progress()`). Not unit-testable
      without a pty; the critic's own `tui_drive.py` reproduction is the
      check, and the next CLI critic pass re-drives it.
    - FIXED - **a bare date was recorded as a midnight nobody stated**,
      against the decision "date and time, not a bare date": `2026-09-20`,
      `20260920` and `2026-W38-1` were all accepted. Refused now, pointing
      at `not known`. `tests/test_stated_original_arrival.py::
      TestResolvingTheAnswer::test_a_date_with_no_time_is_refused_not_recorded_as_midnight`,
      confirmed failing first.
    - FIXED - **receipts that disagreed about who filed a delivery were read
      as whichever came last** (REQ-PIPE-147's NFR says refuse). Refused
      now. `...::TestWhatAKeptSupplyRecords::test_receipts_that_disagree_about_who_filed_are_refused`,
      confirmed failing first.
    - FIXED - the NFR asking for proof that nothing decides on a typed date
      had no test: `...::TestNothingDecidesOnATypedDate` files one file with
      two statements and compares delivery and run id.
    - FIXED - the receipt instant was taken BEFORE the person answered the
      prompt, so thinking time sat between receipt and filing. Taken after.
    - FIXED (wording) - the keep-default notice said `--keep`; the flag is
      `--commit`.
    - FIXED (process) - `plans/running-thoughts.md` #52 was not deleted in
      the commit that built both its requirements; its two decisions no
      requirement carried (records regenerated rather than backfilled; why
      positional run ids keep the statement beside the receipt) moved into
      REQ-PIPE-147's and REQ-PIPE-103's `decisions:` first.
    - FOR KEITH - **a service identity hand-filing is recorded as a
      person**: with `GITHUB_ACTIONS=true` the row reads `person` /
      `github-actions:...`. Refuse hand-filing under a service identity, or
      read "person" as "the hand route"? (Recommendation: refuse - a
      record saying a person filed it should be true.)
    - FOR KEITH - **the stated time has no instant column beside its text**,
      which an NFR asks for; nothing queries it as an instant. Add one, or
      amend the NFR? (Recommendation: amend - a display-only note needs no
      index.)
    - FOR KEITH - **schema version 19 was an in-place additive migration**
      (`ALTER TABLE ... ADD COLUMN ... DEFAULT 'automated'`), not "regenerate,
      never migrate". Moot today (no hand-filed rows existed), but it is a
      departure from the NFR's wording.
    - NOT FIXED, minor and logged: the statement prints straight after
      filing rather than in the closing message (criterion 19's wording);
      `--originally-received` is silently ignored with `--trial`; S3
      LastModified is keyed by basename; `file_or_trial` resolves identity a
      second time rather than taking the command's `run_by`;
      `people.display_name` re-parses people.yaml per call; the S3 routes'
      forwarding of `originally`/`storage_times` is verified by reading only.

97. **[done, 2026-10-05]** **[Pipeline & publishing]** **dbt left out
    checks over a contested table that was perfectly readable, and nobody
    recorded them.** Found by REQ-PIPE-115 criterion 17's reconciliation on
    its first full bootstrap - the run `cp_placements__202605270100000000`
    was refused, as designed, and the batch stopped. `cp_carers` had two
    versions staged for 2026-Q2 and FELL THROUGH to the period's promoted
    version (REQ-PIPE-079 criterion 12), so it was both `resolved` and
    `ambiguous`. Soda asks the catalogue, saw the view and ran its carers
    checks; dbt asked `Resolution.unreadable`, which counted every ambiguous
    name, and excluded `stg_cp_carers+` - taking two cp-placements checks
    with it. The unrunnable rule correctly saw the table readable, so it
    recorded nothing: two checks silently absent, reading as a pass. Exactly
    the coincidence the reconciliation was signed to catch, on day one.
    FIXED at the source: `Resolution.unreadable` no longer counts a name
    that resolved (a run's OWN contested table is still withheld, by
    `own_table`, which asks `ambiguous` directly).
    `tests/test_unreadable_own_table.py::TestAContestedTableThatFellThroughIsReadable`,
    confirmed failing first.

98. **[in-progress, 2026-10-05]** **[Dashboard UI]** **delivery-dashboard-ux-critic
    on the "dataset that cannot be checked" treatment and "Compared with"
    (commit 578d193).** The reason rows, the could-not-be-loaded banner and
    the as-of behaviour of the red itself hold up in a real browser (Green
    the day before receipt, red from it; a rejected failed load red between
    failure and rejection only). Findings, verified against the template:
    - FIXED - the queue's lede said none of its items changes a dataset's
      status, one line below a held dataset's red banner (REQ-DASH-070's own
      decision said that copy would become false once 115 and 148 landed).
      It now says which kinds turn a dataset red.
    - FIXED - a dataset with nine held supplies named only the oldest. The
      reason row and banner now count them and give the oldest and newest
      receipts.
    - FIXED - the blocked dataset's tile read "Latest arrival" while showing
      the held supply's receipt, which is not the latest arrival. Now
      "Waiting since".
    - FIXED - a supply-history block whose rows were all resolved was still
      headed "Waiting for a person"; it reads "Needed a person" then.
    - FIXED (wording) - "Held — its supply is held, waiting for a person to
      place it" now reads "Held — no open period to file its supply to;
      waiting for a person"; the gap note in "Compared with" ends with what
      clears it.
    - NOT FIXED, logged: REQ-DASH-070 criterion 14 (the queue judged at the
      same instant as the red) is not met for queue ITEMS - at an as-of date
      before a hold, the queue still lists it, stamped with the bootstrap's
      wall clock rather than the receipt. A gap against a built claim, so
      it needs its own failing test and is queued for the next pass.
    - NOT FIXED, logged: the supply-history CYCLE table shows a held
      arrival as Green "not filed ... waiting 1253d" (counted from today,
      not the as-of date) beside the Red waiting row for the same supply;
      the reason row's text runs off screen at 390px; the queue stacks nine
      near-identical held cards rather than grouping by dataset; the held
      reason itself is machine text (supply keys, "claim window"); check
      panels leave the document title and focus where they were.
    - FOR KEITH: (a) should an old open hold blank out a later period's
      real, checked results (criteria 10-11 as built say yes - Case Workers'
      green 2026-Q3 supply reads No data because of holds from 2023)? (b)
      should a gap-rule red be shown distinctly from a measured red (153 of
      181 drift and volume results in the bootstrap are gap reds)? Both in
      the morning report.

99. **[in-progress, 2026-10-05]** **[Pipeline & publishing]** **delivery-critic
    on REQ-PIPE-115, REQ-QAC-108's amendment, REQ-DASH-148 and REQ-PIPE-153
    (commit 578d193).** Verified against supply6 and a clean export.
    - FIXED, CRITICAL - **one held supply stopped every later supply of its
      dataset being checked.** `supply_holds.held_tables()` returned every
      dataset with ANY open hold, and both the staging builders and the
      period overlay withheld that table from every run of the dataset;
      REQ-PIPE-115's own-table guard then ran no tool for them. On supply6,
      17 of 18 Case Workers runs had no results, eight of them on-time
      supplies filed to real slots with no hold of their own - and supply
      history showed them GREEN. A false green, the failure the requirement
      exists to prevent, produced by the requirement's own guard meeting a
      pre-existing over-broad helper. held_tables() now takes the arrival
      key and returns only tables whose supply IN THAT ARRIVAL is held.
      `tests/test_unreadable_own_table.py::TestAnUnrelatedHoldDoesNotStopAFiledSupplyBeingChecked`
      (2), both confirmed failing first. Re-bootstrapped (supply7).
    - FIXED - a blocked dataset's check panel still showed the last run's
      value and row counts as "current"; it now says "Not run for this
      period" and drops the current-run row detail (the column drawer row
      too). e2e `TestAHeldOrContestedDatasetReadsRed::test_its_check_panel_does_not_show_an_earlier_run_as_current`.
    - FIXED - the "Latest arrival" tile and the reason row named the oldest
      of nine holds as if latest (also UX #98): "Waiting since", with the
      count and oldest/newest receipts.
    - FIXED - a contested pair's refused file was also listed by the
      terminal queue as its own failed load; filing_queue.could_not_load
      now excludes it as the outstanding items already did.
    - RECORDED, NOT FIXED - criterion 2 (one not-evaluated record per
      unreadable table) is not met as signed; REQ-PIPE-115 now carries it
      as an unmet criterion rather than overclaiming, with the question for
      Keith. Criterion 17's reconciliation skips runs with no period
      (trials, unfiled-and-unheld supplies) because unrunnable records
      nothing for them; recorded as a PROVISIONAL decision and a question.
      load_log.own_words never names the column (criterion 13 lists it) -
      the library's message is the only source of a column name and is
      exactly what may not be recorded; logged. The e2e tests inject
      blockers rather than driving a real hold through the pipeline -
      which is how the critical one got past them.

100. **[done, 2026-10-05]** **[Pipeline & publishing]** **A mark that a
    period was not supplied took the outstanding queue down.** Found by the
    sprint-7 gate run, not a critic. REQ-PIPE-132's mark is about a PERIOD,
    so it records no supply, and `dataset_blockers._decided_keys` took the
    arrival key of every decision's supply - a `TypeError` on the NULL,
    raised from `outstanding.survey()`, so one mark anywhere emptied the
    whole queue. Fixed (a supply-less decision decides nothing about an
    arrival's files); failing test first:
    `tests/test_not_supplied.py::TestAMarkCarriesNoSupply`. The other
    readers that walk `qa.decision` by supply were checked: rejections are
    REJECT-only and always carry one, `load_log._settled_by_rejection` the
    same, and `slot_holds` excludes marks by construction.

101. **[done, 2026-10-05]** **[Dashboard UI]** **A period whose only supply
    was rejected never read as unfilled.** Found re-testing REQ-PIPE-153
    criterion 9's deferral once REQ-DASH-133 shipped. The first cut of
    `pipeline/closed_slots.py` counted ANY filing to a period as "something
    arrived", so a supply filed then rejected left the period looking
    filed for good: no red, no "no supply", and nothing saying what had
    happened. Fixed before it was ever committed: from the rejection on,
    the filing no longer counts, the period is its own item naming who
    rejected it, when and why, and "could not be loaded" where the load
    log says so. Tests: `TestARejectedSupplyLeavesItsPeriodEmpty` and the
    JS pair in `tests-js/closed-no-supply.test.js`. SAID PLAINLY: this
    test was written alongside the fix rather than before it, because the
    defect was in code written the same hour and never shipped.

102. **[done, 2026-10-05]** **[Testing & dev tooling]** **A new test
    promoted into the shared CP fixture's period.** The sprint-7 drift test
    for a marked period promoted cp-case-workers into 2026-Q1 - exactly
    where `tests/conftest.py`'s module-scoped CP fixture promotes its
    reference delivery on the same worker's append-only log - so every CP
    module after it on that worker errored with "superseding ... needs a
    reason" (16 errors). Its own docstring said 2027-Q1; moved to 2025,
    with the reason in the docstring. The general hazard is the one the
    fixture's own docstring already names: shared periods on an
    append-only log are shared state.

103. **[done, 2026-10-05]** **[Pipeline & publishing]** **A daily feed's
    missed day reached the dashboard as "1 period with no supply,
    2026-09-23".** Found by the real-browser display-standard test
    (`TestTheDisplayStandardHoldsInARealBrowser`) the first time a daily
    gap reached the outstanding queue: `filing_queue.Gap.describe()` wrote
    the ISO period name and called a day a period, and the queue carries
    that headline verbatim onto the page. Fixed - a daily run reads "2 days
    with no supply, Tuesday, 22 September 2026 to Wednesday, 23 September
    2026", the page's own form - failing test first
    (`TestGrouping::test_a_daily_run_says_days_in_the_pages_own_date_form`).
    The same gate run caught three TEST defects of this sprint's own,
    fixed rather than waived: the supply-history drill-down test read
    `data-run-date` from rows that now include gap rows without one; the
    nodata-pill contrast test needed a page where something is still
    nodata (every corpus dataset has an unmarked gap by 2027); and a
    sprint-6 check-panel test compared against `innerText`, which carries
    the heading's CSS upper-casing.

104. **[in-progress, 2026-10-05]** **[Dashboard UI]** **delivery-dashboard-ux-critic
    on REQ-DASH-133 (commit 0f96148).** Driven in a real browser against the
    built page plus an injected-gaps variant. Verified against the code
    before acting.
    FIXED (2026-10-05, tests in `tests-js/closed-no-supply.test.js` and
    `TestClosedWithNoSupply`):
    - HIGH: the queue was judged as at the BUILD, so at a past date it
      listed periods that had not closed yet beside a banner that
      correctly did not (criterion 9). Closed periods now come from the
      page's own as-of reading, and any other item observed after the date
      on show is left out (`asOfQueueItems`). What was open then and
      resolved since still cannot be shown - REQ-DASH-070 criterion 14.
    - HIGH: the queue's lede said everything but holds, contests and
      failed loads "change no status", directly under a red caused by a
      missing-supply item (REQ-DASH-070 criterion 1). Reworded; such an
      item is now pilled "Makes its dataset red" and counted separately
      rather than as "needing review".
    - HIGH: a daily feed's row flipped to the reason row whenever the day
      on show had no file yet, hiding the period actually late and open
      and the arrivals before it. The reason row is now only for a dataset
      with nothing ever arrived; otherwise the row keeps its columns with
      the gap beneath its pill.
    - LOW: the queue called the kind "Missing supply" where everything
      else says "no supply" - renamed.
    - HIGH (partly): "no supply", held, contested and unloadable banners
      now draw in the red tokens rather than the all-clear grey.
    - MEDIUM: the banner's command omitted the required `--reason` and
      did not say how a day is named; the accepted row's pill read "No
      data" (now "Accepted"); the accepted line's contrast (now the muted
      ink rather than faint); "The period has closed" for several groups.
    FOR KEITH (forks, not taken): which route the banner should name -
    mark-not-supplied alone, all three, the wizard, or "chase the
    supplier" first; and whether a daily feed's late-open period should be
    named on the row beside an old gap.
    LOGGED, NOT FIXED: at 390px the agency table scrolls and the gap note
    wraps to eight lines in the status column; the Birth Registrations page
    can show a red dataset, green supply-level checks and grey column
    cards at once (may predate this); the accepted line does not name
    which datasets; ordering (banner oldest first, history newest
    first), a tight " - " in queue text, and dark-mode red-pill contrast
    (shared pill styles).

105. **[in-progress, 2026-10-05]** **[Pipeline & publishing]** **delivery-critic
    on REQ-PIPE-132 and REQ-DASH-133 (commit 0f96148).** Reviewed against a
    `git archive` of the commit, with reproductions on a scratch database.
    Verified against the code before acting.
    FIXED, failing tests first (`tests/test_not_supplied.py`
    `TestAnEmptiedPeriodIsAGapAgain`, `TestASupplyWaitingInAClosedPeriodIsNotAGap`,
    and the JS pair in `tests-js/closed-no-supply.test.js`):
    - HIGH, a false green: `pipeline/closed_slots.py` recorded only a
      slot's FIRST fill and first mark, and skipped any slot filled before
      it closed - so a closed period substituted then de-substituted, or
      promoted then demoted, read as filled on the page for ever while the
      queue said it needed a person. The build now embeds every change to
      what the slot holds, from `qa.slot_holds` via `slot_timeline` (the
      one statement of which decisions fill and which empty - the first
      cut had re-stated it, which is the root cause), and every mark; the
      page reads the slot's last change by the date on show, and a mark
      stands only until the slot next changes.
    - MEDIUM-HIGH: after a rejection, a resupply filed to the same closed
      period still read REJECTED and closed - listed as "no supply" and
      markable as not supplied (REQ-PIPE-132 criteria 3 and 6). A supply
      filed and not rejected now outranks the decision that emptied the
      slot, and the mark refuses it.
    - MEDIUM: the queue panels ignored the as-of date and said gaps change
      no status - fixed with #104's `asOfQueueItems`.
    - LOW: the awaiting-supply refusal's `--operation promote|reject` was
      not pasteable (now two commands, each with `--reason`); the banner's
      command lacked `--reason` (#104); marking a substituted or inherited
      period named `demote` of the supply it stands on as the undo (now
      de-substitute / un-inherit, `TestTheRefusalNamesTheRightUndo`).
    LOGGED, NOT FIXED: an accepted gap on a dataset with no runs as at the
    date shows neither its note nor its history (the no-runs branch); a
    future real period is refused as "not a
    period it owes" (bounded by claimable_until); CLOSED is not shown in
    `mothman supply slots` or the TUI period label; `slot_state._accepted`
    and `mark()` read marks and holds without `as_at`; OVERDUE's responses
    still offer marking a period that is open; a grouped accepted note
    shows only the last mark's reason; the card mixes units (datasets for
    gaps, items for the rest). The critic also noted my REQ-PIPE-122 work
    in progress had upgraded `supply7` to schema 21 mid-review.

106. **[in-progress, 2026-10-05]** **[Pipeline & publishing]** **delivery-critic
    on REQ-PIPE-122 (commit 1798c63).** Reproduced against a `git archive`
    of the commit and a scratch database; verified against the code before
    acting. Core sound: hold leaves an amber supply unpromoted on the real
    `after_run` path, acknowledge has parity on the GitHub route, and the
    past is read from what was recorded.
    FIXED (failing test first where a defect):
    - F1, MEDIUM: an amber supply waiting under hold read
      `awaiting-decision` - the red supply's state - where an earlier
      decision had emptied its slot (criterion 17). The emptied-slot branch
      of `state_of` now asks for the hold too
      (`TestAmberWaitingAfterAnEmptiedSlot`).
    - F4 and F5: an asset level whose every version starts in the future,
      and two versions of one level sharing a date, are refused by the
      schedule gate (`amber_setting.standing_problems`,
      `TestTheConfigurationAsItStands`).
    - F6: "a acknowledge needs a reason".
    - F7: the old per-dataset ticket still told people to comment
      `/accept` (now gone, test inverted); docs/components.md and two embed
      comments still named the retired mechanism.
    LOGGED, NOT FIXED:
    - F2 (latent until REQ-PIPE-121): `amber-waiting` sticks if a supply's
      verdict later changes, because it asks whether a hold note ever
      existed rather than reading the newest outcome.
    - F3, MEDIUM, FOR KEITH: criterion 7's "not dated before the day it is
      added" is measured against the day the gate RUNS, so a commit made
      late on day D and pushed after midnight, or a CI job re-run the next
      day, goes red on a legitimate change. The fix is to take the day from
      the commit that added the version; it is a design call because a
      commit's date is author-supplied.
    - A bare `/acknowledge` with no `supply:` line is refused with "a
      decision needs the supply it acts on", without saying how to name it.
    - NFR "visible, not set-and-forget" is NOT BUILT and nothing records a
      deferral: no view shows the resolved amber value and level per
      dataset, which was the stated answer to REQ-PIPE-075's quiet-failure
      objection. For Keith.
    - No test drives `after_run`'s hold path end to end, the
      `_amber_setting_errors` wiring through `diff_base`, the GitHub
      `/acknowledge` route, or `pipeline/acknowledgements.for_dataset`.

107. **[in-progress, 2026-10-05]** **[Testing & dev tooling]** **delivery-cli-ux-critic
    on REQ-PIPE-122 (commit 1798c63).** Driven against a `git archive` of
    the commit and a scratch database, under a real terminal capture. Both
    routes agree, acknowledge is offered first on a promotion owing one, no
    state or refusal says "held", and the frozen-past errors are the
    clearest of the config errors.
    HIGH, FOR KEITH (predates 122, made likelier by it): one indentation
    slip in `contract/data-asset.yaml` crashes EVERY mothman command -
    `mothman schedule validate` included - with a ~60-line traceback,
    because `hierarchy` is loaded when `cli.app` is imported, before the
    validator's own "could not be parsed at line X" message can run. 122 is
    the first requirement that asks a lead to hand-edit nested levels of
    that file. Fixing it touches how every CLI module loads the hierarchy,
    so it is not a polish-sized change.
    HIGH, FOR KEITH: the same NFR #106 names - the resolved amber setting,
    its level and version are not visible anywhere in the terminal:
    `schedule show` says nothing about amber, `supply decisions` shows the
    rule's promotion without the setting it acted under (the row holds it),
    and the hold note names the value but not the level.
    FIXED 2026-10-05: the hold case's refusal now names `--operation
    promote` (`TestRefusalsNameTheNextCommand`); "already acknowledged"
    says by whom and when and names `supply decisions`; "not the promoted
    supply" names `supply slots`; the TUI picker shows states in words; the
    prompts say "acknowledgement" as a noun.
    MEDIUM, STILL OPEN: an empty slot is refused in lower
    case without naming `--supply`. `supply slots` truncates the automatic
    reason to "every check ... passed..." on exactly the amber rows. The TUI
    asks for an acknowledgement's reason without pointing at which checks
    warned. Config errors: an unknown value's fix text talks about versions;
    the missing asset level does not name the three values or say there is
    no default; a past-dated new version is told to "add a NEW version".
    LOW: `supply decide --help` reads as requirement ids and
    `supply decisions --help` still lists four operations; `schedule
    validate` does not say amber was checked; all three waiting states are
    yellow (met by words); at scale the closed-gaps table pushes
    acknowledgement rows below the fold; a stale schema version crashes
    `supply decide` with a raw read-only-transaction traceback.
    CAUTION RECORDED: the critic closed every `/tmp/mothman-tui-*.sock` at
    clean-up, not only its own.

108. **[done, 2026-10-05]** **[Testing & dev tooling]** **CI's bootstrap
    died on a DDL race between the two collections.** Found checking CI at
    the end of the night, as Keith asked: the deployment half of "Run test
    suite" failed on 1798c63 inside `mothman pipeline bootstrap` with
    `UniqueViolation ... pg_type_typname_nsp_index`. The bootstrap runs Birth
    Registrations and Child Protection in parallel processes, and both ran
    `CREATE TABLE IF NOT EXISTS staging._resolutions` on their first run -
    PostgreSQL's IF NOT EXISTS is not safe against a concurrent creator.
    Intermittent (0f96148's bootstrap passed), so it read as noise until it
    happened. Reproduced first with eight threads at a barrier, on the first
    attempt, with the exact CI error (`tests/test_concurrent_ddl.py`).
    Fixed: `supply_db.create_if_absent()` serialises every shared
    `CREATE ... IF NOT EXISTS` on an advisory lock - held to COMMIT when
    called inside a transaction, because a lock released after the
    statement lets a second creator pass the check against the first's
    uncommitted row - at the staging, period, superseded, rejected and
    sample schema sites and the resolutions table. The same pattern
    `qa_store.ensure_schema` already used for its own DDL.

109. **[done, 2026-10-05]** **[Pipeline & publishing]** **The delivery critic on
    REQ-PIPE-118/120: a person's supersession was invisible, and five readers
    did not know about superseded supplies.** Every finding was reproduced in
    `tests/test_supersession_critic.py` before it was fixed, and each failed
    against 99abafd.
    - **F1, critical:** `is_superseded()` read the `superseded_by` column,
      which a person's supersession leaves empty. So every one was unseen:
      not listed, still promotable while its tables sat in the superseded
      schema, and impossible to bring back. It now reads the action.
    - **F2, critical:** the relaxed shape constraint shipped without a
      schema-version bump, so a database already at 22 refused a person's
      supersede with a CheckViolation. Bumped to 23.
    - **F3/F4:** the slot read the LATEST filing. After an un-supersede it
      showed the rejected newer supply, and a superseded latest filing read
      "awaiting a decision". Fixed with `slot_state.filings_by_period()`.
    - **F5:** all 28 superseded supplies in supply8 read "waiting Nd" on the
      dashboard; `awaiting` and `waited` are now empty for a set-aside supply.
    - **F6:** a promoted supply displaced by a person's promotion was
      "superseded" with nothing moved. A supply accepted into the period is
      now left alone unless it was demoted.
    - **F7:** a superseded supply could be rejected and then brought back
      still rejected. Both are now refused.
    - **F10:** a person could supersede a supply not filed to the period.
      Now refused.
    - **F11:** the "why not promoted" text claimed only one of the three
      causes. Now covers all three.
    - **F12, pre-existing:** reset-synthetic added period names, not schema
      names. Now drops period and superseded schemas by name.
    - **F14:** a repeated supersede was refused. Now done-already.
    - **F15:** REQ-PIPE-120's evidence claimed one invocation listed all 28;
      re-measured as 16 + 12 across two.
    - **Not fixed:** F8 is a product question **for Keith**: demoting into a
      period with a newer waiting version leaves two waiting versions —
      supersede the demoted one, or refuse? F9 (closed_slots judges
      supersession by current state, not as-of) is latent; the supply8
      corpus has no instance. F13 (a period whose name normalises to end in
      `_superseded`) is an edge case. All three are recorded on the
      requirements' decisions. The critic also found two REQ-PIPE-120 NFRs
      riding on REQ-PIPE-151 that were not listed as unmet; they are now.

110. **[in-progress, 2026-10-05]** **[Dashboard UI]** **The dashboard UX critic
    on 8a942e7 (Keith's morning answers): the new verdict line was wrong for
    five of six Child Protection datasets, and past dates showed today's
    check colours.**
    - **H1, FIXED** (failing test first; Keith signed the fix off):
      `drift_reference.run_for()` took the earliest run that read a
      supply's table. Every Child Protection run reads its siblings' tables
      at one instant, so the alphabetical tie-break named cp_carers' run for
      every dataset's supply. The page said "Nothing is in place" on
      datasets whose supplies were promoted, and a drift reference could
      come from the wrong run. The run named for the table now wins; all
      107 run keys across the seven datasets map to their own dataset on
      the real database. `tests/test_drift_reference.py::
      TestASupplysRunIsItsOwnDatasetsRun`.
    - **H2, FIXED** (pre-existing; failing test first; Keith signed the fix
      off): `clipDatasetToAsOf()` overrode each check's value but kept its
      NEWEST `current_status`, which `checkStatus()` reads first. So a past
      date rendered today's colours - 96 of 227 checks as of 2 May 2026, a
      check red on that day's run reading green. The clipped check now takes
      the shown run's own status. `tests/test_dashboard_e2e.py::
      TestStatusMatchesEachToolsOwnVerdict::test_on_every_past_date_too`
      compares every check on every run date against the run it shows, and
      failed against the unfixed template. This also resolves M5, where a
      gap-red note sat beside a green pill.
    - **FIXED, minor:**
      - H3: the verdict line no longer appears on a page whose checks are
        blanked.
      - M1: the held and unloadable banner is now red, like the contested
        one.
      - M6: the queue's closed-period advice now leads with "chase the
        supplier first".
      - The held reason's "its supply" wording.
      - The mixed dashes in the held banner.
      - The gap-red note now names the filing wizard.
      - "Amber supplies:" is now "Amber setting:", on the page and in the
        terminal.
    - **KEITH'S ANSWERS, 2026-10-05:**
      - M2: judge "late, still open" against the build instant for today.
        BUILT: on the build's own day the page compares instants with
        BUILT_AT; past dates still compare days.
      - M3: LEAVE IT. The bold "Awaiting a decision" on nearly every Birth
        Registrations date comes from the bootstrap's invented promotion
        lag (one hour to three days, Keith's own choice of 2026-10-02).
        In production the rule promotes minutes after QA, so this is a
        demo-corpus artefact, not worth a second wording.
    - **LOGGED, pre-existing, not fixed:** M4. The "what is in the
      warehouse is not the latest file" banner and the supply history are
      not clipped to the date on show, so a past date shows supplies from
      later months. A real as-of gap, older than this commit.
    - Not a defect: the lowercase "unloadable" label came from the critic's
      own injected variant page. Real blockers are kind `refused`,
      labelled "Could not be loaded".

111. **[in-progress, 2026-10-05]** **[Pipeline & publishing]** **The delivery
    critic on 8a942e7: the same wrong-run defect as #110's H1, a trial
    crash, and a too-permissive commit date.** Each finding was verified
    against the code before it was written here.
    - **H1**: the same root cause as #110's H1, fixed there.
    - **H2, FIXED** (failing test first): reconciling trials (REQ-PIPE-115
      criterion 17 as amended) while a trial wrote no not-evaluated
      records crashed an ordinary trial on LeftOutMismatch when a sibling
      file would not load. Before the amendment those checks were silently
      absent (157 of 184). `unrunnable.results_for_trial()` now records
      them, explained by an unreadable table; a left-out check nothing
      explains still trips the reconciliation. The critic's exact
      reproduction now exits 0 with 27 not evaluated and 184 total.
    - **M1, FIXED** (failing test first): REQ-PIPE-122 criterion 7 dated a
      change by the earliest commit in the push that touched the file, so
      an unrelated edit let a back-dated version pass.
      `_version_added_on()` dates each version by the commit that
      introduced it.
    - **M2, FIXED**: REQ-PIPE-115's `unmet_criteria` still carried
      criterion 2 after Keith had answered it. While closing it,
      `held_blast_radius` was found recording one result per (check, held
      table) - two results for one check in one run. Now one, naming
      every held table (failing test first).
    - **M3, BUILT on Keith's answer (2026-10-05):** on a day a daily feed
      has no file at all, its row took the "no QA run within tolerance"
      branch and skipped the late-but-open note. That row now shows it
      too.
    - **FIXED, minor:**
      - The demote refusal now says "another version", not "a newer
        version".
      - `unrunnable.describe()` names every table.
      - REQ-PIPE-081 now lists its tests and implementing functions.
      - REQ-PIPE-115 now lists `blockerWithoutARunOfItsOwn`.
      - REQ-DASH-133's decision now names the wizard the way the banner
        does.
    - **LOGGED:**
      - `lateOpenAsOf` and `runStateAsOf` are date-granular, not
        instant-granular. Part of #110's M2 question.
      - REQ-PIPE-144 criterion 29's text still describes the
        reshape-only refusal; the stricter rule lives in its decisions.
      - The wiring of `_version_added_on` inside `_amber_setting_errors`
        has no test of its own.

112. **[done, 2026-10-05]** **[Pipeline & publishing]** **The delivery and CLI
    UX critics on REQ-PIPE-128 (commit c66cf3c): three ways a period could
    still hold two versions, undo text that did not undo, and a terminal
    that asked before refusing.** Each finding was verified against the
    code before it was written here. Keith answered the four that needed
    him the same morning (2026-10-05).
    - **H1, FIXED** (failing test first): `promote()` read what the slot
      held before taking its lock, so two promotions at once each saw the
      slot as it was. Two tables ended up in one period, or one supply was
      superseded twice. The slot is now locked first and judged under the
      lock (`decision_log.lock_slot`). Under the lock, a RULE meeting a
      promoted holder is refused rather than displacing it, so a person
      promoting at the same moment wins.
    - **H2, FIXED** (failing test first): rejecting a PROMOTED supply
      looked for its table only in staging, so the table stayed in the
      period and the next promotion made two. REJECT now takes the
      period's table when the supply is promoted.
    - **H3, FIXED** (failing test first): a promotion with no tables (a
      rejected supply, a mistyped id) superseded the holder in the log and
      left its table in the period. It is now refused before anything is
      written. `supersede_promoted` also fails loudly if the holder's table
      is not there (criterion 12).
    - **M1, FIXED on Keith's answer ("Honest two-step wording"):** the
      undo text now says what each undo really takes. A displaced supply
      is un-superseded (back to waiting) and then promoted again. A
      removed substitution needs a demote and then a substitute. Each
      command is on its own line.
    - **CLI #3, FIXED on Keith's answer ("Refuse before asking"):**
      `consequences()` runs the slot's refusals first: an inherited slot,
      and a displaced supply that a later period stands on. A promotion
      that cannot happen is now refused before the prompt, never after the
      yes.
    - **CLI product question A, BUILT on Keith's answer ("Yes, add it
      now"):** a version waiting in a period that already holds a
      promoted supply now appears in the queue and the period door, as
      "another version waiting". It offers promote, which leads to the
      displacement warning; before this it was reachable only through
      `supply decide`.
    - **FIXED, minor:**
      - A mistyped `--acknowledge` key is no longer blamed on a change
        that never happened. It says mistyped or changed, and gives the
        current key.
      - When the warning changes mid-decision, the terminal now says
        somebody else's decision changed it and shows what is new. Being
        changed twice now prints a message rather than exiting silently.
      - Commands print below the panel, one per line and unwrapped, so a
        copy picks up neither the border nor a line break.
      - The refusal after a `--yes` with a shown warning no longer
        repeats the warning.
      - The success message says what else was done ("X moved to
        superseded").
      - `--yes` help and the non-interactive hint mention `--acknowledge`.
      - The refusal on a rule into a substituted slot, and on an
        unconfirmed person, now gives a command to paste.
      - The stale `newest_promoted` docstring is fixed. The dead
        `len(found) > 1` branches in substitution and inheritance are
        gone.
      - `scripts/dev/tui_drive.py` answers a cursor-position query with
        the real cursor, not a fixed 1;1. The fixed answer made
        prompt_toolkit redraw from the top and wipe anything printed
        above a prompt, so a critic using the tool would wrongly report
        "no panel".
    - **LOGGED, not changed:**
      - The success panel still reads "promote recorded for ..." in
        lowercase.
      - Supplies in the panel are still named by id rather than by arrival
        date.
      - Refusal output still goes to stdout.
      - L3's window between the key check and the lock remains. It is
        harmless now that the slot is judged again under the lock.

113. **[done, 2026-10-05]** **[Pipeline & publishing]** **The delivery critic on
    REQ-PIPE-129 and the 081 census, and the CLI UX critic re-checking
    #112.** Each finding was verified against the code before it was written
    here. Keith answered the four that needed him the same morning
    ("Fix all three now"; "Narrow to move/rename").
    - **H1, FIXED** (failing test first): `mothman env reset-synthetic` failed
      on any database holding an inherited or substituted view. The new
      drop guard refuses a cascaded drop of a period view unless its own
      schema goes in the same statement, and the reset dropped schemas one
      at a time. It now drops them all in one statement.
    - **H2, FIXED** (failing test first): a demote naming a supply the period
      does not hold took the period's real table out under that supply's
      name. The decision log now refuses a demote of anything but the
      period's holder. A demote or reject whose table is missing is now
      loud and rolled back, as `supersede_promoted` already was.
    - **H3, FIXED** (failing test first, shown to fail on the old code): a
      substitution or inheritance was judged before taking its lock and
      never again, so a promotion in the gap left a view reading the
      newcomer under the old supply's name. Both are now judged again
      under the lock: the person's substitute and inherit, and the rule's
      inheritance at a period's birth. The rule's inheritance now records
      its view and its entry in one transaction.
    - **M1, FIXED on Keith's answer ("Narrow to move/rename"):** the event
      trigger refused every `ALTER TABLE` on a stood-on table, including an
      added column. That would have broken REQ-PIPE-130's schema bump once
      its `_manifest` views exist. It now refuses only `SET SCHEMA` and
      `RENAME TO`, read from the statement text, since the trigger cannot
      see the sub-command.
    - **M2, FIXED:** criterion 16's build warning printed only from the
      builders' `__main__`, which no `mothman` path runs.
      `census.build_warnings()` is now called by `mothman dashboard
      build-data`, by `rebuild` and by `pipeline run`.
    - **M3, FIXED** (failing test first): the census read the log and the
      catalogue as two statements, so a promotion committing between them
      was recorded as a stray. Both are now read in one REPEATABLE READ
      transaction.
    - **CLI re-check HIGH, FIXED** (failing test first): the substitution
      undo printed by #112 had no `--supply`. Pasted, it took the
      just-demoted supply and crashed with a traceback. It now names the
      supply stood on. `SubstitutionRefused` and `InheritanceRefused` are
      now shown as refusals, not tracebacks.
    - **CLI re-check MEDIUM, FIXED** (failing test first): a supply
      un-superseded after being displaced never showed as waiting, though
      the undo text says it returns to waiting. `_accepted_into` now counts
      a displacement's SUPERSEDE as leaving the period.
    - **CLI re-check MEDIUM, FIXED:** in the "another version waiting"
      state, "reject" and "supersede" now say the period keeps its promoted
      supply. Every supply-scoped confirmation names the supply by its
      arrival.
    - **FIXED, minor:**
      - The census banner compares dates on the asset's calendar, not UTC's.
      - The guard gate no longer calls an empty database "installed", and
        its column reads as a question, not a result.
      - A missing guard now names a remedy, the new `mothman supply
        install-guard`.
      - The session-start hook checks the guard wherever a qa schema exists.
      - A refusal that is certain now comes before the reason prompt.
      - The non-interactive hint at the confirmation names `--acknowledge
        KEY`.
      - "Recording - this waits up to 15s ..." is said before a decision
        that may wait on a lock.
      - An unknown person's refusal uses the same panel as every other
        refusal.
      - The inherited refusal starts with a capital.
    - **LOGGED, not changed:**
      - Views are still created and dropped with no census of their own (L4
        - criterion 13 says "wherever a table is moved").
      - `promote` takes its slot lock outside `_lock`'s sorted discipline.
        No deadlock pair was found (L5).
      - The NFR 6 source test's argument heuristic stays weak; the run-time
        refusal in `move_table` is the real guard.
      - `mothman supply queue --collection cp` ends in a traceback rather
        than accepting the shorthand.
      - The queue takes about 3 seconds to render.
      - "2 later period(s)" and "supply/supplies" pluralisation.

114. **[done, 2026-10-05]** **[Pipeline & publishing]** **The delivery critic on
    sprint 9 - REQ-PIPE-140 (a decision's own QA run), REQ-PIPE-141
    (re-file) and REQ-GHUB-142 (its warning).** Each finding was checked
    against the code before it was written here. None needed Keith: all are
    defects in the built behaviour against signed criteria, not changes to
    what was agreed. Fixed before sprint 9 was first committed.
    - **D1 (HIGH), FIXED** (failing test first): re-filing a SUPERSEDED
      supply moved its tables to staging but left it superseded. Every
      route then refused to promote it, and the re-file had still
      superseded the versions waiting in the target, so that period could
      end with nothing promotable. A re-file now ends a supersession:
      `supersession._latest` reads REFILE alongside supersede and
      un-supersede.
    - **D2, FIXED** (failing test first): a re-run's id was minted past
      `qa.run` only. An attempt that broke before its run opened held its id
      on `qa.owed_run` alone, so the next owed re-check took the same
      `__r1`, and its results would have replaced the first's. Ids are now
      minted past both, under an advisory lock.
    - **D3, FIXED** (failing test first): the warning said the target
      "reads the re-filed one from this decision on". A promoted version
      there stays until the re-filed one is checked and promoted (criterion
      9), and even an empty target only has it waiting. It now says which.
    - **D4, FIXED** (failing test first): the re-file was planned before
      the slot lock and never re-judged, so a version filed into the target
      in between was neither superseded nor named. The plan is now worked
      out again under both slots' locks, and a re-file whose consequences
      changed is refused, with nothing done.
    - **D5, FIXED** (failing test first): on the GitHub route a rejected,
      contested or inherited re-file was asked to confirm before being
      refused. Its refusals now come first, as on the terminal.
    - **D6, FIXED** (failing test first): a decision-triggered run's
      results named the run's own `__r1` key as the ARRIVAL that caused
      them. Every result of such a run now carries
      `reevaluated_after_decision`, and none carries the arrival key.
    - **FIXED, minor:**
      - An overlay that broke half-built left the re-run's view schema
        behind.
      - A held supply asked to be re-filed got an empty warning, then a
        refusal about two slots. It is now told to place it instead
        (failing test first).
    - **RECORDED AS UNMET, not fixed:** criterion 5's terminal half on
      REQ-PIPE-140. No terminal command shows a supply's verdict at all, so
      there is no reader to point at the newest run.
    - **LOGGED, not changed:**
      - Owed re-checks can pile up when a supply is re-filed back and
        forth: one per decision, each run against the current filing.
        Harmless, since each completes as its own run. REQ-PIPE-151's pass
        is where they are drained.
      - NFR 2 (time one run on the largest Child Protection table) is not
        yet measured.
      - The Birth Registrations re-run path is exercised only through the
        shared executor. The BDM fixture files nothing, so there is no
        end-to-end test of it.
    - **FOUND BY THE GATE, NOT THE CRITIC, FIXED** (failing test first):
      `sprint_state` read an `**Owns:**` paragraph one line deep, so a
      sprint whose list wrapped owned only its first line's requirements.
      Two delivery-sprint tags in `plans/supply-model.md` were wrong
      because of it. Sprint 11 was counted on four requirements of eleven.
      Sprint 26 had read `done` since 2026-09-27, when its own register
      says 96 of 112 criteria are met. Both now read `in-progress`, as
      counted. Worth knowing: a "done" sprint tag before today was checked
      against a short list.

115. **[done, 2026-10-05]** **[Pipeline & publishing]** **The CLI UX
    critic on the re-file (11eb18e), driving it for real** against a copy of
    the deployment database. Each defect below was checked against the code
    and, where it could be, reproduced in a failing test before it was fixed.
    None changes agreed behaviour, so none needed Keith.
    - **D1, FIXED** (failing test first): the target period was never
      checked. `2026-Q9` was accepted, recorded and re-checked. A re-file into
      a period the dataset's calendar does not have is now refused and names
      `mothman supply slots`. Tests mint `2099-` periods, which a conftest
      fixture counts as on the calendar; every real name is still judged by
      the real calendar.
    - **D2 and D3, FIXED** (failing tests first). This was the serious one.
      A period emptied by re-filing a WAITING supply out read "returned by a
      person", naming the supply that had left. The queue offered actions on
      it, and a reject there was recorded against the supply's OLD period
      while it waited in the new one. Three fixes:
      - The slot view now reads a slot emptied by a re-file whose supply is
        filed elsewhere as though nothing was decided there.
      - The decision log refuses a reject or demote naming a supply filed to
        another period, and names that period.
      - A supply re-filed into a period past the claim horizon was listed
        nowhere. Its period is now listed.
    - **D5, FIXED:** the re-check panel was green whenever the run completed,
      red verdict or not, and said only two run ids. It now says what the
      supply came out as against which period, and whether the gate promoted
      it, coloured by the verdict.
    - **D4, NOT REPRODUCED, OPEN:** re-filing a PROMOTED supply left a
      re-check that could not read its own table (`UnreadableOwnTable`). A
      real-tools test of exactly that path, into an empty period, passes
      (`TestAPromotedSupplyRefiledIsCheckedInItsNewPeriod`). The critic's
      case had a target that already held a promoted version, and its tree
      was an archive run without dbt on PATH. RETRIED AND CLOSED, 2026-10-05:
      on a copy of the schema-27 deployment, re-filing the promoted
      cp-carers supply of 2026-Q2 into 2026-Q1, which already held one, ran
      its owed re-check to completion (green, left waiting because the slot
      is filled - the correct outcome under `never`). Not reproducible on
      the real tree; taken as the critic's environment.
    - **FIXED, wording:**
      - The held-supply refusal now points at `mothman supply holds` (W1).
      - The supersede undo says what "out of the way" means (W3).
      - "Recorded" names the target period (W6).
      - The warning names what an already-filled target keeps reading (W7).
      - "re-file", never "refile", in what a person reads (W8, partly).
    - **LOGGED, not changed:**
      - The non-interactive hint for a re-file leaves out `--to-period` (W2).
      - The `--acknowledge` key wraps inside its panel (W4).
      - "Recording ..." prints before a refusal that needs no lock (W5).
      - The actor shows as an email rather than a name (W8).
      - "or point them elsewhere:" is unexplained (W9).
      - Library warnings leak into re-check output (P1).
      - `--collection cp` crashes, which predates this (P2).
      - The queue shows no supply ids (P3).
      - The Ctrl-C reason wording (P4).
      - The queue's silent pause (P5).
      - The re-file prompt offers no list of periods.

116. **[done, 2026-10-05]** **[Pipeline & publishing]** **The delivery
    critic on sprint 10 (8040a69)**, which drove the dashboard built from a
    copy of the schema-27 deployment in a real browser. Every finding was
    checked against the code before it was written here.
    - **D1 (HIGH), FIXED** (failing test first): "newest cause wins" ordered
      a supply's runs by a mix of time scales. A decision's run was ordered
      by the decision's historic effective time; an arrival's run by the
      batch's WALL CLOCK, which a replay stamps years later. So in any
      replay a re-evaluation could never outrank the arrival it
      re-evaluated (REQ-PIPE-121 criteria 3 and 10). It showed a false "Red
      promoted ... turned red 5 October 2026" on cp-investigations 2024-Q3.
      An arrival's run is now ordered, and dated, by its supply's receipt
      instant. The same fault stamped a re-check's gate decision with the
      wall clock; it now takes effect when its cause did (failing test
      first).
    - **D3, FIXED** (failing test first): a supply promoted while already
      red got no label, because every point before the promotion was
      skipped. It now reads "Red promoted - promoted while red".
    - **D4, FIXED** (failing test first): a legacy `?asof=` link was
      honoured but stayed in the address bar until the date was changed.
      It is now rewritten on arrival.
    - **D5 (security), FIXED:** `manifest_for` is SECURITY DEFINER with
      `search_path = pg_catalog` alone, so pg_temp was searched first and a
      caller's temporary `pg_class` could spoof the listing (verified by the
      critic). It is now `pg_catalog, pg_temp`. Schema 28.
    - **D6, FIXED:** the knock-on read an INHERITED table as holding
      nothing, so every reader of it looked stale and ran its tools again.
    - **D2, FOR KEITH:** the status pill on a supply-history row and the
      red-promoted label answer different questions, and they can
      disagree on screen. The pill is the supply's arrival verdict; the
      label is the newest result per check. One was a Green pill with
      "Red promoted", and that one was D1's false red. Others were a Red
      pill with no label, where later re-evaluations went green.
      REQ-DASH-126 criterion 4 asks for the promoted-on verdict beside the
      current one, but does not say which of the two the PILL is. Which
      should it be, for a promoted supply?
      **ANSWERED 2026-10-06 (Keith): the newest result.** Built the same
      day - `supplyRowStatus`, with "Arrived <status>" beside the pill when
      the two differ; recorded on REQ-DASH-126.
    - **D7, LOGGED:** REQ-DASH-127's NFR, which collapses superseded
      versions under the version that superseded them, is not built. They
      are flat rows. Recorded on the requirement.
    - **D8, FOR KEITH (wording):** REQ-PIPE-123 criterion 3 says "as one
      decision in one transaction". The build writes TWO entries, supersede
      and promote, in one transaction, as REQ-PIPE-128's displacing
      promotion does. Amend the criterion, or record the replacement as
      one entry?
    - **LOGGED, latent:** a move queued by a nested decision whose
      savepoint later rolls back would still be owed. No caller today
      catches inside an outer decision transaction.
    - Coverage gaps the critic named and that are still open: no
      real-browser test of red promoted (REQ-DASH-126 NFRs 1 and 3); no
      cascade test; no test of an amber replacement owing an
      acknowledgement.

117. **[in-progress, 2026-10-05]** **[Data generation]** **The delivery
    critic on sprint 11 (8fb2229)**, which reviewed an exact archive of the
    commit against a copy of the rebuilt deployment and drove the built page
    in a real browser. Each finding below was checked against the code
    before it was written here.
    - **D1 (MEDIUM), FIXED** (failing test first): the dataset page printed
      a decision's actor as recorded - an email - so a scripted decision
      read `scripted-history@synthetic.invalid` (REQ-GEN-135 criterion 12).
      Every person's mark, rejection and acknowledgement is now shown by
      NAME from contract/people.yaml, as REQ-PIPE-147 criterion 7 already
      does for who filed a delivery. tests/test_not_supplied.py asserted
      the raw email and was updated on purpose.
    - **D2 (MEDIUM), FIXED** (failing test first): an old `?panel=scenarios`
      link stayed in the address bar and took over every later reload and
      copied link. It is now dropped once it has opened the tab.
    - **D3 (MEDIUM, security, latent), FIXED** (failing test first): the
      "playback only" lock lived in the person lookup, so a caller holding
      the synthetic record could reach `filing_decisions.apply()` directly
      and be accepted. The decision path now refuses it on its own (NFR 2).
    - **D4 (LOW), FIXED** (failing test first): a decision timed exactly at
      an arrival's receipt played after it; criterion 3 says "at or after".
    - **D5 (LOW, FOR KEITH)**: the replay applies scripts in PROCESSING
      order, while rule promotions are stamped receipt + an invented lag of
      one hour to three days (`promotion.effective_at_for`). Seven
      decisions have an effective instant earlier than the row recorded
      before them, and on TS-47's own day the late file's promotion takes
      effect two days after the on-time file arrived, so 09-08 shows two
      waiting versions for two days on the asset timeline. Harmless for the
      one script planted; a hazard for parked TS-45/TS-53 shapes. Whether
      the replay should order by asset time (and what the lag is for) is a
      design question.
    - **D6 (LOW-MEDIUM, FOR KEITH)**: two definitions of a supply's
      "current" run disagree - `supply_status.runs_about` (asset time, the
      #116 D1 fix) puts the stalest re-evaluation of cp-investigations
      2024-Q3 last, `qa.supply_current_run` (run instant) the freshest. No
      visible effect today (all pass). A load-caused re-check would also
      sort at receipt, below every sibling re-evaluation (latent - nothing
      owes one yet).
    - **D7 (FOR KEITH)**: `recheck._cause_instant` stamps a gate promotion
      at its cause decision's instant with no `min(now, ...)`, so in a live
      deployment a re-check run hours later is recorded as in place before
      the checks justifying it ran. Right for a replay, questionable live.
    - **D8 (LOW), OPEN**: `redPromotedBadge` says "promoted while red" for a
      supply promoted red, turned green, then red again, losing the
      "turned red <date>" wording. No red promotion exists in the data;
      read from code only.
    - **RECORDS CORRECTED**: REQ-GEN-136 criterion 14's second clause (the
      register names the settings in force where a planted scenario lands)
      is now met for TS-41 and TS-47. Its TS-48/49/51 unmet entries named
      the wrong blocker - the arrival shape already exists in 2024-Q3; what
      is missing is a red outcome, the #63 blocker. REQ-DASH-139 now records
      criterion 3's gap (31 of 66 entries name no requirement - the older
      register entries cite none) and gained NFR 2's click-through test.
    - **ALSO NOTED**: the history already holds two naturally occurring
      "promoted, awaiting acknowledgement" BDM supplies (09-12, 09-13) -
      TS-44's shape, unplanted. `load()` defaults a script's `supply` and
      `after_hours` silently and `validate` crashes on a non-number (minor,
      open). Determinism across two replays (criterion 7) was not verified.

118. **[in-progress, 2026-10-05]** **[QA checks & contract]** **The delivery
    critic on sprint 12 (4305585, f8f209e)** - file checks (REQ-QAC-096),
    their page section (REQ-DASH-097), TS-12/TS-56, and #117's D1-D4. It
    reviewed an exact archive against a copy of the rebuilt deployment and
    drove the built page in a real browser. Each finding was checked
    against the code before it was written here; every fix had a failing
    test first, confirmed failing.
    - **D-A (MEDIUM), FIXED**: the date page chose the newest file by
      comparing receipt times AS TEXT, and receipts carry different UTC
      offsets (injected supplies +08:00, the rest +00:00) - so on BDM
      2026-09-08 it showed 11:00 Perth's file over 14:04's. Now compared as
      instants (tests-js/file-checks.test.js), and the panel dates a receipt
      on the asset's calendar rather than by slicing the stored string
      (tests/test_file_check_panel.py, which is also the panel's first
      Python test).
    - **D-B (MEDIUM), FIXED**: on TS-12's own date the page said "could not
      be loaded ... until a person resolves it" and directly below "Nothing
      is waiting for a person here". The blocker opened at the supply's
      receipt (REQ-DASH-148 criterion 3) but the outstanding ITEM was
      stamped with the load record's wall clock - the night of the rebuild -
      so the page dropped it as not yet observed. Both now take the instant
      from one function, `dataset_blockers.refused_opened_at`. Not
      re-routed to Keith: criterion 3 already says receipt, so this is the
      item catching up with a signed criterion rather than a new decision.
    - **D-C (LOW-MEDIUM), FIXED**: staging a trial or reference run screened
      its file and registered a `qa.run` that nothing completed, so
      `incomplete_runs()` listed it as crashed for ever. `trial.discard` now
      removes the file-check rows it added and the run row when that is all
      it holds; a trial whose own checks were recorded keeps them.
    - **D-D (LOW, accessibility), FIXED**: each file-check row's aria-label
      replaced its accessible name, so a screen reader heard neither the
      status nor the finding. The hint is now sr-only text inside the
      button. The DATA-check rows use the same aria-label pattern (template
      ~5500) and were NOT changed tonight - same defect, older code; open.
    - **D-E (LOW, privacy edge), HALF FIXED, HALF FOR KEITH**: (a) FIXED - a
      repeated header name the contract does not list may be a row value,
      so it is now counted ("1 column name the contract does not list"),
      never quoted (criterion 14). (b) FOR KEITH - the header-row check
      passes when the first line names ANY contract column, so a headerless
      file whose first row holds a value equal to a column name passes, and
      the loader takes that row for the names: a false green. A "more than
      half" rule was tried and REVERTED the same night: it refused a file
      for MISSING columns, which is a data check's question (REQ-QAC-096
      criterion 2), and broke every test fixture whose header is a subset.
      What makes a first line "a header" is a design question.
    - **D-F (LOW), FIXED**: Python's csv field limit (128 KiB) refused a
      file the loader would read, reported as "could not be split". The
      limit is lifted; that branch now has a test.
    - **D-G (LOW, wording), FIXED**: a refusal names the check as the page
      does ("Fields per row", not `fields_per_row`) and ends its sentence,
      so the item no longer reads "...were expected Nothing can read"; a
      refused file's section no longer claims its checks "never change the
      status of the checks below" beside a red dataset. FOLLOW-ON, caught by
      the gate the same night: ending the reason's sentence made the
      blocker, which adds its own full stop, read "were expected.. Nothing" -
      fixed with a failing test first (tests/test_dataset_blockers.py).
    - **D-H (LOW), FIXED**: `missing_tools` counted file-check rows, so a
      refused file's dataset was reported missing every data tool.
    - **#117 D1 CAVEAT, FOR KEITH (privacy)**: `people.display_name` falls
      back to the RECORDED identity for anyone not in contract/people.yaml,
      so an unlisted person's email would be published on the page. Not
      changed: whether to show "someone not on the list", refuse, or keep
      the identity is a privacy call.
    - **NOT VERIFIED BY THE CRITIC**: a refused BIRTH REGISTRATIONS file end
      to end (none exists in the history); the authoring-rules compliance
      of the six checks' prose; D3/D4 at runtime.

119. **[in-progress, 2026-10-06]** **[Pipeline & publishing]** **The delivery
    critic on sprint 13 (91fbd85)** - REQ-PIPE-093, 107, 146 and REQ-TEST-114,
    #118's fixes and the TS-56 move. Reviewed from an exact archive against a
    copy of the deployment database, the TUI driven in a real pty. Checked
    against the code before it was written here; each fix had a failing test
    first, confirmed failing.
    - **D1 (MEDIUM-HIGH), FIXED - a defect against a signed criterion, so not
      routed as a choice**: `mothman env mark --confirm <id> --replacing ...`
      re-marked a database with no terminal at all, production included, in
      both directions - REQ-PIPE-093 criterion 6 says no flag skips the typed id
      for a re-marking. `--confirm` now stands in for typing ONLY on an unmarked
      database (the setup scripts' whole need); replacing an identity needs a
      person at a terminal typing out what is being replaced, and `--replacing`
      is gone. The refusal no longer prints the exact text to copy back
      (criterion 3).
    - **D2 (MEDIUM), HALF FIXED, HALF FOR KEITH**: `supply tidy`, `supply
      discard-sample`, `env reset-synthetic` and the "originally received"
      prompt now name the environment in the prompt (REQ-TEST-114 criterion 4).
      WHETHER tidy and discard-sample should also need production's typed id,
      with `--yes` unable to skip it, is outside REQ-PIPE-093 criterion 4's
      list - a question for Keith (morning report).
    - **D3 (MEDIUM, test gap), FIXED**: the production confirmation was tested
      only on `confirm_change` alone - swapping the flows' calls back to a plain
      yes/no passed every test. Two flow-level tests now fail under exactly
      those mutations (tests/test_cli_filing_tui.py).
    - **D4 (LOW-MEDIUM), FIXED**: the image-tag gate passed an untagged,
      digest-pinned, templated or `postgresql`-named image, and never looked at
      a job's own `container`. Now every PostgreSQL image is found and one whose
      major cannot be read is an error.
    - **D5 (LOW), FIXED**: the version refusal appended a redacted DSN; it now
      carries none, as the identity refusal already did.
    - **D6 (LOW), PARTLY FIXED**: the press-any-key prompt carries the toolbar;
      the "originally received" `click.prompt` names the environment in its
      text instead (a click prompt has no toolbar). Progress printed with no
      prompt showing still names nothing - open, minor.
    - **D7 (LOW), FIXED**: four tests that could pass vacuously now assert what
      they claim (the id was asked for; the command succeeded; at least two CI
      jobs were checked, found by image; the PROBE statement itself).
    - **D8 (LOW), FIXED**: the percent-encoded form of a password is scrubbed
      too.
    - **D9 (LOW), FIXED**: a ticket repository with no owner is refused before
      connecting, as the ticket service would refuse it mid-run.
    - **D10 (FOR KEITH)**: production hand-filing asks "keep this?" (y/N) and
      then the typed id. A recorded decision accepts that; whether the typed id
      should replace the y/N is a choice (morning report).
    - **NOT VERIFIED by the critic**: nothing in a browser, CI for 91fbd85, and
      REQ-TEST-114 criterion 9 (the cast).

120. **[in-progress, 2026-10-06]** **[Pipeline & publishing]** **The delivery
    critic on sprint 14 (827636e)** - REQ-PIPE-151, REQ-PIPE-086, REQ-TEST-150,
    REQ-PIPE-093 criterion 15 and #119's fixes. Reviewed from an exact archive,
    with every write against copies of the deployment database (sandbox-,
    production-marked and empty); the TUI was driven in a real pty. Each
    finding was checked against the code before being written here, and each
    fix had a failing test first, confirmed failing.
    - **D1 (MEDIUM-HIGH), FIXED - against signed criteria (151 c6, 086 c8)**:
      a terminal keep took no arrival lock, so a keep and a processing pass
      could process one arrival at once. Reproduced by the critic: each run
      dropped the other's run schemas, and both failed. Now every hand-filed
      route (`run_arrivals`, both collections) processes each arrival under
      its advisory lock. An arrival another process holds is refused BEFORE
      filing, naming why. Once the lock is held the record is read again: an
      arrival a pass finished while the person was answering prompts is
      refused rather than recorded twice. Refused rather than waited for,
      because the other process may be a whole pass long - PROVISIONAL.
    - **D2 (MEDIUM), FIXED - against signed criteria (151 c14, c20)**: a
      failure outside the per-arrival `try` was an uncaught traceback, which
      exits 1 (criterion 20's "red"). The stages affected were setup, the
      delivery record, owed work and tickets. A staging failure also aborted
      the whole pass. Now: a setup failure ends the pass with exit 2. A staging
      failure is that arrival's failure, holding back only its own collection.
      Owed-work and ticket failures are recorded as failures (exit 2), and the
      rest of the pass still completes. `run_pass` had no automated test; it
      now has eight, covering order, both kinds of collection hold-back, a
      locked arrival, every pass-level stage failing, and owed work.
    - **D3 (MEDIUM), FOR KEITH**: tickets that could not be reconciled (as
      opposed to the reconciler raising, now covered by D2) change neither the
      exit status nor the summary. Criterion 20 reads "any stage failed", but
      the slot state is durable and the next pass retries, so either reading
      is defensible (morning report Q1).
    - **D4 (MEDIUM), FIXED - REQ-TEST-150 c1/c2/c5 on a route 086 c9 makes
      kept**: a kept synthetic arrival printed the check table and "Recorded
      N results", but nothing the lifecycle decided. Both collections now end
      on the lifecycle summary, interactive or not.
    - **D5 (MEDIUM), FIXED - 086 c14**: in the TUI, a kept file that filing
      refused, turned into a trial, stopped at once saying "pass
      --reference-file". That is a trial offered and then not runnable, with a
      flag named to a person in a menu. At a terminal the reference is now asked
      for; with no answer, nothing is run and the message says so. Without a
      terminal the flag is still the remedy. Covers both BDM files and CP folders.
    - **D6 (MEDIUM-LOW), FOR KEITH**: a kept folder silently leaves behind files
      no dataset recognises. A renamed extract is "a supply on the floor", which
      the batch warns about and the terminal does not (morning report Q4).
    - **D7 (LOW-MEDIUM), FIXED - 151 c3**: a refusal was skipped if the supply
      had EVER been promoted or withheld. So a supply that was promoted,
      demoted by a person, and refused on re-check left no entry, and the
      kept-run report kept saying "promoted". It now looks at the LATEST gate
      outcome or move for the supply: skip after a promote or a withheld, or
      after the same refusal; record after a move (demote, re-file, reject,
      supersede) or a different refusal. A refusal can therefore be recorded
      again after an intervening different one. No rebuild was done for this
      change; the deployment database's history was written under the old rule.
    - **D8 (LOW), FIXED - 150 c1**: the aggregated report rewrote each dataset
      as "its dataset", and "Kept." named only the first arrival. Shared lines
      now list the datasets beside the count (eight named, then "and N more").
      A multi-arrival keep names every arrival.
    - **D9 (LOW), FOR KEITH**: an arrival whose run never completed is re-run
      under its own run id, replacing its partial results. This is crash
      recovery, but it reads against 086 c8's "SHALL NOT replace any result
      already recorded" (morning report Q2).
    - **D10 (LOW, security), FIXED**: #119 D8 scrubbed only the decoded password
      and one canonical encoding of it. A partly-encoded or lowercase-hex
      spelling went through. The scrub is now one pattern matching every
      character either literally or percent-encoded in either case.
    - **D11 (LOW), FIXED**: `--table` still said the other five tables
      "auto-pull" from the last promoted run, which is now true only for a
      trial. `--reference-run-id` still described a default that REQ-QAC-108
      removed (that one predates this sprint).
    - **D12 (LOW), FOR KEITH**: a locked arrival does not hold back later
      arrivals of its collection, as a failure does. This is now reachable
      through D1's fix: a person keeping one arrival while a pass runs (morning
      report Q3).
    - **D13 (LOW), FIXED, except one part**:
      - Each arrival's `--- run ---` header printed twice; fixed.
      - A synthetic keep of a run id recognition does not know raised a bare
        `StopIteration`; it is now refused with the run named.
      - NOT CHANGED: `backlog.unprocessed` has no caller. Criterion 18 required
        amending it, and it now reads `processing_pass.recorded()`, so there is
        one definition rather than two. Deleting a module owned by REQ-PIPE-061
        is a separate call (morning report).
      - NOT CHANGED: the pass's own output is not REQ-TEST-150's aggregated
        report (151's observability NFR) - open, minor.
    - **D14 (NFR note)**: every pass recognises the whole delivery tree and
      records every delivery. That costs in proportion to history on disk
      (about 5 seconds at 66 deliveries), not to what is unprocessed. Recorded
      here, not changed.
    - **OUTSIDE THIS SPRINT, FOR KEITH**: a trial leaves a completed `qa.run`
      and its `check_result` rows behind (`run_by` `trial:not-recorded`, which
      `check_result_visible` shows), while it prints "nothing was recorded".
      `trial.discard` says so on purpose. That contradicts REQ-PIPE-103
      criterion 6. It predates 827636e, and which one is right is a question
      about a signed requirement (morning report).
    - **WEAK TESTS NOTED, partly addressed**: the critic called out two tests:
      `TestTheCommandGeneratesNothing` (a source grep) and the help-codes
      substring match. Both stand. D1's and D2's new tests cover what the lock
      tests never reached.
    - **NOT VERIFIED by the critic**: the S3 routes live; a real held or
      contested keep; an owed re-check (as opposed to a re-evaluation); a
      configured ticket reconciliation succeeding; `--all-checks`; the
      dashboard's display of `promotion-refused`; CI for 827636e.
    - **KEITH'S ANSWERS, 2026-10-06**: D3 -> exit 2 (a ticket failure is a
      failed stage); D9 -> same run id, with c8 amended to except an
      incomplete run; D12 -> a locked arrival holds back its collection;
      D6 -> keep the recognised files and name each one left behind; D13's
      backlog.unprocessed -> deleted; the trial finding -> REQ-PIPE-103 c6
      stands, so a trial's run and results are discarded.

121. **[in-progress, 2026-10-06]** **[Dashboard UI]** **The dashboard visual
    critic on a17d6e8** - the first visual pass since 2026-09-24, over the
    supply history (REQ-DASH-126/127/133), the file-check section
    (REQ-DASH-097), the Scenarios tab (REQ-GEN-135) and the cross-table rows.
    Real Chromium, 1440 and 390 wide, light and dark, measured with
    getComputedStyle. D1 and D6 checked against the template before being
    written here.
    - **D1, FIX AS POLISH**: the "Red promoted" badge uses `var(--red)`,
      which is not a token (`--bad` is), so it renders ink-on-blue with no
      red at all.
    - **D2, FOR KEITH (Q2)**: the badge is one nowrap pill carrying a whole
      sentence - 598px wide, wrapping Arrived to three lines, scrolling the
      table 3.2x on mobile.
    - **D3, FOR KEITH (Q1)**: supply-history cycle tables misalign (measured:
      Outcome's left edge swings 499px between cycles) - road-testing #11
      confirmed. The blocker table's Arrived also uses a different font.
    - **D4, FIX AS POLISH**: blocker and gap rows show a pointer and hover
      fill but do nothing; a dead Rows column and an empty unlabelled one.
    - **D5, FOR KEITH (Q3)**: dark-mode status pills fail contrast - Red
      2.61:1, Green 4.43:1, against 4.5:1. A different token from #49's
      declined debt.
    - **D6, FIX AS POLISH**: `.scope-check .label .ds` is an inline span, so
      its margin does nothing and the tool id runs into the description
      ("soda:row_countThe number of rows..."); 7px past the viewport on one
      mobile page.
    - **D7, FOR KEITH (Q4)**: the collection page's cross-table rows show only
      the check name - nine "Client reference" rows, nothing to tell which
      table pair or tool (road-testing #14 confirmed).
    - **D8, FIX AS POLISH**: Scenarios link chips carry an inline
      `font:inherit` that overrides `.pill.sm` - 15px, clipped up to 58px at
      390 wide, 29px tap target.
    - **D9, FIX AS POLISH**: an "In the data" pill on all 31 scenarios,
      including the 23 with no data, drawn in the dashed "No data" style.
    - **POLISH JUDGEMENTS**: a 2,708px queue notice above the agency cards;
      spaced hyphens reading as hyphenated words; unbounded line lengths;
      mixed table header styles; a held supply reading Red in one table and
      Green/Waiting in the next.

122. **[in-progress, 2026-10-06]** **[Pipeline & publishing]** **The delivery
    critic on 96813c1 and a17d6e8** (the #120 answers and the twelve standing
    answers, qa schema 31). 413 tests across 15 modules passed in its own
    archive; every finding reproduced against copies of the deployment.
    - **D1, FOR KEITH (Q5)**: during `env reset-synthetic`, another
      connection's probe can read the newly created `qa.identity` under an
      older snapshot and is refused "this database carries no recorded
      identity - mark it" - fails closed and brief, but sends a person to
      re-mark a marked database. Recommended: drop every qa table except
      `identity` rather than the schema.
    - **D2**: the reset rewrites `marked_at`. Fixed by D1's recommendation.
    - **D3, FOR KEITH (Q6)**: `decision_log.follows()` can return an instant
      after now (clock skew, or a future-dated decision). Recommended:
      `min(now, ...)`, as effective_at_for already does. Latent.
    - **D4, FOR KEITH (Q7)**: REQ-PIPE-081's decision says the lag cap changes
      nothing live - wrong when a live pass catches up a backlog, since the
      pass records every delivery first. Recommended: keep the behaviour,
      correct the decision text.
    - **D5**: a role that lost its grants after a reset is refused with an
      identity message rather than a grants one. Wording; fails closed.
    - **D6, FOR KEITH (Q8)**: supply_current_run's tie-break sorts run keys as
      text (`__r10` before `__r9`). Latent - nothing makes load-caused
      re-runs yet.
    - **COVERAGE AND TRACEABILITY**: several new functions are missing from
      their requirements' `implemented_by` (follows, next_receipt,
      confirm_drop, decide_keep, reset, inherit_into); no test fails if the
      `before=next_receipt(...)` argument is removed from the orchestrators;
      two of this morning's tests assert a flag or source text only. FIX.
    - **CODE QUALITY**: db_identity's docstring says qa_store's DDL creates
      the table (it does not); `_KEEP_TYPED` is module state passed between
      two functions. FIX.
    - Verified sound: the reset keeps the identity under a failure inside its
      transaction; no code still reads the old database settings; the header
      rule refuses no real header in the 152 delivered files; the lag cap
      never moves a promotion before its own receipt.

123. **[in-progress, 2026-10-06]** **[Dashboard UI]** **The dashboard UX
    critic on a17d6e8** - everything since #110. Real Chromium, desktop and
    mobile, cross-checked against the record with `mothman supply`.
    - **A1 (HIGH), against REQ-DASH-126 c1/c3**: on a date when the one red
      promoted supply is in place but a newer one awaits a decision, the
      dataset reads Green and "Red promoted" appears only in collapsed
      history; the agency card never names the kind. FOR KEITH (Q9) on where
      it surfaces.
    - **A2 (HIGH), against REQ-DASH-133 c6/c9**: on any past date, held
      supplies drop out of the queue and the agency count while the dataset
      row still says Held - a hold's observed instant is the replay's wall
      clock. Same family as #116 D1. A DEFECT.
    - **A3 (MEDIUM-HIGH), against REQ-DASH-127 c1**: "Superseded by the
      supply received <day>" cannot identify which, on a day with several
      supplies. A DEFECT.
    - **A4 (MEDIUM), against REQ-DASH-097 c4**: the as-of view leaks today -
      a file's history lists later files; "waiting Nd" counts to today.
    - **A5 (MEDIUM)**: "results below are the newest supply" sits above tiles
      that all read No data - #110 H3's fix applied to one of its two causes.
    - **B1 (HIGH), FOR KEITH (Q10)**: supply history still groups by the old
      red-then-green resupply chain, now contradicting the slot model on the
      same page.
    - **B2 (HIGH), FOR KEITH (Q11)**: the dashboard's "waiting for a person"
      leaves out the red supplies awaiting a decision that the terminal's
      queue lists - about 20 in Child Protection.
    - **B3, FOR KEITH (Q12)**: the headline count and the card counts use
      different units.
    - **B4, FOR KEITH (Q13)**: a scenario jump silently moves the whole
      dashboard to a past date, and Back does not undo it.
    - **B5-B9, POLISH**: queue items are dead ends; the Scenarios prose
      disagrees with the data and shows reviewer notes; the Outcome column
      clips on mobile; repetition and REQ ids in reader text; "Show all
      history" not kept in the URL.
    - **CLI SIDE-FIND**: `mothman supply queue --collection cp` dies with a
      raw UnknownDatasetError traceback.
    - Verified sound: SPA basics (titles, focus, real links, Back, cold
      deep links); REQ-DASH-097's file-check section; REQ-DASH-133's gap
      grouping; promotion-refused correctly kept off the page.

124. **[in-progress, 2026-10-06]** **[Testing & dev tooling]** **The CLI UX
    critic on sprints 13-14 and a17d6e8**, driving the real TUI in a pty
    against sandbox-, production- and unmarked copies of the deployment.
    - **D1 (HIGH), A DEFECT OF THIS MORNING'S #119 D10 FIX, confirmed in the
      code**: production asks for the typed id TWICE on every keep.
      decide_keep() is called again inside filing with keep=True, and resets
      the "already typed" flag before filing reads it. The test written for
      it asserted the flag alone and never drove the flow - the weak,
      defensive kind of test plans/running-thoughts.md #67 is about.
    - **D2 (HIGH), A DEFECT, FOR KEITH AND ANSWERED**: a file REFUSED at load
      still had all four tools run - against the period's existing promoted
      table - recording 78 passes under its run, and the unloadable file
      SUPERSEDED a real waiting supply.
    - **D3 (MEDIUM)**: the kept-run report says "promoted - every check passed
      or warned" under a table showing two reference-gap reds.
    - **D4-D8 (MEDIUM to LOW)**: the non-interactive fallback names a
      `--keep` flag that does not exist; an empty fallback-trial reference
      ends the whole TUI session; the production no-terminal refusal reads
      "use the flag-based form... cannot be confirmed by a flag"; the
      multi-arrival progress bar counts past its total (7/5); a repr in
      discard-sample's error.
    - **UX JUDGEMENTS**: the Check column shows only the shared
      "data-asset-1.registry-services.civil-..." prefix at normal widths;
      raw Python UserWarnings with source paths on every pass; a ticket
      outage prints 590 lines; a kept folder names its left-behind files only
      after the keep and into the spinner; an unplaceable file is refused only
      after "originally received" is answered; the keep prompt still calls
      the delivery log "this repository's"; an identity mismatch in the TUI is
      titled "Unreachable"; the no-environment first screen gives no example;
      `pipeline process` does not say what is red; times in UTC in one
      refusal; REQ ids and design history in errors and help; a stale
      ENGINE_TAG (dbt-duckdb); the publish offer only on the synthetic route.
    - Works well: process discoverable and its exit codes stated; the
      toolbar on every prompt; production confirmations for process and tidy;
      env mark's refusals; keep before reference; recorded arrivals refused
      naming --trial; the lifecycle report's wording.

    **KEITH'S ANSWERS TO #121-#124, 2026-10-06** (13 + 4 questions):
    supply history keeps resupply chains but NEVER ACROSS A PERIOD, with
    aligned columns (over grouping per period); the dashboard's "waiting for a
    person" INCLUDES red supplies awaiting a decision, grouped per dataset;
    Red promoted surfaces in the dataset header and as a kind on the agency
    card, a short pill with its sentence beneath; dark-mode red and green
    lightened to clear 4.5:1; the cards count what the queue counts; a
    scenario jump shows a "viewing <date> for <scenario> - back to today" bar
    and Back undoes it; cross-table rows name their source table and tool;
    the reset drops every qa table except identity; follows() never returns
    a future instant; the live-backlog lag cap stays and REQ-PIPE-081's
    decision is corrected; the current-run tie-break orders by run instant
    before key, now; a REFUSED FILE records its file-check verdicts only, runs
    no tool and supersedes nothing; a promotion past gap-reds names them;
    terminal tables show `column.check`; a mistyped production id gets one
    retry before becoming a trial. Defects and polish are fixed without
    further sign-off; each defect with a failing test first.

    **CHUNK A, THE DEFECTS - FIXED 2026-10-06**, each with a failing test
    first:
    - #124 D1: `decide_keep()` now returns a `Keep` decision carrying whether
      the id was typed, and returns one passed back in unchanged, so the
      filing step reads how the first decision was made instead of a module
      flag the second call reset. The new tests drive the real filing step.
      Keith's one-retry answer went in at the same time.
    - #124 D2: `own_table.why_unreadable()` now answers REFUSED before asking
      whether a view exists, as CONTESTED already did, so a refused table
      that fell through to the period's promoted one no longer runs the
      tools. `supersession.supersede_earlier()` returns nothing for a newer
      supply refused at load. TS-12's deployment record still shows the old
      behaviour until the next rebuild.
    - #123 A2: a held supply's queue item is observed at its receipt, as
      `dataset_blockers` already did, not at the pass's wall clock.
    - #123 A3: "superseded by the supply received" names the receipt instant.
    - #123 A4: on a past date a file check's history stops at that date, and
      a wait counts to it (`waitedInPlaceOn()`); the default date keeps the
      built figure.
    - #123 A5: the verdict line is withheld where the date on show blanks
      the tiles (`noDataInPlaceOn`), the cause #110 H3 missed.
    - #123 CLI side-find: every `supply` command's `--collection` is
      validated, naming the known collections, and takes bdm/cp as `pipeline
      run` does.

    **CHUNK B, KEITH'S ANSWERS - BUILT 2026-10-06**, each recorded as a
    decision on the requirement it belongs to:
    - #122 D1/D2 (REQ-PIPE-107): the reset empties the qa schema of
      everything but `identity` and never drops that table, so marked_at
      stays and no probe meets a table newer than its snapshot.
    - #122 D3 (REQ-PIPE-140): `follows()` is capped at now.
    - #122 D4 (REQ-PIPE-081): the decision text that said the lag cap changes
      nothing live is corrected; the behaviour stays.
    - #122 D6 (REQ-PIPE-140): `supply_current_run` breaks a tie by
      run_instant before run_key. **qa schema 32.** The sandbox `supply`
      database had the view hand-applied (the code never migrates in place);
      its next rebuild makes that moot.
    - #124 D3 (REQ-QAC-108): a promotion past gap reds names them in its
      reason; `gap_reds()` shares the gate's own contributing-check rule.
    - #124: terminal report tables show `column.check` (`check_label()`).
    - #123 A1 / #121 D1, D2 (REQ-DASH-126): a short Red promoted pill with its
      sentence beneath, in the dataset header, and a kind on the agency and
      collection cards. D1's `var(--red)` went with it.
    - #123 B2, B3 (REQ-DASH-133): supplies awaiting a decision are queue
      items, one per dataset, from `filing_queue.awaiting()`; the cards count
      queue items (`gapItemCount()`). A needs-action item makes its card read
      as needing action whether or not it blocks.
    - #123 B1 / #121 D3 (REQ-DASH-127): a chain never crosses the period its
      supplies are filed to (`recorded_arrival` now carries the slot), and
      every cycle table shares fixed column widths.
    - #123 B4 (REQ-DASH-139): a scenario jump pushes an entry carrying the
      date it left, shows a "Viewing <date> for <scenario>" bar with Back to
      today, and popstate restores the date.
    - #121 D5: dark-mode `--good`/`--bad` lightened to #14B47A/#EF5A6F
      (5.64:1 and 5.25:1 on their pills), held there by
      `tests-js/status-contrast.test.js` in both themes.
    - #121 D7 (REQ-QAC-037): cross-table rows name their table, column and
      tool. #121 D6 (`.ds` display:block) went in alongside, being the same
      span.

    **CHUNK C, POLISH AND TRACEABILITY - 2026-10-06.** Fixed:
    - #124 D4: the non-interactive fallback names `--commit`/`--trial`, not
      a `--keep` that does not exist.
    - #124 D5: a ClickException inside any main-menu flow is shown and the
      menu carries on, rather than ending the session - fixes the empty
      fallback-trial reference and every other refusal of its kind.
    - #124 D6: production with no terminal raises `NeedsATerminal`, which
      says to run it from a terminal and no longer points at a flag form.
    - #124 D7: the progress bar counts each arrival's own steps
      (`StepCounter`) and names the arrival, so it never reads 7/5.
    - #124 D8: `UnknownDatasetError` prints its message, not its repr.
    - #124 judgements: the keep prompt calls the log "this asset's recorded
      delivery log"; the dbt ENGINE_TAG names dbt-postgres (old tag still
      mapped); an unreadable log is titled "Decision log not available".
    - #121 D4: blocker and gap tables are static (no pointer, no hover) and
      lost the dead Rows and unlabelled columns. #121 D8: scenario chips keep
      `.pill.sm`'s size and wrap. #121 D9: an unplaced injected scenario
      says "Planned for the data", in the tag style.
    - #123 B5: each queue item naming a dataset links to it. B7 (Outcome
      clipping on mobile) is answered by the fixed-layout tables, which
      scroll at phone width rather than clip.
    - #122 traceability: `implemented_by` and `linked_tests` added for every
      new or named function; `tests/test_promotion_waits_for_next_receipt.py`
      drives both orchestrators' `promote_after()` and was shown to fail with
      `before=` removed; db_identity's docstrings no longer say qa_store
      creates the table or the reset re-marks it.

    **LEFT AS THEY ARE, and why** - none is a defect, each is a judgement
    better made with the next road-test than guessed now:
    - #122 D5 (a role without grants after a reset is told about identity,
      not grants): fails closed; the right message needs the grants model
      REQ-PIPE-092 is still settling.
    - #123 B6 (Scenarios prose disagrees with the data, shows reviewer
      notes), B8 (repetition and REQ ids in reader text), B9 ("Show all
      history" not in the URL): each is a sweep across many strings or a
      routing change, not a fix - candidates for road-testing.md.
    - #121's judgements (the 2,708px queue notice, spaced hyphens, line
      lengths, mixed header styles, held-supply Red/Green) and #124's
      remaining ones (UserWarnings on every pass, the 590-line ticket outage,
      left-behind files named after the keep, unplaceable refused after
      "originally received", the no-environment first screen, `pipeline
      process` not naming what is red, one UTC refusal, REQ ids in help, the
      publish offer only on the synthetic route): recorded, not changed.

125. **[todo, 2026-10-06]** **[Pipeline & publishing]** **REQ-PIPE-057
    criterion 19's guard has done nothing since REQ-PIPE-089, and its tests
    stay green.** Found by the delivery-scoper while re-scoping REQ-PIPE-057
    criterion 18; confirmed against the code the same hour.

    `qa_tools/common/run_id_guard.py::committed_deliveries` reads
    `QA_RESULTS_DIR = ROOT / "qa_results"` - the committed tree
    REQ-PIPE-089 deleted. A missing directory returns `{}`, so `check()`
    returns early on every run, and both orchestrators still call it.
    `tests/test_run_id_guard.py` builds its JSON fixtures in `tmp_path`, so
    it is green against a guard that guards nothing in production - the
    "a passing test proving nothing" shape again.

    **Why it still matters**: run ids no longer come from position
    (REQ-PIPE-105 made them `<table>__<receipt key>`), so the original
    fragility is gone, but a run id can still change under recorded history
    through a table rename or a changed receipt instant. The guard should
    read `qa.run` - or be retired with the criterion amended, if Keith
    judges the receipt-keyed id makes it moot. **A defect against a built
    criterion, so his call before the fix.**

    **A neighbouring gap the same pass raised, unverified**: two separate
    deliveries of the SAME dataset with the same receipt instant (plausible
    off S3, whose LastModified is to the second) would get the same run id,
    and `qa.run.run_key` is a primary key. Not yet checked what happens.

    **KEITH, 2026-10-06: RETIRE IT.** Run ids are receipt-keyed since
    REQ-PIPE-105, so the positional renumbering the guard existed for is
    gone; criterion 19 is amended as moot and the guard and its tests are
    deleted rather than repointed at `qa.run`. The same-instant collision
    above is NOT covered by that answer and stays open.

126. **[todo, 2026-10-06]** **[Docs & process]** **REQ-PIPE-068's NFR 2
    still says a build "may never open or query any database, including
    this one"** - the wording REQ-DOCS-101's sweep replaced everywhere else
    with "a build may read recorded QA results, never actual data, and never
    anything else". Found by the delivery-scoper 2026-10-06. Wording only,
    but it states the opposite of the built design, so it is a claim in
    requirements.yaml and is written up here rather than quietly fixed.

127. **[done, 2026-10-06]** **[Pipeline & publishing]** **REQ-PIPE-154 labelled
    holds schedule-ended while the calendar ran on for four more years.**
    Shipped in 91226ea; caught the same afternoon by REQ-PIPE-156's
    whole-history comparison, which found `qa.hold.reason` differing: two
    2023 Case Workers holds read "it is the last period this dataset's
    schedule has" with `last_period` 2023-Q1, under a calendar that runs to
    2027.

    THE CAUSE was an assumption made explicitly and wrongly while building:
    that the last slot in the list handed to `assign()` is the calendar's
    last. Filing passes the slots up to the arrival's claim horizon, and for
    a dataset that skips quarters that list stops at the slot before the
    arrival - which had closed - so a gap read as an end.

    FIXED by telling `assign()` the dataset's real final period
    (`filing.final_period_for`, from the whole calendar; None for a cadence
    rule, which never ends); only that slot closing ends a schedule. Failing
    test first: `TestATruncatedSlotListIsNotAnEndedSchedule`, against the real
    Case Workers configuration. No supply was mis-filed - the hold kind and
    the filing were right; the reason and the structured flag were wrong.
    Worth carrying: the whole-history comparison built for the replay clock
    caught a bug in a different change, which is what it is for.

128. **[done, 2026-10-06]** **[Testing & dev tooling]** **The on-demand
    bootstrap-equivalence test (REQ-TEST-116 criterion 4) had been failing
    on every run, and nothing noticed because nothing runs it by default.**
    Found building REQ-TEST-159, whose criterion 5 rests on the same
    harness. Two causes, both of the "it moved on and the test did not"
    kind. The scripted decisions (REQ-GEN-135) refuse a cut-down corpus for
    missing their supplies - `run_into_fresh_database` had been patched for
    that, but the spawned-collection path the equivalence test uses had not,
    so it now rides `apply_redirects` and reaches a spawned child. And the
    comparison's exclusions predated the census, the identity row, owed
    runs, `check_result.load_attempt` and `filing.refiled_by`, so it
    reported every stamp and surrogate id in them as a difference.

    FIXED in `tests/equiv_support.py`: those clock columns dropped, surrogate
    ids dropped, and every id that points at another table compared as what
    it names (a load outcome, a decision, a filing), with a knock-on's
    running number (`knock-on/6`, `__r2`) masked. Confirmed failing on the
    commit before (6 errors), passing after (6 passed).

    THE PART WORTH SAYING TO KEITH: REQ-PIPE-158's evidence said its
    whole-bootstrap comparison found "every difference one the comparison
    already excludes". It did not exclude them - they were the same columns,
    explained by hand with a scratch script, as REQ-PIPE-156's evidence
    describes correctly. The comparison now does what that sentence claimed,
    and the evidence is reworded. The finding itself stands: no difference
    outside stamps, surrogate ids and the generator's receipt counter.

    DECIDED, Keith 2026-10-06 ("option one sounds good"): an `on-demand`
    job in `.github/workflows/test.yml` runs every test marked `on_demand` on
    every push, beside the other jobs (~5 minutes, under the 15-minute
    deployment job, so no added wait). The marker stays - it keeps a local
    `uv run pytest` quick. Rejected: a nightly run (the failure lands on
    nobody's push), path filters (a guess about what can break the history,
    which is what these tests exist to catch), and remembering to pass
    `--run-on-demand` locally (what had just failed). Pinned by
    `tests/test_ci_on_demand.py`.

129. **[done, 2026-10-06]** **[QA checks]** **A check's recorded failing-row
    sample was whichever rows a query happened to return first.** Found by
    the whole-bootstrap comparison for REQ-TEST-159: 20 cross-table results
    whose `failing_sample_keys` held the same five keys in a different
    order, once staging per arrival changed the tables' physical row order.
    The dbt helpers read `SELECT pk ... LIMIT 5` with no ORDER BY, the Soda
    sampler kept Soda's first five rows, and datacontract-cli's samples were
    kept in its order. Past five failing rows, WHICH rows were sampled could
    differ between two runs of the same data, not just their order - and a
    sample is what a person reads to see what went wrong.

    FIXED: the dbt queries order by the key, the Soda sampler keeps
    everything Soda returned (bounded by Soda's own sample limit) and
    `failing_sample_keys` sorts before keeping five, and datacontract-cli's
    samples are sorted.
    Failing test first: `tests/test_sample_keys_deterministic.py`, three
    tests, all red before. MEASURED over a whole bootstrap against the
    previous one: 1,002 results' samples changed and nothing else in them -
    676 the same keys reordered, 326 DIFFERENT keys chosen for the same
    data - and every sample recorded now is in key order. ONE EDGE REMAINS,
    inside Soda: a check whose `samples limit` is 5 and where more than five
    rows fail lets Soda choose WHICH five it returns before our sort sees
    them (one such result differed between two bootstraps, 2026-10-06 -
    8 rows failing). Fixing it means raising `samples limit` in the
    checks configuration so our sort chooses; NOT done without Keith, since
    it is a configuration change. Minor - no verdict, count or status changes - so
    fixed under the standing rule rather than held for Keith.

    THE SODA EDGE, CLOSED (Keith, 2026-10-07: "go ahead", and "note that in
    the fine print on the dashboard"). The 71 checks at `samples limit: 5`
    now ask for 100 - Soda's own default - so the five recorded are the
    lowest keys of all the failing rows up to 100; past 100, the lowest of
    the 100 Soda returned. The nine "failed rows" checks keep their
    deliberate 100000 (sodadata/soda-core#1985). Failing test first, against
    REAL Soda: eight failing rows stored so the first five are not the
    lowest five, red at 5 and green at 100. The limit is no longer part of a
    Soda check's `config_hash` (how many example rows come back is not what
    a check checks), so raising it asked for no changelog entries -
    `validate-check-lifecycle` reports zero changes. Takes effect on the next
    bootstrap; results already recorded keep the samples they had.

    A CORRECTION TO THE FIX ABOVE: "datacontract-cli's count was never
    capped" was wrong. The tool caps itself - `_FAILED_SAMPLE_LIMIT = 5` in
    `datacontract/engines/ibis/ibis_check_execute.py`, a `LIMIT 5` with no
    ORDER BY - so past five failing rows datacontract-cli chooses which five,
    exactly as Soda did, and there is no setting to raise. Patching the
    tool's private constant was not done (it is the pinning-shaped change
    Keith does not want). The dashboard says so instead: the new fine print
    under the example rows names, per tool, whether the keys are the lowest
    of all the failing rows or the tool's own choice, and
    `tests/test_sample_keys_deterministic.py` pins the page's two numbers to
    Soda's configured limit and datacontract-cli's constant.

130. **[done, 2026-10-06]** **[Pipeline & publishing]** **Recording each
    delivery at its first arrival (REQ-TEST-159) silently switched off
    Keith's #117 D5 cap**, which keeps a replayed promotion's invented lag
    before the same dataset's next receipt. `promotion.next_receipt` read
    the next receipt from the recorded deliveries, and its docstring said
    why that worked: the batch recorded every delivery before processing
    the first. Once it recorded each at its first arrival, the next one was
    not there yet, and 29 promotions' `effective_at` moved past the next
    receipt - two versions shown waiting at once, the very thing #117 D5
    fixed. Caught by the whole-bootstrap comparison before anything was
    committed, which is what it is for.

    FIXED: `next_receipt` also reads the arrivals in the delivery tree being
    replayed - exactly the set the batch used to record up front, so a
    replay answers as it did - and the live processing pass, which has no
    tree, still answers from what it recorded. Failing test first:
    `TestTheNextReceiptIsKnownInAReplay`. THE LESSON is the existing test's:
    it replaced `next_receipt` with a stub, so it proved the call site and
    never what the function would see.

131. **[done, 2026-10-07]** **[Pipeline & publishing]** **The delivery
    critic on five builds of 2026-10-06** - REQ-PIPE-157 (the dbt worker),
    REQ-TEST-159/160 (checkpoint and resume), REQ-PIPE-152 (the S3 handlers),
    REQ-PIPE-154/REQ-DASH-155 (held after the schedule ends) and 15edf01 (a
    Soda check that cannot run is red). Scope chosen by Keith, 2026-10-07:
    everything else built that day was left out on purpose (pure-speed work
    proven by the whole-bootstrap comparison, single-criterion amendments,
    the CI cache). Findings 1, 2 and 6 were re-checked against the code by
    the main session before being written here; the rest are as the critic
    reported them, marked "read" where it did not run anything.
    - **D1 (HIGH), CONFIRMED - a defect against REQ-TEST-160's fail-safe NFR
      and REQ-TEST-159 criterion 3.** `replay_inputs.deliveries_print` has
      one entry PER FILE, and `first_affected` returns that index as an
      ARRIVAL number. An arrival can hold several files for one dataset (the
      contested case, `arrivals.py:316`), so every arrival after one is
      reported later than it is, and a resume can then start too late and
      keep a stale verdict - the one direction the NFR forbids. The reason
      text is wrong too: a changed file reads "removed". Latent today (no
      multi-file arrival in either collection), and live the first time a
      contested pair arrives.
    - **D2 (MEDIUM-HIGH), CONFIRMED - REQ-PIPE-152's reliability NFR.**
      `s3_arrival.handle_event` passes the event's key to `head_object`
      raw, and S3 event notifications URL-encode keys - so any file name
      with a space or bracket fails on every retry. And one object that
      raises stops the rest of the event, so its siblings are never
      recorded either.
    - **D3 (MEDIUM), read - REQ-PIPE-152 criteria 12 and 13.** Criterion 13
      leans on "the scheduled pass remains the backstop", and `aws/` has no
      schedule, retry configuration or dead-letter queue. Several CP files
      landing together start parallel invocations that mostly meet
      `PassLockHeld`; their default retries can run out while one pass
      holds the lock. The time budget is checked inside the staging and
      arrival loops only - `materialise`, `refile_covered` and the owed
      re-checks run outside it. FOR KEITH: whether the scheduled backstop
      is in scope now.
    - **D4 (MEDIUM), read - REQ-PIPE-157 criterion 2.** The worker's schemas
      are named by PID alone, and PIDs repeat across containers; two such
      processes on one database can empty each other's schemas mid-build.
      Also two leaks in `dbt_worker.py`: a worker that died idle is replaced
      without `stop()`, and `_start` catches only `OSError`.
    - **D5 (MEDIUM-LOW), read - REQ-TEST-159 criterion 7 and the clutter
      NFR.** Resume databases are never listed or pruned; `delete()` drops a
      resume database with no confirmation even when it is the one a person
      was told to point `MOTHMAN_SUPPLY_DSN` at; a resume that fails after
      the copy leaves its database behind unnamed.
    - **D6 (LOW, a false-green path), CONFIRMED and latent.**
      `run_soda_cp.py:178` drops an unreported check whose `checks for` key
      is not a bare table name, which excludes Soda's partition syntax
      (`checks for t [recent]`, used by BDM today, not yet by CP); and
      `unreported_checks` skips a check with no `check_id`, which nothing
      at config time refuses.
    - **D7 (LOW), read - REQ-PIPE-154 criterion 7.** `refile_covered` runs
      after the arrival loop, so a newer supply in the same pass is filed
      before an older held one.
    - **D8 (LOW), read - REQ-DASH-155's performance NFR.** One query per
      dataset where the NFR asks for one aggregate in `tally()`'s shape.
    - **D9 (LOW), read.** `require_synthetic` tests truthiness where its
      siblings require `is True`; and the pass lock's pause around a
      checkpoint copy lets another pass start in the window.
    - **D10 (polish), wording.** The schedule-ended notice says "cannot be
      processed", while REQ-PIPE-154 criterion 5 says those supplies are
      still staged and file-checked.
    Found sound, and worth keeping on record: dbt re-reads the environment
    on every invoke (so swapping it per request carries nothing across);
    the partial-parse file never holds the password; checkpoint `delete()`
    and `prune()` cannot reach a non-checkpoint or another source's
    database; a resume writes only to its own copy; a retried S3 event
    records nothing twice; a not-evaluated Soda result is red and escaped.
    NOT VERIFIED by the critic: REQ-PIPE-157's equivalence and ten-minute
    target (both measured at build time), and anything against real AWS.
    TO FIX in one batch once the two UX critics running alongside it have
    KEITH, 2026-10-07, on D3: WAIT for a real AWS deployment, and collect
    this and the other AWS items in their own file - `plans/aws.md`.
    OUTCOME, 2026-10-07, each defect with a failing test first: D1 FIXED -
    the print is counted in distinct arrivals, and a changed file reads
    "changed" (`TestAnArrivalHoldingSeveralFiles`). D2 FIXED - keys
    URL-decoded, and an object that cannot be recorded no longer stops the
    rest; the pass still runs and the invocation then fails for retry
    (`TestEveryObjectInAnEventIsTried`). D3 to plans/aws.md (Keith). D4 FIXED
    - worker schemas carry a per-process random token beside the PID, a
    worker that died idle is stopped before another starts, and a failed
    start removes its process and directory (`TestNamesAndLeaks`). D5 FIXED
    - resume databases are listed (never pruned, Keith), deletes confirm
    and refuse an unknown name, and a resume that fails names the database
    it left. D6 FIXED - the partition is stripped from the table, the column
    is read wherever the call sits, and an unattributable check raises
    instead of vanishing; an id-less check was already refused at config
    time by the check-lifecycle gate's `MissingCheckIdError`, so no second
    guard was added. D7 FIXED - held supplies are re-filed before the pass's
    new arrivals. D8 KEPT AS BUILT - one query per dataset is how every
    per-dataset builder on the page reads, about thirty small indexed
    queries at full scale; an aggregate here alone would be the odd one out.
    D9 FIXED for `require_synthetic` (`is True`); the lock pause around a
    copy is unchanged - the copy refuses rather than proceeds if anything
    connects, which `_copy` already names. D10 FIXED with #132 A4.
    reported, failing test first for each defect.

132. **[done, 2026-10-07]** **[Dashboard UI]** **The dashboard UX
    critic on four small changes** - REQ-DASH-155's schedule-ended notice,
    REQ-PIPE-140 criterion 5's newest-result pill, REQ-PIPE-081 criterion 6's
    "decisions made since then" note, and #129's fine print. Scope chosen by
    Keith, 2026-10-07. Python Playwright over the built page (the MCP
    browser would not connect), 1440 and 390 wide, light and dark, no
    console errors. Finding A1 was re-checked against the code by the main
    session before being written here.
    - **A1 (HIGH, a false green), CONFIRMED - against REQ-DASH-126
      criterion 5.** A promoted supply's history row takes its pill from
      `promotedHealth.timeline`, which `promotion.status_of` fills with the
      GATE's reading of each result - and `_gating_status` deliberately
      reads a reference-gap red as its measured status (REQ-QAC-108
      criterion 15: a gap warns, it does not block). "Arrived X" comes from
      the page's own status. So on Client Register as at 2023-08-05 the
      header and the supply-level checks read Red while the same supply's
      row reads **Green, "Arrived Red"** - two status implementations on one
      row, the item-74 pattern, failing in the green direction. 22 of the 23
      "Arrived X" rows in the real data are this artefact (newest timeline
      point at the arrival instant); one, cp-investigations 2024-08-01, is
      the genuine turned-red case the change was built for. Right for the
      gate, wrong for a display: the fix is to show the displayed status,
      and change the pill only for a reading AFTER the arrival.
    - **A2 (MEDIUM) - the fine print claims more than this database holds.**
      The deployment was bootstrapped before 4a24a4d, so its Soda samples
      were taken at `samples limit: 5`, and the page states today's limit
      (`SODA_SAMPLES_ASKED`) as if it applied to them. Record the limit with
      each result and word the line from that. Also: "the 100 failing rows
      Soda returned" under "5 of 512" reads as if 100 rows failed - reword.
    - **A3 (MEDIUM), injected - a schedule-ended hold reads as the generic
      "held, waiting for a person".** Headline and footer say a person must
      resolve it while the body says the next pass files it; the hold queue
      offers file-it-yourself or reject, both the wrong fix (the fix is
      adding dates); raw ids and "cp-clients's" rather than the dataset's
      name; the command shows literal backticks through `escHtml`.
    - **A4 (LOW-MEDIUM) - the exhausted-schedule notice.** It blames the
      calendar ("quarterly has no delivery dates after...") when it is one
      dataset's own `endsOn` that ran out (cp-case-workers, 2027-10-18,
      while quarterly has 2027-11-01); it never names the dataset; "them"
      beside "1 dataset".
    - **A5 (LOW), injected - "decisions made since then".** Lists every
      dataset's decisions on a single-dataset page (`decisionsChangingDate`
      walks `rawRealDatasets()`); "and 1 more" is a dead end; it reads
      `run.arrivedAt`, which `raw.runs` does not carry, so a same-day
      resupply cannot be told apart.
    - **A6 (polish).** The fine print is 10.5px at 3.39:1 / 3.88:1 contrast,
      under 4.5:1 though matching its label; `dbt:unique` lists a repeated
      key, which "lowest keys among the failing rows" does not explain.
    Works well: the exhausted notice's backlog line counts as at the date
    shown and reflows cleanly; the fine print hides when every row shows;
    the genuine turned-red row reads exactly as intended.
    Out of scope, a sighting only: Client Register at 2023-08-05 shows
    "What is in the warehouse is not the latest file - 2026-Q2 / 2026-Q3".
    TO FIX in the same batch as #131, failing test first for A1-A5.
    KEITH, 2026-10-07: A1 - the pill shows the PAGE's own status, and
    changes from the arrival colour only for a reading AFTER the arrival,
    naming its cause; the gate keeps its own reading for promotion. A2 -
    RE-BOOTSTRAP ONLY: no per-result record of the sample limit and no
    "since" wording, accepting that a future limit change has the same
    window until the next rebuild. A3 - a schedule-ended hold offers
    ADD-DATES ONLY: "file it yourself" and "reject" are removed for this
    kind of hold, not kept as secondary options.
    OUTCOME, 2026-10-07: A1 FIXED at both ends - `promotion.status_of`
    takes `for_gate=False` for display and `pipeline/red_promoted.py` builds
    the timeline with it, and the page moves the pill only for a reading
    after the arrival, naming when and what changed it (Python and JS tests
    first). A2 - the deployment is rebuilt with the new limit (Keith's
    choice). A3 FIXED - a schedule-ended hold offers only adding dates, in
    the terminal and on the page ("Held: schedule ended"), names the
    dataset, says "until its next delivery dates are added" rather than
    "until a person resolves it", and shows a recorded command as code. A4
    FIXED - the notice names each dataset and its own last period, says
    "cannot be filed" (#131 D10: supplies are still received and checked),
    and agrees "it"/"them" with the count. A5 FIXED - the note lists only
    the datasets in view, all of them, with the receipt instant the runs
    carry. A6 - the fine print is reworded ("Soda returns up to 100 of the
    failing rows and chooses which; these are the lowest 5 keys of those")
    and moved from the faint to the muted ink; `dbt:unique` repeating a key
    is correct - each duplicate row is a failing row - and is left.

133. **[done, 2026-10-07]** **[Testing & dev tooling]** **The CLI UX
    critic on checkpoint and resume** (REQ-TEST-159/160), driven for real
    against its own scratch database - a ~10-minute bootstrap with a
    checkpoint, template copies with doctored descriptions for the failure
    states, every database it made deleted afterwards. Scope chosen by
    Keith, 2026-10-07. B2 was re-checked against the code by the main
    session. ITS SIDE EFFECTS, checked and put right the same morning: the
    runs regenerated `data/deliveries` (by design - the arrivals still match
    the `supply` database, 42 and 108, the three extra rows being one
    supply's knock-on re-runs) and rewrote `reports/results_cp.json` from
    the scratch database, which was rebuilt from `supply`.
    - **B1 (HIGH, gap) - where a resume lands cannot be pasted.** It ends
      "Point MOTHMAN_SUPPLY_DSN at user=user dbname=mothman_resume_... host=
      ... password=***", in libpq keyword form, wrapped across three lines,
      password masked - at the end of a multi-minute run, which undercuts the
      signed "a person points MOTHMAN_SUPPLY_DSN at it". Print one unwrapped
      `export MOTHMAN_SUPPLY_DSN=postgresql://user:<password>@.../<db>` line
      and how to go back.
    - **B2 (HIGH, defect), CONFIRMED.** `bootstrap --checkpoint-before` with
      an impossible N (1, 0, negative, past the end) prints a ~70-line
      traceback ending in a good `CheckpointRefused` sentence - only
      `resume_command` catches it. And an unreadable checkpoint (described
      as "before arrival 0") is not refused by `first.arrival < cp.before`,
      so `resume` crashes with StopIteration at `bootstrap.py:310`, while
      `checkpoint list` promises it would replay from the first arrival.
    - **B3 (HIGH, gap) - a refusal after `data/` was already rewritten.**
      Every bad-N refusal came after the synthetic data was regenerated.
      Validate N first.
    - **B4 (HIGH, gap) - N is a number nobody can see.** Nothing prints
      which delivery is arrival 55; the range is learned only from the
      refusal. A listing of arrivals, and the delivery's name beside every
      arrival number in messages.
    - **B5 (MEDIUM) - asking for a checkpoint on a populated database says
      "nothing to do" and exits 0.** Refuse, non-zero, with the three real
      steps (an empty database, `env mark`, bootstrap).
    - **B6 (MEDIUM) - the checkpoint's name is buried** at line 644 of 1,209;
      the run's last line does not mention it. Repeat it, and the resume
      command, in the closing summary.
    - **B7 (MEDIUM, defect against criterion 7) - deleting a name that does
      not exist reports "Deleted"** (`DROP ... IF EXISTS`), with no
      confirmation and `WITH (FORCE)`. Refuse unknown names; confirm.
    - **B8 (MEDIUM) - resume databases are not listed** (also #131 D5).
    - **B9 (MEDIUM) - a resume does not say up front** what changed, which
      arrivals it will replay, into which database, or roughly how long.
    - **B10-B14 (polish).** "removed" for a changed file (#131 D1); help
      text cites requirement ids, says "receipt instant" where the code
      snaps per delivery, does not say NAME comes from `checkpoint list`;
      two confusing result-count lines at the end of a resume, the second
      saying "from committed history"; checkpoint times in UTC rather than
      the asset's clock; a trailing "..." on statements. Not in the TUI,
      rightly - a developer tool.
    Works well: every refusal sentence that is caught says what happened,
    names the arrival and delivery, says nothing was copied, and gives a
    next step; nothing-changed answers in 5 seconds; snapping explains
    itself; `delete supply` is refused.
    TO FIX in the same batch as #131 and #132.
    OUTCOME, 2026-10-07: B1 FIXED - one unwrapped `export
    MOTHMAN_SUPPLY_DSN=postgresql://user:<password>@host:port/db` line, and
    how to go back. B2 FIXED - an impossible N and an unreadable checkpoint
    are refused in a sentence (`TestARefusalChangesNothing`). B3 FIXED - N
    is checked against a regeneration somewhere of its own before data/ is
    touched. B4 FIXED - `mothman pipeline checkpoint arrivals --collection
    cp` lists every arrival number with its delivery and receipt, and
    messages name the delivery beside an arrival number. B5 FIXED - a
    populated database refuses a checkpoint, non-zero, with the three
    steps. B6 FIXED - the closing line repeats the checkpoint and the
    resume command. B7 and B8 as #131 D5. B9 FIXED - a resume says what
    changed, which arrivals and into what, before copying (no time estimate
    - a number not measured would be invented). B10 with #131 D1. B11 help
    text no longer cites requirement ids and says where NAME comes from and
    where a resume lands. B12 FIXED - the rebuild's count line is quiet and
    says "recorded history". B13 FIXED - times on the asset clock; a
    statement keeps its full stop instead of a trailing "...".
