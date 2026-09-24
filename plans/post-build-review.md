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
    **Keith's call, two options,** and the critic's Q1 is the right
    framing: make the headline conditional on runway, or keep the OK
    line as a statement about config validity alone and drop the
    "every one of them expecting something" clause, which is the part
    that reads as a claim about the present.

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
