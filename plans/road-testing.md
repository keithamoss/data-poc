# Road testing

Things noticed while actually USING the dashboard and the `mothman`
CLI/TUI, as opposed to things found by designing, reviewing code or
reading a requirement. Keith's own ask, 2026-09-24: a place for what
turns up when you sit down and drive the thing like a user would.

Deliberately a different kind of file from its neighbours. `plans/
dashboard.md` holds features and design work for the dashboard;
`plans/qa-pipeline.md` holds real bugs found running the real tools.
This one holds **observations from use** - something that is confusing,
unlabelled, misleading, slow to find, or simply not what a reader would
assume - which may turn out to be a bug, a feature, a wording fix or
nothing at all once it is looked at properly.

An entry here is a SIGHTING, not a diagnosis. Write down what was
actually seen and what it made you think, before working out what is
really going on - the value of the record is that it captures the
reader's assumption at the moment it was formed, which is exactly what
is lost by the time someone has read the code.

Same conventions as every other numbered-item plans file: a closed
status (`todo` / `investigate` / `in-progress` / `parked` / `done` /
`superseded`), one or more component tags, and a date. Per `CLAUDE.md`,
anything here that turns into real build work becomes a requirement in
`requirements.yaml`, and the entry comes out when it lands.

1. **[investigate, 2026-09-24]** **[Dashboard UI]** **A trend is drawn
   in two different places, measuring two different things, and neither
   says which.** Keith's own sighting, road-testing the dashboard: it is
   not clear whether a trend line is row counts, failure counts,
   supplies or something else. It should say what it plots rather than
   just saying "Trend".

   **What the two actually plot**, read out of
   `dashboard/qa-reporting-dashboard.template.html` rather than assumed,
   because they are genuinely different quantities:

   - **The dataset table's `Trend` column** (`aggregateSparkline()` /
     `aggregateFailureSeries()`) plots, per run date, the **share of
     that scope's applicable checks that were not green** - a RATE
     between 0 and 1, deliberately not a raw count, because a check
     introduced or retired mid-history moves the denominator. The
     endpoint dot is coloured by the worst status that run. Nothing
     on screen says any of this. The column header is the bare word
     "Trend", there is no axis, no tooltip, no legend and no units; the
     only text anywhere is the SVG's `aria-label`, "aggregate
     failing-check trend sparkline", which a sighted reader never sees.
   - **The per-check trend chart in the drawer** (`trendChart()`) plots
     that ONE check's own metric over its run history, with warn and
     fail threshold lines. Better off, since the endpoint value is
     printed through `fmtMetric(value, unit)` and the unit carries the
     meaning - but the y-axis itself has no title, and the "View as
     table" header is the bare word "Value", so a check measuring a row
     count, a failing-row count and a percentage all render under
     identical labelling.

   **Why this is worth more than a label tweak.** The two are adjacent
   in the same UI and one is a RATE while the other is a RAW METRIC, so
   a reader who works out what one means will carry that reading to the
   other and be wrong. A falling line means "fewer checks failing" in
   the column and "this metric went down" in the drawer, which for some
   checks is bad news.

   **Also worth checking while in here**, both unverified: whether the
   `Rows, latest run` column and the trend column can be read as the
   same series when they are not, and whether the aggregate rate is
   legible at all as a sparkline with no scale - a line pinned near the
   bottom by the 0.05 floor looks like a low flat value rather than an
   all-green history.

   **Not yet scoped, and it needs Keith before it is.** The real fork is
   whether these get named in place (a header that says what is
   measured, an axis title, a tooltip) or whether the aggregate one
   needs a different treatment entirely at 30 datasets, where a column
   of unlabelled sparklines is thirty invitations to the same wrong
   reading.

2. **[todo, 2026-09-24]** **[Dashboard UI]** **Tier 1 and Tier 2 say
   whether there is a problem, never how big it is.** Keith's own ask,
   2026-09-24: roughly how many checks are in trouble for this dataset -
   how many amber, how many red - so a reader can see where to put their
   effort without clicking into each dataset in turn to count failing
   checks.

   **What the two tiers show today**, read out of the template:

   - **Tier 1, Executive** (`renderExec()`) counts AGENCIES by status -
     "N agencies red, N amber, N green" - and each agency card carries
     its collection and dataset counts. Nothing anywhere says how many
     CHECKS are failing, at any level.
   - **Tier 2, the agency view's dataset table** (`renderAgency()`)
     gives each dataset a single worst-of pill, alongside latest
     arrival, rows, last QA run and the trend sparkline. One red check
     and forty red checks render identically.

   **Why worst-of alone is the wrong signal for this job.** Worst-of is
   right for "is anything wrong here", which is what the rollup exists
   to answer, and it is deliberate - the Tier 1 sub-heading says so in
   as many words ("nothing silently hides behind a healthy average").
   But it is lossy in exactly the direction a person triaging needs:
   every red dataset looks equally red, so the only way to rank them is
   to open each one. At two datasets that is a click. At ~30 on the
   quarterly asset it is the difference between a dashboard you triage
   from and a list you work through.

   **Open, and worth settling before building anything:** whether the
   count is of CHECKS or of COLUMNS (a single bad column can carry
   several failing checks, so a check count can overstate how many
   things are actually wrong); whether Tier 1 aggregates the same
   numbers upward or shows something else entirely at agency level;
   whether a count belongs next to the pill, in its own column, or in
   the pill itself; and how this reads against the already-unlabelled
   trend column beside it (item 1) - adding a second number to that row
   without fixing the first risks two unexplained figures instead of
   one.

3. **[todo, 2026-09-24]** **[Pipeline & publishing]** **A
   regularly scheduled dataset whose supplies are FOR THE FOLLOWING
   PERIOD.** Keith's own worked example, 2026-09-24: data arriving in
   January does not fill Q1 - it fills **Q2**. Operational reality is
   that some datasets deliver for the current period and some for the
   next, and this is a per-dataset property.

   **The DESIGN QUESTION is settled; the WORK is not, and is
   deliberately not in these sprints.** Corrected 2026-09-24 after this
   entry was briefly marked done at `REQ-PIPE-062`'s sign-off - the
   sign-off resolved how it fits the model, which is not the same as
   building it. Keith's own placement: "that can go into the future log
   in the road testing plan file".

   **What is settled** (recorded on `REQ-PIPE-062`): it is NOT an
   exception to criterion 5, which stays absolute. The SCHEDULE
   expresses it, not the rule - that dataset's slot for the following
   period carries a due instant and claim window already open when the
   supply arrives, so nothing claims forward. Slots are already
   per-dataset, so no new configuration axis is needed. Same mechanism
   as the daily-cutoff and arrives-a-week-early cases that requirement
   deleted.

   **What is NOT built**: nothing declares, per dataset, that its
   supplies are for the following period, and nothing generates its
   slot calendar accordingly. Today a dataset's slots are derived on
   the assumption that a period's supply arrives within that period.

   **NAME COLLISION - do not merge this with `plans/supply-model.md`
   sprint 25.** Keith used "carry forward" for both on 2026-09-24, and
   they share a phrase and nothing else. Sprint 25 is a HUMAN DECISION
   that a supply is never coming, pointing a period's view at the last
   green supply so downstream consumers have something to query. THIS
   is a SCHEDULING PROPERTY of a healthy, punctual dataset. Sprint 25
   is being renamed for exactly this reason (backfill or patch are his
   candidates); this entry should not inherit whichever name it loses. Keith's own ask, 2026-09-24. Some
   datasets' supplies are for the period they arrive in; others' are
   for the following one. His own framing: "does it appear in a slot in
   this period, or does it need to go into a slot in the next period?"
   - and it is configured at DATASET level, which he chose over
   collection level so that one rule applies consistently even where a
   whole collection happens to share it.

   **Logged here because he raised it here, but it is NOT a road-testing
   sighting** - it is a supply-model design question, and it collides
   directly with a requirement that is drafted and not yet signed.
   `REQ-PIPE-062` criterion 5 says the system SHALL NOT assign a supply
   to a slot whose claim window has not opened, "under any rule or any
   circumstance". A dataset whose deliveries are FOR the next period is
   doing exactly that, under the current wording.

   **The distinction that probably resolves it, and it is not yet
   settled.** Criterion 5 exists to stop a LATE supply being
   misattributed forward to a slot that has not come due, which would
   silently mark a future obligation as met. A per-dataset "supplies
   are for the following period" offset is a different thing: it moves
   where the dataset's period BOUNDARY sits relative to arrival, rather
   than letting an arbitrary arrival claim ahead. If that reading
   holds, this is a property of the slot calendar rather than an
   exception to the assignment rule - and criterion 5 stays absolute,
   which is worth preserving, because an absolute rule with one
   exception is how forward-claiming comes back.

   **Not yet checked**: whether this is the same idea as
   `contract/data-asset.yaml`'s existing `as_of_offset_days`, which is a
   VIEWING offset and data-asset-level rather than per-dataset, or a
   genuinely separate concept that merely rhymes with it. They must not
   be conflated by accident.

4. **[todo, 2026-09-24]** **[QA checks & contract]** **Cardinality
   drift - watch how many distinct values a column has, not which ones
   they are.** Keith's own ask, 2026-09-24, and his own worked example:
   a suburb field holding ~600 values. New suburbs appearing is normal
   and uninteresting. Fifty appearing at once is a question. What we
   want is a threshold of acceptable change that lights amber or red,
   over the COUNT of distinct values - "we don't really care what the
   values are".

   **This is a genuinely different check from the drift we have**, which
   matters because the obvious move is to point the existing one at
   suburb and call it done. Today's drift check
   (`qa_tools/bdm/run_evidently_bdm.py`) computes **PSI** - a
   distribution-shift measure - on the `sex` column against a FIXED
   reference run. PSI answers "have the proportions moved", which is the
   right question for a handful of categories and the wrong one for 600
   suburbs: it bins, and a value that never appeared in the reference
   has no well-defined contribution, so the measure has to be smoothed
   precisely where Keith's signal lives. Counting distinct values is a
   different metric, not a re-parameterisation of this one.

   **A real, separate reason to like it, worth recording because it is
   not why he asked for it.** A check that records only a COUNT records
   no data. Today's `dataset_stats.json` carries value-count
   distributions and per-check failing-value aggregates - real values,
   committed to a PUBLIC repository, which is fine while the data is
   synthetic and is exactly the shape that has to be re-judged on real
   deployment terms. A cardinality check is the same signal with none of
   that exposure, in a Birth Registrations or Child Protection context
   where a list of distinct values is the sensitive part.

   **The forks, none of them settled, and the first two are the ones
   that decide whether this works at all:**

   - **Threshold of WHAT.** An absolute jump (+50 values), a percentage
     change, or a rate relative to row growth? A supply with twice as
     many rows will naturally carry more suburbs, so an absolute
     threshold fires on a legitimately larger extract and a percentage
     one fires on a small column. Keith said "threshold of acceptable
     change" without picking, and the pick changes what the check means.
   - **New values only, or disappearing ones too?** 600 becoming 650 is
     his stated case. 600 becoming 550 is arguably the more alarming
     one - a truncated extract or a dropped join - and a NET count hides
     both against each other: 50 gained and 50 lost reads as no change
     at all. Counting appearances and disappearances separately needs
     the previous run's value SET, not just its count, which partly
     gives back the privacy property above unless the comparison happens
     at run time and only the counts are kept.
   - **Compared against what.** The previous run, the previous PERIOD,
     or a fixed reference? Today's PSI check uses a fixed reference run,
     which ages badly for a field that legitimately grows - the baseline
     drifts further from reality every period and the check gets
     noisier on purpose.
   - **Does a resupply count as change?** A resupply of a period already
     supplied should not read as drift against the supply it replaces.
   - **The first run has no baseline**, same shape as the existing
     reference-run special case.
   - **Which columns get it**, presumably declared per column in the
     contract alongside every other check definition, with the three
     hand-authored prose fields `docs/check-authoring-rules.md` requires.

   Relates to item 1: whatever this check reports becomes another line
   on the per-check trend chart, under a y-axis that currently has no
   title. A count of distinct values is exactly the metric a reader
   would otherwise assume was a row count.

5. **[done, 2026-09-25]** **[Dashboard UI]** **The dashboard should
   display Perth time, not UTC.** Keith's own sighting, 2026-09-24.

   **BUILT by `REQ-DASH-071`, 2026-09-25.** All three shapes this
   sighting separated are closed - the hard-coded `" UTC"` slice, the
   bare `toLocaleDateString` with no zone, and the date-only string
   read as midnight UTC - along with the snapshot banner's own
   viewer-zone time, which it had flagged as honest rather than
   correct. Both of its open questions were answered by Keith and are
   recorded on the requirement: the asset's zone is always the one to
   show, and a time carries NO zone label, because there is only one
   clock and a label would imply a second.

6. **[todo, 2026-09-24]** **[QA checks & contract]** **Known
   date-of-birth outliers, declared explicitly, with a tiered
   percentage tolerance.** Keith's own ask, 2026-09-24. Some bad dates
   are KNOWN - a legacy placeholder, a specific bad batch - and they
   come as individual dates or as a date RANGE. He wants those named,
   and then a tolerance on how many rows may carry one, in bands:
   roughly 1% acceptable, 2% amber, above 3% red.

   **The semantics to hold on to, because the wording cuts both ways.**
   These are values known to be BAD, and we TOLERATE them up to a
   threshold. That is a different check from the plausible-range one
   already in `contract/bdm-birth-registrations-soda-checks.yml`
   (`date_of_birth < DATE '1900-01-01' OR date_of_birth >
   CURRENT_DATE`), which catches UNKNOWN bad dates and tolerates none
   of them - it is a `failed rows` check, so a single row fails it
   outright, with no warn tier and no percentage at all. Two checks,
   deliberately: a named, tolerated defect and an unrecognised one are
   not the same event, and collapsing them means either the known
   placeholder reds the dataset forever or the unknown date gets a
   tolerance it should never have.

   **VERIFIED 2026-09-24 against the installed `soda-core 3.5.6`** by
   running real scans over a ten-row DuckDB table, not from docs.
   Two routes work and two plausible-looking ones fail silently:

   - **WORKS - individual dates.** `invalid_percent(date_of_birth)` with
     `invalid values: ['1900-01-01', '1800-01-01']` and `warn: when >
     1%` / `fail: when > 3%`. Evaluated correctly: outcome `fail`,
     value `20.0` for two sentinel rows in ten. The two thresholds give
     exactly the three bands Keith described - clean below warn, amber
     between, red above fail - which is the same pattern
     `invalid_percent(sex)` already uses in this file.
   - **WORKS - dates AND ranges.** A user-defined metric carrying a SQL
     expression, with the same tiers:
     `known_outlier_percent expression:` computing
     `100.0 * COUNT(CASE WHEN date_of_birth IN (...) OR date_of_birth
     BETWEEN ... THEN 1 END) / COUNT(*)`, `warn: when > 1`, `fail: when
     > 3`. Evaluated correctly: outcome `fail`, value `30.0` for three
     rows in ten. This is the route that handles a range, and it
     handles individual dates too, so it can carry the whole feature.
   - **DOES NOT WORK - `valid min` / `valid max` with dates.** Soda
     parses these as floats: `valid min must be an number (float), but
     was '1900-01-02'`, quoted or not. There is no date-range form of
     the built-in validity config.
   - **DOES NOT WORK - `valid sql`.** Unsupported in this version:
     "Skipping unsupported check configuration: valid sql".

   **Both failures are SILENT FALSE GREENS, which is the part that
   matters more than the feature.** In each case the misconfiguration
   was logged as an error and the check still evaluated to **pass, with
   value 0.0** - because with no validity criterion, nothing is invalid.
   A person writing `valid min: '1900-01-01'` gets a green check that
   looks like it is guarding the column and is guarding nothing. See
   item 7, which is the general fix.

   Still to decide: WHERE the outlier list lives (inline in the SodaCL
   check, or in the ODCS contract beside the column it describes, which
   is where a reader would look for it); whether the same mechanism is
   wanted on other date columns or is specific to `date_of_birth`; and
   the three prose fields `docs/check-authoring-rules.md` requires,
   where `failure_indicates` has real work to do - "more rows than
   agreed carry a known-bad date" is a different message from "a date we
   do not recognise appeared".

7. **[todo, 2026-09-24]** **[QA checks & contract]** **A misconfigured
   Soda check passes silently, because the runners ignore Soda's own
   error log.** Found 2026-09-24 while verifying item 6, and it is a
   real defect rather than a design gap - three separate instances have
   now turned up in one morning.

   `qa_tools/bdm/run_soda_bdm.py` and `qa_tools/cp/run_soda_cp.py` both
   call `scan.execute()` and go straight to `scan.get_scan_results()`.
   Neither inspects the return value, and neither calls
   `scan.has_error_logs()`. Soda reports a bad check configuration by
   logging an ERROR and carrying on, so the three cases found today all
   reach the dashboard as ordinary results:

   - `valid sql` - unsupported, silently skipped, check then **passes**
     at 0.0% invalid because nothing is being validated.
   - `valid min` / `valid max` given a date - rejected as not-a-float,
     check then **passes** at 0.0% for the same reason.
   - a change-over-time check with no Soda Cloud - crashes in
     evaluation, and the check vanishes from
     `get_scan_results()["checks"]` entirely, so it reports nothing at
     all (see item 4).

   In every case `scan.has_error_logs()` was `True`, so the signal
   exists and is simply not read. Two of the three produce a GREEN check
   that guards nothing, and the third produces a `check_id` that is
   declared, lifecycle-validated, and never reports - all three are the
   false-green direction.

   Not yet decided, and worth a moment because the obvious fix is too
   blunt: whether an error should fail the whole scan (simple, and one
   bad check then stops a dataset's entire QA run - the blast-radius
   shape `REQ-PIPE-053` exists to avoid), or mark just the affected
   checks as errored and surface them as needing attention, or be
   caught at config time by a gate over the checks file so a broken
   check never runs at all. The third is the most in keeping with how
   this project already gates check lifecycle, and would not have
   caught the change-over-time case, which only fails at run time.

8. **[investigate, 2026-09-24]** **[Dashboard UI]** **Closing a check
   panel navigates back TWO levels, landing on the agency view instead
   of the dataset.** Keith's own sighting, 2026-09-24, and this one is a
   real bug rather than a design gap - closing a panel should return you
   to what you were looking at, and instead it throws away a level of
   drill-down.

   **What the code says, read but NOT yet reproduced** - recorded this
   way on purpose, because the reading and the symptom disagree and that
   disagreement is the lead:

   - `openCheckPanel()` sets `STATE = {...STATE, checkKey:check.key,
     compareIdx:undefined}` and does ONE `history.pushState`.
   - `closeCheckPanel()` does ONE `history.back()` when
     `STATE.checkKey` is set.
   - `renderFromState()` then re-renders and reopens the drawer if the
     restored state still carries `columnName`.

   One push, one back - so on this reading it should land exactly one
   level down, on the dataset view with the drawer open. It does not.
   **So the wrong assumption is about what sits UNDERNEATH the pushed
   entry**, not about the count of history steps, and that is what to
   check first: whether the entry the check panel was pushed on top of
   was a dataset-tier entry at all. Two candidates worth testing before
   anything else - a check panel opened from somewhere that never
   pushed its own dataset-tier entry, and a `navigate()` call
   (`hideCheckPanel(); hideDrawer(); hideAllPanelsDom(); render();
   pushState`) collapsing two conceptual levels into one entry.

   **Reproduce in a real browser before touching anything.** Per
   `CLAUDE.md` this gets a test that fails against the current code
   first, then the fix - and `tests-js/navigation.test.js` already
   covers drill-down navigation in a real jsdom window, so there is an
   obvious home for it. `tests/test_dashboard_e2e.py` is the heavier
   option if the bug turns out to need real history semantics jsdom
   does not model.

9. **[todo, 2026-09-24]** **[Dashboard UI]** **A value-distribution
   histogram in the drill-down, this supply beside the previous one.**
   Keith's own ask, 2026-09-24, for categorical columns where it makes
   sense: show what is in the column now and what was in it last
   supply, side by side, so a reader gets an immediate visual sense of
   how much has shifted.

   **His own framing of why, and it is the part worth keeping**: this is
   a HUMAN COMFORT feature, not a check. Drift detection will exist for
   the variables that warrant it, but we will not want a drift check on
   every column - and for all the rest, a picture gives you the same
   reassurance at a glance for no configuration and no threshold to
   argue about. It answers "does this look like it always does" rather
   than "is this within tolerance", and those are genuinely different
   questions.

   **The data already exists and needs no new collection.**
   `dataset_stats.json` already carries value-count distributions, and
   the drawer already has the previous run in hand for its
   current-vs-previous comparison. So this is a rendering job over
   committed history, not a new computation - which also keeps it on
   the right side of `CLAUDE.md`'s rule that the dashboard build never
   touches `data/`.

   **Open, and mostly about restraint rather than mechanism:** which
   columns qualify as "where that makes sense" - a bounded categorical
   like `sex` is obvious, a 600-value suburb field is a different chart
   and possibly a top-N one, and a free-text name column is neither;
   whether a small count is shown at all, since a category with two
   rows renders as a bar indistinguishable from zero; whether the
   comparison is previous SUPPLY or previous PERIOD, which differ the
   moment a resupply exists; and how it reads for a column whose
   categories CHANGED between the two supplies, where the honest
   rendering has to show a bar that appeared and one that vanished
   rather than quietly aligning the lists.

   Note the overlap with item 4: cardinality drift answers the same
   question numerically for high-cardinality columns where a histogram
   would be unreadable. Worth designing the two together so they do not
   end up as two unrelated treatments of one concern.

10. **[investigate, 2026-09-24]** **[Dashboard UI]** **[QA checks &
    contract]** **An invalid-values check should say WHICH values were
    invalid and how many of each - and mostly it already can, for six
    columns out of everything.** Keith's own ask, 2026-09-24: a table, a
    histogram, a bar chart, whatever - just be clear what was wrong and
    how much of it there was.

    **It already exists, which reframes this from "build it" to "why did
    you not see it".** `aggregateValuesBlock()` in the template renders,
    inside the check panel's Row-level detail section:

    - **categorical** - "Invalid values seen, current run (N row(s))",
      then one labelled bar per distinct invalid value with its count.
      That is exactly what was asked for.
    - **numeric/date** - earliest bad value, latest bad value, distinct
      count, then a bucketed histogram of the failing values.
    - **sensitive columns** - suppressed behind a lock with only the
      count, which is the right default and worth not losing.

    **The gap is COVERAGE, and it is a hand-maintained allowlist.**
    `AGGREGATE_SPEC` in `qa_tools/bdm/dataset_stats.py` and
    `qa_tools/cp/dataset_stats.py` names **six column entries in total**
    - BDM's `sex`, `place_of_birth_suburb`, `date_of_birth`; CP's
    `(cp_clients, postcode)`, `(cp_clients, date_of_birth)`,
    `(cp_notifications, concern_type)`. Against that, the two SodaCL
    files alone carry **19 `invalid_percent` checks** (8 BDM, 11 CP),
    before counting the dbt and datacontract equivalents. Every check
    outside the allowlist renders no value breakdown at all, silently -
    there is no "not available for this check" line the way the
    failing-row sample block has one.

    **A second entry gate on top of the first**: each spec carries a
    `check_names` set, so even a covered column shows nothing unless the
    check's own name is in it - and the naming is already inconsistent
    between the two files (`"invalid_percent[all]"` in BDM,
    `"invalid_percent"` in CP). A check renamed, or a new tool reporting
    the same column under a different name, drops out with no signal.

    **And the validity rule is DUPLICATED, which is the part that will
    bite.** Each spec carries its own hand-written `invalid_condition`
    SQL restating what the check already declares - `_SUBURB_VALID`,
    `_SEX_VALID`, `_POSTCODE_VALID`, `_CONCERN_TYPE_VALID` are literal
    re-copies of lists that also live in the SodaCL checks and the ODCS
    contract. **Checked 2026-09-24: they are in sync today** - suburb 51
    values both sides, no difference either way; sex identical - so this
    is a latent risk rather than a live bug. But nothing gates them
    against each other, and the failure is quiet in a nasty way: the
    panel would confidently draw a value breakdown computed from a stale
    list while the check's own verdict used the current one, so the
    numbers on screen would disagree with the status beside them. Same
    family as `CLAUDE.md`'s "enumerate every consumer" bullet.

    **So the real work is probably not a new chart.** It is deriving the
    aggregate from the check's own declared validity rule instead of a
    parallel hand-written one, so coverage follows the checks
    automatically and there is one copy of the truth - with the
    sensitive-column suppression preserved, since that is a deliberate
    decision and not an omission. Worth checking against item 9 before
    building either: that one wants a distribution of ALL values current
    versus previous, this one wants a distribution of the INVALID ones,
    and they are close enough that two unrelated implementations would
    be a mistake.

    Open: whether an uncovered check should say so rather than render
    nothing (the failing-row sample block already sets that precedent);
    whether every column can have one or whether some genuinely should
    not (a free-text name column's invalid values are close to
    row-level data, which is the line
    `docs/remediation-workflow-design.md` draws); and whether the
    breakdown should also show the compared run, which is item 9's
    question arriving from the other direction.

11. **[todo, 2026-09-24]** **[Dashboard UI]** **Supply history: columns
    do not line up across cycles, and the dates are raw.** Keith's own
    sighting, 2026-09-24. Two small things in one place, both in
    `renderSupplyHistorySection()` / `renderSupplyCycleRows()`.

    **The alignment.** Every row emits the same five `<td>`s, so the
    cell COUNT is not the problem. The problem is that **each supply
    cycle renders its own `<table class="dataset-table">`**, stacked
    vertically down the section. Table layout is auto, so every table
    sizes its columns independently from its own content - and a cycle
    containing a resupply sizes differently in two columns at once: the
    trailing column has to fit a "Resupply, attempt N" chip instead of
    being empty, and the Timing column holds "N days since previous"
    text rather than an arrival pill plus a timestamp. So two cycles
    stacked one above the other put their column edges in different
    places, which is exactly what Keith is seeing. Read from the code
    rather than reproduced in a browser, but independent auto-layout
    tables genuinely cannot align, so the mechanism is not in much
    doubt. Likely fixes: one shared `<colgroup>` with `table-layout:
    fixed`, or one table for the whole section with cycle header rows
    instead of a table per cycle.

    **The dates, and there are two different raw values, not one.**
    - The **Arrived** column renders `e.run_date` straight into a
      `mono` cell - a bare `2026-07-01`, where the rest of this
      dashboard uses `fmtDate()` and reads "Jul 1, 2026".
    - The **Timing** column renders `e.arrivedAt` raw, and in supply
      history that is a **full ISO timestamp** - `arrival
      ["earliest_extract"]` straight out of
      `pipeline/build_dashboard_data.py`. Note this is a DIFFERENT
      value from the `arrivedAt` the dataset header shows, which
      `buildRealDataset()` slices to `HH:MM` and labels " UTC". Same
      field name, two shapes, one of them unformatted.

    **Do this with item 5, not before it.** That raw timestamp is UTC,
    so making it readable is the same edit as making it Perth - format
    it through `ASSET_TIMEZONE` rather than just prettifying a UTC
    reading into a nicer-looking wrong answer.

    `tests-js/supply-history.test.js` already covers this section's
    grouping logic and is the obvious home for anything asserting the
    rendered output.

12. **[todo, 2026-09-24]** **[QA checks & contract]** **A completeness
    check for a TALL dataset: every event must have exactly one row per
    expected category.** Keith's own ask, 2026-09-24, with his own
    worked example - a geocoding dataset holding one row per geocoding
    event per ABS census year, so one geocoding event generates six
    rows for six census years. Anything that violates that, we want to
    know about.

    **The generalisable rule underneath it**, which is what makes this
    worth building rather than one bespoke query: *for every key, there
    must be exactly one row for each member of a declared set.* Stated
    that way it has three distinct violations, and they mean different
    things operationally - worth separating rather than reporting one
    count:
    - a **missing** member (five years present, one absent) - an
      incomplete event;
    - a **duplicate** member (two rows for the same event and year) - a
      double-load or a bad join, and the one most likely to skew any
      downstream aggregate silently;
    - an **unexpected** member (a year not in the declared set) - the
      source has started emitting something nobody agreed to, which is
      the same event class as an unrecognised arrival artefact.

    **This is the PoC's first TALL dataset, and that is the part likely
    to bite.** Every dataset here today is wide - one row per entity -
    and several existing patterns quietly assume it:
    - the **primary key is composite** (event plus census year). The
      contract expresses uniqueness as `unique: true` on a single
      column, and the check panel's failing-row sample renders
      "primary key only" as a single value per row. Neither is wrong,
      but neither has ever had to carry a two-part key.
    - **`row_count` bands become a multiple.** A supply of N events is
      6N rows, so the absolute band that works for a wide table needs
      to be stated against events, or against rows with the multiplier
      made explicit - otherwise a supply missing a whole census year
      still lands comfortably inside a row-count band.
    - a bare **`unique`** check on the event column would fail by
      design, since every event legitimately appears six times.

    **The expected set GROWS, on a known five-year cadence** (Keith,
    2026-09-24, confirming this is a certainty rather than the
    hypothetical the first draft of this entry treated it as). ABS runs
    a census every five years, so a seventh year arrives, then an
    eighth. That makes the expected set a function of time, not a
    constant, and it splits the check into two genuinely different
    questions that are easy to conflate:

    - *Does every event have a row for every census year that EXISTS?*
      On this reading, the day a new census is processed, every
      historical event in the table is instantly incomplete until it is
      backfilled - the whole dataset goes red at once, for a reason
      that is real but not a data-quality failure.
    - *Does every event have a row for every census year it was
      geocoded AGAINST?* Nothing ever goes red, and a backfill that
      never happened is invisible, because nothing expected it.

    Neither is right on its own. The likely answer is that the expected
    set is DECLARED rather than inferred, and widening it is an explicit
    act - so a backfill is something someone decides to require, and
    the check goes red only against a set we have said we expect.

    **And this project already has the machinery for that**, which is
    worth saying because it looks like it needs something new. A
    declared set widening every five years is exactly a check-definition
    change: `check_lifecycle.py` already validates hand-authored check
    metadata, `changelog:` already records dated definition changes, and
    the trend chart already draws a real break at a breaking one so a
    before/after comparison is not silently made across a moved
    goalpost. What is unusual here - and useful - is that the change
    date is known YEARS in advance, which is a strong argument for the
    set being declared data rather than derived from whatever happens
    to be in the table.

    **Open:** where the expected set of census years is DECLARED - a
    literal list in the contract beside the column, which is how
    `valid values` already works, or derived from the data, which would
    make a wholly-missing year invisible because nothing would expect
    it; whether the
    check reports per event or as a percentage of events, which is
    `REQ-QAC`-style tiering and pairs with item 6's tolerance bands;
    and which tool runs it - this is a `GROUP BY ... HAVING` shape,
    so Soda's `failed rows` with a `fail query` or a dbt test, not any
    built-in metric.

    **Also unresolved, and prior to the check itself**: whether this
    PoC gains a real geocoding dataset to demonstrate against, or
    whether the pattern is shown on one of the existing collections.
    There is no geocoding or census data in the repo today - checked -
    so something has to be generated either way, and `plans/
    data-generation.md` is where that lands rather than here.

13. **[todo, 2026-09-24]** **[QA checks & contract]** **Soda Core
   cannot execute a change-over-time check at all, so any such check in
   this project has to be computed by us.**

   Split out of item 5 on 2026-09-25: it was appended there while that
   item was open, and it is a different subject that outlived it.

   **VERIFIED 2026-09-24, and it constrains any "change over time"
   check, row counts included.** Keith asked whether
   Soda's row-count check can express an expected increase and separate
   amber/red thresholds for change over time. Answered by real
   experiment against the installed `soda-core 3.5.6`, not from docs -
   `docs.soda.io` is blocked from this environment, and a real run is a
   better primary source regardless.

   - **Absolute row-count bands with both tiers already work, and we
     already use them.** `contract/bdm-birth-registrations-soda-checks.
     yml`'s `row_count` check carries `warn: when < 500` and `fail: when
     < 100 / when > 20000`. Re-ran it live against a three-row table: it
     evaluated and FAILED as expected.
   - **SodaCL does have change-over-time syntax, and it does accept
     tiered thresholds.** `change for row_count`, `change percent for
     row_count` and `change avg last 7 for row_count` all parse, and a
     `warn:`/`fail:` pair on one parses cleanly - no syntax error.
   - **But Soda Core cannot EXECUTE any of them.** `soda/scan.py`'s
     `__get_historic_data_from_soda_cloud_metric_store()` logs "Soda
     Core must be configured to connect to Soda Cloud to use
     change-over-time checks" and returns `{}` - the measurement history
     lives in Soda Cloud, and Soda Core has no local store for it. The
     check then crashes evaluating (`'NoneType' object has no attribute
     'get'`), is marked NOT EVALUATED, and the scan returns exit code 3.
   - **The failure mode is the dangerous one: the check DISAPPEARS.** A
     not-evaluated check is absent from `scan.get_scan_results()
     ["checks"]` entirely - verified, the list came back empty. This
     repo's runners read exactly that structure and ignore
     `scan.execute()`'s return code, so adding such a check would
     produce no red, no amber and no visible error - just a declared
     `check_id` that never reports. That is a silently missing check,
     which is the false-green direction.

   **So any change-over-time check in this project has to be computed
   by us**, against committed `qa_results/` history, rather than
   declared in SodaCL, and that now applies equally to row-count
   change.
   Note the history is already there and already committed, so the
   comparison needs no live data access; per `CLAUDE.md`'s hard rule it
   would still be computed at run time by whoever legitimately holds a
   connection, never in the dashboard build.

14. **"Client reference" three times in a row, with nothing to tell
    them apart.** Noticed 2026-09-26 while driving the new cross-table
    section (REQ-QAC-037) on the Child Protection collection page. The
    section lists 21 checks and only 9 distinct labels: "Client
    reference" appears three times, "Carer reference" three times, and
    so on. They are genuinely different checks - the dbt, Soda and
    datacontract-cli versions of the same relationship, and the same
    relationship on different tables - so de-duping them would hide
    real results. But a reader cannot tell which is which from the row.

    **Status:** todo (2026-09-26) · **Category:** Dashboard UI

    Not new to this section: the dataset pages have shown the same
    repetition all along, and the collection page has simply gathered
    it into one place where it is finally obvious. Worth saying because
    that is the point of road-testing - the section did not create the
    problem, it revealed it.

    A row probably needs to name its participants and its tool, but
    that is a guess and this entry is a sighting rather than a
    diagnosis.

14. **[investigate, 2026-09-28]** **[Dashboard UI]** **"Arrived at" on
    the dashboard is the earliest row in the file, not when the supply
    arrived - and the two only agreed by coincidence.**

    **Status:** investigate · **Category:** Dashboard UI

    Found while injecting REQ-GEN-044's first scenarios, which is the
    kind of thing that requirement exists to surface: the whole of TS-1
    is three files landing at 14:00, 16:00 and 20:00 on one day, and
    the dashboard shows none of those times.

    **What is actually happening.** `pipeline/build_dashboard_data.py`
    and its Child Protection counterpart both set `arrivedAt` from
    `earliest_extract` - the earliest `extract_timestamp` in the staged
    rows. The RECEIPT instant, which REQ-PIPE-105 established as the
    authoritative answer to when a supply arrived and which records
    which clock timed it, is not what the page renders.

    **Why nobody noticed.** For generated Birth Registrations data the
    two were the same value by construction: `generate_runs.py`'s own
    `_received_at()` takes the receipt instant FROM the payload's
    earliest extract, deliberately, so that "the manifest and the
    warehouse cannot disagree". So the label was true of every supply
    this project had ever generated. An injected scenario sets its own
    arrival instant - that is the point of it - and the two came apart
    immediately.

    **Why it matters beyond the scenarios.** A real supplier's extract
    timestamp is a fact about their system, not about when we received
    anything, and the gap between the two is exactly what a lateness
    verdict is measured on. A dashboard that labels one as the other is
    fine until the day they differ, which is the day somebody is trying
    to work out why a supply was late.

    **Not fixed here**, deliberately. `arrivedAt` is pinned by
    `tests/fixtures/arrival_semantics_golden.json` and read by the
    arrival-classification display, so changing what it means is a
    shape change with several consumers - this project's own standing
    rule says enumerate them first. Written down as a sighting.

## Seen on 2026-09-28 night, once promotion started working

**[investigate, 2026-09-28]** **[Dashboard UI]** **Seventeen "missing
supply" items for ONE daily dataset, on one page.** Birth Registrations'
dataset page now carries a closed-unfilled-slot item for every day the
synthetic corpus skipped between its earliest arrival and its newest -
each individually correct, and seventeen of them in a column.

This is REQ-PIPE-063's rule working exactly as written, so it is a
SIGHTING rather than a diagnosis. What makes it worth writing down is
the scale argument this project already applies elsewhere: `supply_holds`
aggregates precisely because "at two datasets a banner per held supply
is fine; at the ~30 this is a PoC for it is thirty banners, and a banner
per dataset is exactly how people learn to ignore a whole class of
warning". A DAILY dataset multiplies that again - a feed with a quiet
fortnight produces fourteen items about one fact.

Three things it might be, and it is not obvious which:
- the items should aggregate, the way holds do - "14 days with no supply
  between X and Y", one row, expandable;
- a run of consecutive closed slots is one event (a gap) rather than N;
- it is right as it is, and a daily feed simply has more to say.

Nothing done. It needs Keith, because "how much is too much" is a
judgement about who reads the page rather than about the rule.

15. **[blocked, 2026-10-04]** **[Testing & dev tooling]** **`mothman
    pipeline bootstrap --force` no longer reproduces the same content.**

    Seen while regenerating for REQ-PIPE-105: a `--force` bootstrap over
    an already-populated database promoted 11 supplies where a clean one
    promotes dozens, and refused the very first Child Protection arrival
    of 2023 because "this supply's slot is already filled by a promoted
    supply". Nothing about the data was wrong: the PREVIOUS bootstrap's
    promotions were still in the decision log, filling every slot, so
    every supply filed as a resupply into a filled slot.

    Its own docstring says the opposite - "the pipeline is deterministic
    and seeded, so re-running is safe and reproduces the same content".
    That was true before filing became write-once and the decision log
    append-only (a database trigger refuses TRUNCATE); `--force` re-runs
    the pipeline but resets neither.

    The figures recorded on REQ-PIPE-105 for the first regenerate (73
    promoted, 28 contested) came from a `--force` run on top of a crashed
    one, so they are suspect for the same reason; the second regenerate
    was taken from a database recreated empty.

    Worked around by dropping and recreating the sandbox's `supply`
    database. What `--force` SHOULD do - refuse on a populated decision
    log, recreate the database, or say plainly that it adds to history -
    is a call about how destructive a dev command may be, so it is
    Keith's rather than fixed in passing. CI is unaffected: every runner
    starts from an empty database.

    **DECIDED 2026-10-04 (Keith), carried by REQ-PIPE-144:** `--force` on a
    database that already holds history REFUSES and points at the new
    guarded `mothman env reset-synthetic`; it never wipes anything itself.
    Delete this entry when REQ-PIPE-144 is built.

16. **[investigate, 2026-10-03]** **[Pipeline & publishing]** **A clean
    resupply cannot get through once a quarter has two undecided
    versions of anything.**

    Seen in the first regenerate with REQ-PIPE-105 criterion 13 wired, in
    Child Protection 2026-Q2. The 05-01 delivery had real failures in
    Clients (25), Investigations (17), Notifications (9) and Placements
    (3), and was refused. Refused supplies STAY IN STAGING awaiting a
    person. The 05-20 resupply's Investigations and Placements were clean,
    but they read Clients, which now had two undecided versions for Q2;
    criterion 8 makes that contested and unreadable, so both went red as
    "a supply is staged awaiting a decision" and were refused too. The
    05-27 resupply was clean in all six files - and all five that read a
    sibling went red the same way, because every sibling now had two or
    three undecided versions.

    So it is a pile-up rather than a deadlock: each resupply adds a
    staged version, and once any dataset has two undecided supplies in a
    period, nothing that reads it can be checked until a person rejects
    the stale ones. 12 supplies across the corpus were refused with no
    data failure at all, 9 of them this way.

    Put to Keith 2026-10-03 morning with one candidate - read a sibling
    from the run's OWN ARRIVAL first where that arrival carried it, which
    pairs files that came together without choosing by arrival time - and
    he chose to talk it through first. Whether an "unrunnable" red should
    gate promotion at all is deferred until this is settled, since it may
    remove most of the cases.

    **MOSTLY NOT WHAT IT LOOKED LIKE, found an hour later.** All 90 of
    that regenerate's "could not be evaluated" reds were about a table
    the supply's OWN ARRIVAL carried: each file of a zip was filed just
    before its own run, and the overlay reads only filed siblings, so the
    first file saw none of the rest. Fixed under REQ-PIPE-105 criterion 5
    (a zip is filed whole, Keith 2026-10-03). What remains of this entry
    is whatever the next regenerate still shows - two undecided versions
    of a dataset in one period, where a red supply sits awaiting a person
    beside its correction - and the gate question waits on that number.

    **DIRECTION, Keith 2026-10-03: option 2, plus a re-run on acceptance.**
    A supply that has been checked and refused stops being a candidate for
    its period (it stays in staging for a person), so a clean correction
    reads its own fresh siblings and promotes on its own. Because that is
    the system choosing by verdict, ACCEPTING a refused supply must
    trigger a re-run of every check that reads it. Being worked through
    as a scenario before any wording is drafted; it amends REQ-PIPE-079
    criterion 11 ("SHALL NOT choose between them for any purpose") and
    adds a decision-time trigger beside 079's arrival-time re-evaluation.

    **SETTLED IN THE SCENARIO WALK-THROUGH, Keith 2026-10-03** - not yet
    requirement wording, which still needs drafting and sign-off:
    - **Own arrival always visible.** Option 2 sets aside refused supplies
      from EARLIER arrivals only. A sibling carried by the run's own
      arrival is read whatever its verdict, or the order files happen to
      run in would decide what a check sees.
    - **Acceptance reopens.** When accepting a supply re-runs the checks
      reading it, a sibling whose EVERY red was "could not read a table",
      and all of which are now resolved, promotes automatically. One real
      data failure keeps it refused. This settles the deferred gate
      question: "could not read" reds DO block promotion, because
      acceptance is what unblocks them.
    - **Displacing a promoted supply: preview, then allow.** Accepting a
      red supply that replaces a promoted one (newest-by-promotion wins,
      REQ-PIPE-105 criterion 7) shows first how many promoted supplies
      read it and will be re-checked, then proceeds. No automatic
      demotion afterwards - a re-check that fails is shown on the
      dashboard against the promoted supply, naming the acceptance that
      caused it.
    Re-run results carry `caused_by` naming the DECISION, the same field
    arrival-time re-evaluation uses (REQ-PIPE-079 criterion 7).

    **REFINED BY KEITH, same conversation:** acceptance does not need a
    rule of its own. It re-checks what was waiting and applies EXACTLY THE
    SAME GATE as a first arrival - all green across own and cross-table
    checks and it promotes, anything else and it does not. The "every red
    was could-not-read" condition above is just what that gate already
    implies, so draft the requirement as "re-evaluate and re-apply the
    promotion gate", not as a separate reopen rule. Path B confirmed as
    written.

    **SCOPED 2026-10-03 by delivery-scoper as drafts REQ-PIPE-118 (set
    aside), REQ-PIPE-119 (accepting re-checks and re-gates), REQ-GHUB-120
    (displacement preview) and REQ-DASH-121 (decision-caused re-check on
    the dashboard) - unsigned; draft held in the session scratchpad, to be
    revised with the answers below. "Path B" above = accepting a red
    supply that DISPLACES a promoted one. Verified while relaying: the
    gate records a refusal durably only for off-cycle supplies
    (promotion._record_withheld), so 118 needs a refusal record.
    Keith's answers to the scoper's questions, 2026-10-03:
    - **Q1, a lone refused sibling: READ IT.** Set-aside only breaks a
      tie; where a refused supply is the only staged version of a table,
      a run reads it, so a single-file correction after a refused zip is
      judged on its own checks.
    - **Q3, what re-gates waiting siblings: ANY PROMOTION**, automatic as
      well as a person's - the same first-arrival logic. Terminates
      because a supply promotes at most once.
    - **Q4, which decisions trigger the re-check: EVERY DECISION THAT
      CHANGES WHAT A PERIOD RESOLVES A TABLE TO** - promote, reject,
      demote, re-file, substitute, de-substitute, inherit, un-inherit.
      Note REQ-PIPE-075 criterion 17 (re-file re-runs QA) is unmet and
      adjacent.
    - **Q2, which refusals set a supply aside: ANY RED VERDICT**, "could
      not read a table" included ("a pretty good reason to set a file
      aside too"). Refusals that are not about the data - slot already
      filled, off-cycle, inherited - do not. Safe against the mutual
      deadlock because Q1 reads a lone refused sibling and Q3 re-gates on
      every promotion. "Set aside" defined for the record: skipped when
      another run resolves the period's version of that table; left in
      staging, its own verdict standing, still a person's to decide.
    - **Q5, two staged versions of a sibling both re-gate green: RE-CHECK
      BOTH, PROMOTE THE ONE THAT ARRIVED MOST RECENTLY** (Keith). Note
      for drafting: this chooses by ARRIVAL time, which REQ-PIPE-105
      criterion 7 currently reserves to promoted supplies by PROMOTION
      time. CONFIRMED by Keith as a deliberate amendment of 105 criterion
      7 for this case only (two GREEN staged versions after a re-check),
      and the OLDER GREEN VERSION IS REJECTED BY RULE as superseded - an
      automatic rejection of a clean supply, which REQ-PIPE-076 (rejection
      is a person's decision) will need to allow for, naming the rule as
      actor and the newer supply as the reason.
    - **Q6: `mothman supply decide` WAITS** for the re-checks and shows
      the outcome. A queue can come later.
    - **Q7: the as-of view shows the window AS RECORDED, ANNOTATED** with
      the decision that later resolved it.
    - **Q8: a gate refusal is recorded in the DECISION LOG as a
      rule-actor entry**, the promotion-withheld pattern; nothing may read
      it as a person's decision.

    **SCENARIO RE-WALKED UNDER ALL OF THE ABOVE, 2026-10-03 - four issues
    found and decided (Keith):**
    1. **A supply that read a REFUSED own-arrival sibling is HELD**, not
       promoted. Without it the 05-20 resupply's clean Placements promoted
       against a refused Clients (its FK check can pass - Clients' 39
       failures were elsewhere), filled Q2's slot, and the fully clean
       05-27 set then met a filled slot: a quarter holding a combination
       the supplier never sent. Narrow - only the supplies that read the
       refused sibling, never the delivery (the retired hold stays
       retired). Keith's framing: it should read red anyway.
    2. **When EVERY version of a sibling is refused, a run reads the
       NEWEST-ARRIVED one** (extends Q1's "read the only one"). Found as a
       real deadlock: Investigations and Notifications read EACH OTHER
       (the only mutual pair today), so two clean single-file corrections
       after a bad zip each judged the other's set-aside predecessor and
       both stuck with nothing promoted to trigger a re-check.
    3. **Re-checks triggered during a zip wait until every file sharing
       its receipt instant has run** - otherwise Clients 05-27's promotion
       re-gated Placements 05-20 into Q2 before Placements 05-27 had run.
    4. **A decision that does not change what the period RESOLVES a table
       to triggers no re-check** - stops rule-rejections (Q5) and no-op
       rejects starting a second wave.
    5. **COST IS AN NFR, measured once built**: the wait on `supply
       decide` and the bootstrap's extra runs; Q6 (queueing) is revisited
       if decide exceeds a threshold Keith sets.

    **CHANGE OF DIRECTION, Keith 2026-10-03 afternoon: OPTION A replaces
    everything above from "DIRECTION" on.** Keith stepped back from the
    set-aside / re-gate design as "heading towards complicated territory
    with deadlocks and rerunning and uncertainty" - each rule had closed a
    hole the previous one opened, all from keeping "never choose between
    two waiting versions". Option A drops that assumption instead. The
    REQ-PIPE-118..121 drafts (scratchpad only, never committed) are
    SHELVED, not revised. Option A as settled in conversation:
    1. ONE WAITING VERSION PER TABLE PER PERIOD. A new file for a table
       moves every earlier UNACCEPTED version for the same period to
       SUPERSEDED; the new file is then checked as normal.
    2. SUPERSEDED IS ITS OWN STATE, likely its own schema. Never deleted,
       never "rejected"; the file and its recorded results are kept.
    3. FULLY REVERSIBLE BY A PERSON: a person can supersede or
       un-supersede. Un-superseding returns the file to staging, re-runs
       its QA, and the normal gate promotes it if green. Keith's worked
       case: reject the bad newer file, pull the earlier good one out of
       superseded, re-run, promote.
    4. GUARDS: a byte-for-byte identical resend supersedes nothing; an
       accept made on a supply superseded since it was shown is refused,
       saying so.
    5. UNCHANGED: two files for one table in ONE arrival are still
       contested, for a person. A resend into a period already holding a
       promoted supply still waits for a person.
    6. NOISY WHEN IT MATTERS: a promotion into a slot where another supply
       was waiting or was superseded gets a prominent decision-log entry,
       so a mis-filed (e.g. early next-period) supply is noticed and
       re-filed by a person. Keith judged the wrong-period case rare -
       quarterly gaps get a substitution long before the next quarter;
       daily supplies are scheduled extracts, and the calendar's early
       allowance covers quarterly - so noise, not a special rule.
    7. ONE SIMPLE RE-CHECK: when a supply is promoted, waiting supplies in
       that period whose cross-table checks read it are re-checked and the
       normal gate applied - covers a first correction arriving before
       its partner.
    8. MIXED RESENDS ACCEPTED: a single-table resend checked against the
       other tables of an earlier send may fail cross-table checks; the
       supplier resends both, and RAG thresholds on cross-table checks
       absorb expected churn.
    What Keith told us about real suppliers (for drafting): the period in
    a file name/content varies by supplier (daily likely just a date
    stamp); resends are the whole delivery for systemic issues, else
    individual tables, sometimes with cross-table effects; suppliers say
    a file replaces another only by email; an early next-period file
    overlapping an unresolved current one is rare.
    Residual narrow case noted: a not-yet-promoted (e.g. amber) fix can
    be superseded by a later non-identical resend - visible and
    reversible under 2-3.

    **OPTION A, ROUND TWO (Keith, 2026-10-03):**
    - **AMBER AUTO-PROMOTION BECOMES A SETTING** at data asset, collection
      and dataset level (nearest wins). Keith expects the quarterly asset
      to hold amber for a person at asset level, and the daily asset to
      let some collections/datasets auto-promote amber. NOTE: today amber
      ALREADY promotes itself into an empty slot (REQ-PIPE-075 criterion
      1; promotion.PROMOTES_ITSELF, whose comment gives the reason - holding
      every amber "is how a queue becomes noise nobody reads"). So this
      amends 075 criterion 1 rather than adding an option.
    - **A SECOND SETTING, same levels: whether a resupply into an
      already-promoted slot may replace it automatically** - never (today's
      behaviour, item 5 above), when green, or when green or amber. Keith
      expects the daily asset to opt in. A promoted supply replaced this
      way would move to SUPERSEDED like any other, so it stays reversible.
    - Asked: whether item 7's re-check also runs QA for already-promoted
      datasets (answered in conversation - see the next entry).

    **OPTION A CONFIRMED, Keith 2026-10-03** - the two settings (amber
    auto-promotion; resupply replacing a promoted supply), the byte-for-
    byte guard (an exact repeat of a file already held for the table and
    period is recorded as received but supersedes nothing and is not
    re-checked) and item 6 all agreed, with two emphases: item 6's
    "promoted while something else was waiting" must REALLY STAND OUT on
    the dashboard and in the decision log; and a promoted supply whose
    refreshed cross-table result has gone red must be shown, very
    clearly, as a RED PROMOTED supply. Item 7 confirmed as: arrival-time
    re-evaluation already refreshes promoted siblings' cross-table
    checks; a promotion re-gates WAITING supplies only; nothing promoted
    is ever demoted by a re-check (the one exception being the resupply
    setting). Next: delivery-scoper drafts from this entry.

    **SCOPED 2026-10-03 by delivery-scoper as option A: drafts
    REQ-PIPE-118..124 and REQ-DASH-125..127** (unsigned; scratchpad
    draft_option_a.yaml, validator OK). 118 one waiting version + the
    superseded state; 119 identical-resend guard; 120 a person supersedes /
    un-supersedes; 121 a promotion re-checks waiting readers; 122 amber
    setting; 123 replacement setting; 124 overtaking promotions logged;
    125 overtaking stands out; 126 red promoted supply shown clearly; 127
    superseded supplies and repeats in supply history. VERIFIED while
    relaying: it REVERSES two recorded Keith decisions - REQ-PIPE-076's
    "there is NO SUPERSEDED state" (2026-09-23) and REQ-PIPE-075's
    "auto-promotion is unconditional across both assets" (2026-09-26,
    which rejected per-asset and per-dataset flags as "set once and
    forgotten, and it fails quietly") - plus 105's "no arrival-time
    decision against anything in staging". Also amends 105 crits 6/7/8,
    079 crits 10/11, 075 crits 1/4, 076 crits 7/8, 082 crit 1, 074 crit 1;
    082 crit 9 (re-file "supersedes what is there") to be flagged.
    plans/supply-model.md ~3726 needs repointing when this lands. Four
    questions put to Keith (automation vs a person's decision; un-supersede
    beside a waiting version; whether setting-authorised replacements are
    "overtaking"; how long overtaking stands out).
    Keith's answers, same day:
    - **The rule applies even where a person has touched a supply** - it
      supersedes a supply a person returned to the queue, and the
      replacement setting may replace a hand-promoted one. One waiting
      version always holds; everything stays reversible. This also
      reverses 076's "automation only acts on a supply no human has
      touched" - a third reversal, to be read aloud at sign-off.
    - **Un-supersede beside a waiting version is REFUSED until resolved**:
      reject or supersede the waiting one first (his worked example).
    - **Setting-authorised replacements ARE recorded as overtaking, but
      as INFORMATIONAL** - present, not shouting. Only promotions the
      setting did not authorise stand out.
    - **How long overtaking stands out: FOREVER IN THE DECISION LOG; in
      the reporting layer (dashboard) until the next period's slot is
      filled.**
    Keith accepted all seven of the scoper's working assumptions as
    written (identical resend of a REJECTED file is checked again;
    un-supersede waits for its re-check; settings at asset/collection/
    dataset, not agency; CI refuses amber=hold with replacement=green-or-
    amber; overtaking one level above WARNING; a substituted or inherited
    next period counts as filled; a red promoted supply is dashboard-only)
    and that a re-file into an occupied slot moves the occupant to
    superseded. Next: sign-off walk-through.

    **SIGN-OFF ROUND, group 1 (118-121), Keith 2026-10-04:**
    - 118: asked how we know a file is "older" (answered: our own receipt
      instant, never anything in the file - see conversation) and whether
      a newer file after a contested same-zip pair supersedes BOTH (yes, as
      drafted: both are unaccepted waiting versions, so the contest
      resolves itself).
    - 119 (identical-resend guard): Keith questioned whether it is needed
      at all - "a file turns up, it's identical... it gets checked and
      pushed through... so what?" Under discussion.
    - 120: agreed.
    - 121: when a re-check leaves a waiting supply failing the
      auto-promotion rules AS RESOLVED FOR ITS DATASET (red; or amber where
      the amber setting is "hold"), that is a LARGE SHOUT in the decision
      log, so a person sees it and acts.
    - **119 DROPPED, noted** (Keith): without it an identical resend is
      re-checked and gets the same verdict; the only real cost is a
      pointless to-do item when a supplier double-sends onto a filled
      quarterly slot. Record in 118's decisions as considered and dropped;
      cheap to add later if duplicates become a nuisance.
    - **118 criterion 3 DROPPED** (Keith): "older" was read as the file's
      contents; it only ever meant processed-later-than-received, which the
      pipeline already prevents (always processed in receipt order; a
      hand-filed file's receipt is "now"). Replace with a plain statement:
      "newer" means received later by our own clock, and files are always
      processed in receipt order.
    - **GROUP 1 SIGNED OFF by Keith, 2026-10-04: REQ-PIPE-118 (criterion
      3 dropped, receipt-order statement in its place, 119's dropping
      noted), REQ-PIPE-120, REQ-PIPE-121 (with the large shout).**
      REQ-PIPE-119 dropped. Not yet written into requirements.yaml - the
      drafts go in once all groups are signed.

    **SIGN-OFF ROUND, group 2 (122-123), Keith 2026-10-04:**
    - **DEFECT FOUND, to fix IN THIS BATCH (Keith):** period_schema.newest()
      ranks a period's promoted versions by ARRIVAL key, but REQ-PIPE-105
      criterion 7 (signed) says newest-wins among PROMOTED supplies is by
      PROMOTION time. Today a period schema can hold several promoted
      versions of a table and readers take the newest - so the wrong one
      can be read after an out-of-order promotion. Failing test first.
    - Corrected for the record: today a green resupply into a FILLED slot
      does not auto-promote (the gate refuses "slot already filled"), and
      a person promoting a second supply leaves BOTH in the period schema
      with the newest read - nothing is superseded.
    - **Amber acknowledgement:** a person may be asked to ACKNOWLEDGE an
      auto-promoted amber supply - wanted on the quarterly asset for some
      problematic collections, not on the daily asset (noise). Keith
      expects the quarterly asset's asset-level default to be "promote,
      don't ask", toggled to "promote and ask" for some collections.
      ACKNOWLEDGE becomes a new decision type - reverses REQ-PIPE-091's
      "no acknowledgement entry type", accepted by Keith.
    - **Replaced accepted file:** Keith first chose "do as today" (leave
      it in the period schema, newest read), then reconsidered - he wants
      the PROMOTED SCHEMA CLEAN (no tables not actually used for the
      period) but worries the superseded area grows "massive and
      unwieldy". Being discussed.
    - **REPLACED ACCEPTED FILES GO TO SUPERSEDED** (Keith, settled): the
      period schema is what people AND EXTERNAL TOOLS read, so it must
      hold only what is in use - otherwise every consumer re-implements
      "which is the real one", or we maintain a separate list of tables.
      Superseded's growth is a RETENTION question (it is the same data
      either way) - a separate item, not this batch, unless Keith says
      otherwise. Raised as following from his reasoning: (1) EVERY
      promotion, including a person promoting a second supply by hand,
      leaves exactly ONE version per table in the period - the previous
      one moves to superseded; the newest() arrival-vs-promotion defect
      then becomes mostly moot by construction, but is still fixed and
      tested for periods already holding several; (2) each period exposes
      the promoted table under its PLAIN logical name (e.g. cp_clients),
      as inherited tables already are, so a person or tool queries
      <period>.cp_clients with no knowledge of arrival keys.
    - **AMBER: ONE SETTING, THREE VALUES** (Keith): hold | promote |
      promote-and-acknowledge. Quarterly asset expected: "promote" at asset
      level, "promote-and-acknowledge" for problematic collections; daily:
      "promote".
    - **PERIOD SCHEMA NAMING: KEEP STAMPED NAMES, PUBLISH THE RULE**
      (Keith). Rejected: renaming promoted tables to plain names (much code
      identifies a supply by its stamped name) and moving promoted tables
      to a separate storage schema behind plain-name views (Keith: a
      years-deep dumping ground that is hard for a human to look at).
      Instead: the period schema holds EXACTLY ONE object per logical
      table - `<table>__<arrival key>[__<ordinal>]` for a supply promoted
      into the period, or plain `<table>` for an inherited view - and the
      naming rule is published as a short contract for downstream
      consumers, who list the schema's tables at start-up and strip the
      stamp to find each base table. supply_db.split_staged already
      implements the parse.
    - **AMBER VALUE ORDER** (Keith): wherever the options are listed - docs,
      comments, schema, errors - in logical order, strictest first: hold,
      promote-and-acknowledge, promote.
    - **newest() FIX DROPPED** (Keith): with exactly one version per table
      per period there is nothing to rank, and he is happy to regenerate,
      so the multi-version code path goes away rather than being fixed.
    - **INHERITED AND SUBSTITUTED TABLES TAKE FULL STAMPED NAMES TOO**, and
      the chain check (inherit only from a period holding a real supply)
      asks the DATABASE whether an object is a table or a view rather than
      reading its name (Keith: "a very reasonable fix"). Amends REQ-PIPE-098
      and REQ-PIPE-084's "visible by its logical name" criteria.
    - **NEW IDEA, Keith: A MANIFEST IN EVERY PERIOD SCHEMA** - one row per
      table in the schema: its current name, its base name (the dataset's
      table), its TYPE (promoted / inherited / substituted), and the facts
      the name encodes today (supply, arrival stamp, the period an
      inherited or substituted table came from). External tools query it
      instead of parsing names, e.g. a downstream tool flagging
      substituted data to its own users. Being discussed.
    - **PERIOD SCHEMA TABLES TAKE PLAIN BASE NAMES** (Keith, revising the
      stamped-names call above): `cp_clients`, not `cp_clients__<stamp>`,
      for promoted, inherited and substituted alike. The facts the stamp
      carried move to the manifest. Cost acknowledged: every place the
      pipeline reads a stamped name in a period schema switches to looking
      the supply up; one version per table per period is what makes that
      safe.
    - **THE MANIFEST: `_manifest`, a VIEW over the decision log** (Keith:
      "that's elegant"), one row per table in the period: table_name,
      dataset_id, kind (promoted / inherited / substituted), supply,
      received_at (from the filing), from_period (inherited/substituted),
      decided_at, decided_by (RULE OR PERSON ONLY - no names), acknowledged,
      reason, promoted_status. Current health (e.g. red promoted) is kept
      OUT - it changes as checks re-run and belongs on the dashboard.
      Status at promotion is RECORDED ON THE PROMOTION DECISION ITSELF.
      Table name: Keith suggested writing it into the decision log beside
      dataset_id (rather than re-implementing the dataset->table mapping in
      SQL as well as in the pipeline) - being confirmed.
    - **TABLE NAME GOES INTO THE DECISION LOG** beside dataset_id (Keith,
      confirmed) - no dataset->table mapping re-implemented in SQL. Group 2
      (122, 123, plus the period-schema rules and _manifest) sent back to
      delivery-scoper for a full redraft, since the manifest and plain
      naming had never been through it.

    **SIGN-OFF ROUND, group 3 (124-127), Keith 2026-10-04:**
    - 126 agreed - and confirmed as NO NEW LOGIC: a promoted supply goes red
      on refreshed cross-table results exactly as a staged one would; it is
      only shown in a new place.
    - 127 agreed (identical-resend parts removed with 119).
    - 124/125: Keith asked for worked examples. Doing so exposed a flaw: as
      drafted, "promoted while another version was waiting or superseded"
      makes EVERY ordinary correction under option A an unauthorised
      overtaking that shouts (and, under 128, every hand promotion of a
      second supply too). Proposed: flag instead a promotion whose supply
      ARRIVED AFTER THE NEXT PERIOD'S EARLY-ARRIVAL WINDOW HAD OPENED - the
      actual "this may be next period's file" signal; ordinary corrections,
      supersessions and authorised replacements are history, not shouts.
      Awaiting Keith.
    Group 2 redrafted by delivery-scoper as 122, 123, 128 (one version per
    table per period), 129 (plain base names), 130 (_manifest); two
    questions put to Keith (promoting into a substituted/inherited slot;
    whether ACKNOWLEDGE replaces REQ-QAC-017's built /accept).
    - **124 AND 125 DROPPED** (Keith): filing's on-time-for-the-current-slot
      branch already files an early next-period file to the next period;
      the residue is indistinguishable by timing; history (127), authorised
      replacements (123) and the re-check shout (121) cover the rest.
    - **FOUND WHILE CHECKING THAT, and it reopened the filing rule.** A file
      arriving after the current period's on-time window, while an OLDER
      period is unfilled, is filed BACKWARD into the older period
      (oldest-claimable-unfilled), because a period's claim window never
      closes (Thread E, "late is always allowed") and monotonic filling
      (REQ-PIPE-063) closes an older period only once a LATER one is FILLED.
      REQ-PIPE-065's ambiguity flag does not fire for that shape (it looks
      only for unfilled periods older than the one chosen). Keith had
      believed periods closed when the next one opened.
    - **KEITH'S PROPOSAL: A PERIOD CLOSES WHEN THE NEXT PERIOD'S EARLY
      (CLAIM) WINDOW OPENS.** An unfilled period that closes is shown very
      clearly as red / no supply. Reasoning: on the DAILY asset nothing
      moves slowly enough for a person to decide, and a period with no data
      breaks everything downstream - "I'd rather have some data in there
      than nothing" - so a file that misses its window goes to the next
      period. On the QUARTERLY asset a missing supply is resolved
      (substitution, not-expected) long before the next quarter opens, so
      the slot is filled and nothing changes. REVERSES Thread E's "late is
      always allowed" / an open-ended claim window, and changes REQ-PIPE-063
      - to be confirmed and scoped.
    - **PERIOD CLOSING SETTLED (Keith):** not a setting - how the whole
      system works, both assets. RULE: a period CLOSES once the NEXT
      period's early (claim) window opens, or, where there is no early
      window, once the next period opens. Must hold for date-based
      calendars (quarterly) and cadence-based ones (daily). Reversals of
      Thread E's "late is always allowed" and REQ-PIPE-063's "closes only
      once a later period is filled" accepted as deliberate.
    - **PERIODS MUST NOT OVERLAP, ENFORCED** (Keith) - for both calendar
      kinds. Checked 2026-10-04: NOTHING enforces it today
      (validate_schedule.py checks dates, months and grace, never one
      period's windows against the next). Under the closing rule an
      overlap is worse than before: if the next period's window opens
      before this period is due, this period closes before it can ever be
      on time.
    - Sent to delivery-scoper as its OWN requirement(s), separate from
      option A. REQ-PIPE-065's ambiguity flag for backward filing (option
      b) is moot: a file can never fit two open periods.
    - **PERIOD CLOSING SCOPED** by delivery-scoper as drafts REQ-PIPE-131
      (a period closes once the next period's claim window opens; file to
      the one open slot, else resupply), REQ-PIPE-132 (a slot closing
      unfilled is final and reads as not supplied), REQ-DASH-133 (shown very
      clearly), REQ-PIPE-134 (non-overlap enforced in CI) - unsigned,
      scratchpad draft_period_closing.yaml. VERIFIED: a THIRD reversal -
      REQ-PIPE-062 records "Rejected CLOSING a slot's window when the next
      one opens ... Monday's supply landing Tuesday morning would file as
      Tuesday". Today's configuration passes 134's constraint (narrowest:
      Birth Registrations, 19 hours). One fork for Keith: next window must
      open after this period's due-plus-grace (drafted) or only after its
      due instant. 124/125 removed from draft_option_a.yaml.
    - **REQ-QAC-017 RETIRED** (Keith): ACKNOWLEDGE (122) replaces its
      per-run amber /accept; 017 is amended or retired in the same change.
    - Confirmed for 129: moving and renaming are ALTER TABLE ... SET SCHEMA
      / RENAME (supply_db.move_table already does the first) - catalogue
      changes only, no data copied.
    - Promoting INTO A SUBSTITUTED OR INHERITED SLOT: Keith - an INHERITED
      slot must not be replaced, since inheritance means nothing was
      expected; undecided on SUBSTITUTED - worked example requested.
    - **128 and 130 APPROVED** (Keith).
    - **129 APPROVED, both directions explicit:** renamed to the plain base
      name coming INTO a period, renamed back to its full stamped name on
      EVERY way out (superseded, demoted, rejected, re-filed) in the same
      transaction. The full name is rebuilt from the decision-log entry
      that put it there (table name + supply id are both on it), no second
      store.
    - **A PERSON PROMOTING INTO A SUBSTITUTED SLOT** (Keith, "option c"):
      warn that the substitution is about to be removed, then do it - TWO
      decision-log entries, a de-substitute and then the promotion, in one
      transaction. **INTO AN INHERITED SLOT: REFUSED** until a person takes
      a separate un-inherit action (inheritance means nothing was expected).
    - **GROUP 2 SIGNED OFF by Keith, 2026-10-04: REQ-PIPE-122, 123, 128,
      129, 130** (with the points above). Group 3: 126 and 127 agreed, 124
      and 125 dropped. Next: superseded retention, then period closing.
    - **SUPERSEDED IS PER PERIOD** (Keith, option A): superseded_<period>
      beside each period's own schema, not one global area - small to
      browse, and it makes retention by period trivial later. Amends the
      draft REQ-PIPE-118's "one superseded schema".
    - **RETENTION DEFERRED** to its own later requirement - plans/running-thoughts.md #60.
    - **SUPERSEDED SCHEMA NAMING AND LIFECYCLE** (Keith): a SUFFIX, not a
      prefix - `period_2026_q2_superseded` sorts directly after
      `period_2026_q2`, so a person browsing sees each period with its
      set-aside versions beside it. Created ONLY when a first table needs
      it, and DROPPED when its last table leaves. NOTE for drafting: the
      period_of() parser reads schema names back into periods, so it must
      not mistake a `_superseded` schema for a period.

    **SIGN-OFF ROUND, period closing (131-134), Keith 2026-10-04:**
    - 131 broadly agreed. A file that ARRIVED inside a period but is
      PROCESSED after it closes must be honoured as arriving in the window
      - already the drafted rule (filing is by RECEIPT instant, never
      processing time); to be stated plainly.
    - 131 "next period" for a dataset that participates in only some
      periods (delivery_months, e.g. Case Workers Feb + Aug): Keith -
      its period CLOSES WHEN THE CALENDAR PERIOD IT PARTICIPATES IN
      CLOSES, not when its own next participating period opens. A dataset
      wanting a longer period gets its own calendar (e.g. an annual one).
      Reverses the scoper's working assumption 1. Consequence to confirm:
      a gap with no open slot (Case Workers May-August), where an arrival
      is held for a person.
    - 132 agreed; Keith assumed its listed responses are all actions a
      person can take on GitHub or in the terminal. CHECKED: substitute
      and re-file are (REQ-GHUB-082's eight), "record as not supplied" is
      NOT a decision that exists - to settle.
    - 133 agreed. 134 agreed, constraint "after due time plus grace".
    - The 118 change (superseded per period, `_superseded` suffix, created
      and dropped on demand) approved.
    - Follow-ups settled (Keith): (1) filing is by receipt instant, stated
      in as many words; (2) a partially-participating dataset's period
      closes with its calendar period, and an arrival in a gap with no
      open slot is HELD FOR A PERSON - agreed; (3) **A NINTH FILING
      DECISION, "MARK AS NOT SUPPLIED"**, person-only with a MANDATORY
      reason, changing no data; the period then reads "not supplied
      (accepted)" and leaves the to-do list. Keith's framing: it pairs with
      `not_expected` in configuration - that is what we know AHEAD of time,
      this is the tactical, operational decision AFTER the fact. Amends
      REQ-GHUB-082 criterion 1's list of eight.
    - **PERIOD CLOSING SIGNED OFF by Keith, 2026-10-04: REQ-PIPE-131,
      132, REQ-DASH-133, REQ-PIPE-134**, with the points above. All signed
      drafts go back to delivery-scoper for one final pass applying every
      sign-off change, then into requirements.yaml.
    - **SCENARIOS FOR THIS BATCH, VISIBLE IN THE REPORTING UI** (Keith,
      2026-10-04): little test cases showing each shape discussed - built
      on the existing test-scenario register + generator injection +
      SCENARIOS.md map (REQ-GEN-045), not a parallel mechanism. Candidate
      shapes: clean resend superseding a failed one (and a same-zip pair
      resolved by a later file); a correction before its partner, promoted
      on re-check, and one whose re-check still fails (the shout); amber
      held / promote-and-acknowledge awaiting acknowledgement; daily
      replacement; red promoted; a late daily file closing the missed day
      empty, and a Case Workers arrival in its gap held for a person; the
      manifest showing promoted/inherited/substituted; and person
      decisions (un-supersede, mark as not supplied, acknowledge,
      substitute). **SCRIPTED HUMAN DECISIONS WILL BE BUILT** (Keith) - the
      generator produces files only today, so synthetic history gains a
      way to play back seeded decisions ("on <date> a person
      un-supersedes X"). Its own requirement(s), via delivery-scoper after
      the final pass on the batch. **THE SCENARIO MAP IS ALSO SHOWN INSIDE
      THE DASHBOARD** (Keith) - e.g. a Scenarios tab beside Plans and Demo,
      embedded like PLANS. Inside the dashboard it can LINK to the page
      (the dashboard knows its own routes, which is why SCENARIOS.md gives
      coordinates not URLs). **The dataset pages STAY UNLABELLED** (Keith) -
      a planted red looks exactly like a real one; ONLY the Scenarios tab
      says what was planted.
    - **CHAIN PROTECTION UNDER PLAIN NAMES - checked 2026-10-04 (Keith
      asked).** "A later period stands on this supply" is asked of the
      DECISION LOG by dataset + SUPPLY ID (decision_log.periods_standing_on,
      REQ-PIPE-084 criterion 11), never by table name, so plain names
      change nothing; substitution/inheritance views are schema-qualified
      (`period_2026_q2.cp_clients`). ONE HAZARD WORTH A GUARD when 128/129
      are built: PostgreSQL views bind to a table by OID, so if any path
      ever moved or renamed a stood-on table WITHOUT the log check, the
      later period's view would silently FOLLOW it into
      `_superseded` and keep reading set-aside data as current. Proposed
      second line of defence: refuse a move-out when pg_depend shows a
      dependent view, with a test.
    - **RE-FILE'S EFFECT is from an EARLIER batch**, not this one:
      REQ-GHUB-082 (signed 2026-09-28) offers re-file on both routes but
      records its effect as unmet, blocked by REQ-PIPE-079; REQ-PIPE-075
      criterion 17 (re-run QA when promoted or re-filed into a different
      period) likewise. 079's overlay is now wired, so the blocker may be
      largely cleared. 128, 131 and 132 name re-file as a remedy, so it
      belongs early in the build queue.
    - **RE-FILE'S EFFECT WILL BE BUILT** (Keith, 2026-10-04) - to be
      scoped; Keith asked what in REQ-PIPE-079 / 075 criterion 17 blocks it.
    - **SCENARIOS (REQ-GEN-135..DASH-139, scratchpad draft_scenarios.yaml):
      Keith delegates the detail to the scoper's drafts** - surface only
      really major decisions. Question 1 answered: **a TOP-LEVEL Scenarios
      tab** (139 stays) beside Plans and Demo, replacing REQ-DASH-046's
      header drawer. Question 2 (where the scripted decisions' synthetic
      actor lives) re-explained. Question 3 (whole-history settings vs
      scoped) opened a bigger question from Keith: **can changing one of
      the new settings later change or misrepresent PAST history?** -
      answered in conversation (see the next entry once settled).
    - Keith asked how to make the pg_depend "second line of defence" (a
      stood-on table must never be moved out of its period) 100% robust.
    - **STOOD-ON-TABLE GUARD: ALL THREE LAYERS** (Keith) - (1) the
      decision-log rule; (2) one door for every move/rename out of a period,
      locking the table and checking pg_depend in the same transaction, with
      a test that nothing else issues that DDL; (3) a PostgreSQL EVENT
      TRIGGER on ALTER TABLE refusing a move-out while a view depends on
      it, catching any path including a person at a SQL console. Each layer
      tested to refuse on its own. Event triggers need elevated rights -
      verify the target platform supports them. Goes into 128/129.
    - **BUILD ORDER (Keith): REQ-PIPE-079 finished FIRST** (verify it is
      built; build what is not), **then RE-FILE's effect, then today's
      batch.** Keith asked whether re-file moves the supply into the period
      schema or back to STAGING with its new period, then QA - to settle in
      re-file scoping. REQ-PIPE-075 criterion 17 agreed.
    - **SYNTHETIC ACTOR: option (a)** (Keith) - a synthetic person in
      contract/people.yaml, locked to synthetic playback, refused on
      GitHub.
    - **SETTINGS ARE EFFECTIVE-DATED, VERSIONED LIKE CALENDARS** (Keith):
      the amber and replacement settings carry effective dates so a change
      can never reach back and alter how the past is represented; each
      decision records the setting that applied and every display of the
      past reads the RECORDED value, never the current one. Amends signed
      REQ-PIPE-122 and 123 (wording to be approved). Synthetic history
      re-replaying under today's settings on regenerate is accepted as
      harmless (synthetic only); effective-dating also lets one synthetic
      history show both eras of a setting.
    - **RE-FILE MECHANICS SETTLED (Keith):** a re-filed supply goes BACK TO
      STAGING filed to its new period, is QA'd there, and the normal gate
      decides. RE-FILE WINS: it supersedes a version already waiting in the
      target period. If the re-filed supply then fails, it waits red and the
      displaced version sits intact in that period's _superseded schema -
      reject, then un-supersede (REQ-PIPE-120). **A person making a re-file
      is WARNED AND MUST CONFIRM whenever it will displace another table,
      and the warning names EVERY consequence** - e.g. "This removes Q3's
      accepted Clients and supersedes Q2's waiting Clients from 14 May" -
      so leaving an old period without its promoted table is never a
      surprise.
    - **AMENDMENTS WRITTEN, 2026-10-04 (Keith approved both wordings):**
      effective-dated settings into REQ-PIPE-122/123, and the three-layer
      guard into REQ-PIPE-129. **No synthetic exception** (Keith): the
      scenario eras are authored straight into this asset's own
      `data-asset.yaml` as dated versions, unlabelled, since adding a new
      version - even a past-dated one - is already the sanctioned mechanism
      for calendars. Pre-build UX review accepted and written in: one
      prompt with a warning panel, warnings say how to undo, paste-able
      fixes on refusal, `mothman supply superseded`, un-supersede names its
      version, the shout undimmed, red-promoted as a label, outcomes in
      supply history, one marker line per agency card, 'held' not reused.
      Keith's answers to the six UX questions: stale confirmation refused
      and re-shown on both routes; **a closed unfilled period rolls up RED
      to the agency** (against the reviewer's label-only lean); consecutive
      gaps grouped; not-supplied (accepted) quieter and outside the red
      roll-up but still visible at collection and agency level; as-of
      before a supply turned red shows it as it was, annotated. Still open:
      the interrupted-wait question (re-check owed) and the as-of test,
      both pending a worked example.
    - **CLOSED THE SAME DAY (Keith):** past setting versions are corrected
      exactly as calendars are (allowed only with an added changelog line);
      the setting version is picked by the instant the decision takes
      effect; an interrupted terminal wait leaves a **re-check owed**
      record, written in the promotion's own transaction and cleared when
      the re-check completes (one transaction around both rejected: the
      tools cannot see an uncommitted promotion, the lock would block the
      period, and a failed re-check would undo the promotion).
    - **SCENARIOS AND RE-FILE SIGNED, 2026-10-04 (Keith).** REQ-GEN-135..
      REQ-DASH-139 as the scoper drafted them, including its settings-era
      choice; the asset's synthetic declaration stays as playback's lock
      only. REQ-PIPE-140..REQ-GHUB-142 with Keith's changes: "fails" means
      the run breaking, and a broken run is owed and retried; a re-filed
      supply is gated under TODAY's settings; "re-file wins" is over
      versions waiting in staging only - **a promoted version in the target
      period stays until the re-filed one is promoted** (082 criterion 9
      reworded, no gap); re-file is REFUSED for a rejected supply, one file
      of a contested pair (saying why), and into an inherited period
      ("force them to un-inherit and then re-file rather than ... leaving
      it dangling in staging"). **ONE MECHANISM for the knock-on effects of
      ANY table arriving in or leaving a period schema** - REQ-PIPE-121
      widened from "only promotion triggers it" to every arrival and
      departure.
    - **ARCHITECT REVIEW ANSWERED, 2026-10-04 (Keith):** withheld bug
      tested first (proven - post-build-review #75); **re-file built
      AFTER REQ-PIPE-128/129**, revising "079, then re-file, then the
      batch"; REQ-PIPE-077 retired by 131; a `retired` requirement status
      (drafted as REQ-DOCS-143, unsigned); `_manifest` keeps every reason
      as signed; the database guard also refuses cascaded drops of period
      views; a platform without event triggers runs on two guards and
      says so. Technical findings written into 118/121/128/129/130/131/
      132/133 as amendments.
    - **ONE KNOCK-ON HANDLER, SETTLED 2026-10-04 (Keith):** every table
      arriving in or leaving a period re-checks the checks that READ it -
      waiting AND promoted readers, nothing unrelated ("otherwise we're
      not telling the real truth"); a promoted reader going red is shown,
      never demoted. One run per decision; the newest CAUSE wins, not the
      last run to finish; shouts grouped per decision; a person's warning
      says which readers will be re-checked and may go red. Staging
      arrivals stay in their own first run (079). REQ-DOCS-143 signed,
      either grain of retirement allowed. Correction recorded in passing:
      the RULE does supersede in two places (118's newer-file supersession,
      123's opt-in replacement) - it is re-checks that never reject,
      demote or supersede.
    - **ONE VIEW OF WHAT A SLOT HOLDS, and the BUILD ORDER REVISED,
      2026-10-04 (Keith).** His idea: bake "what does this slot hold" into
      the database once and have everything read it, rather than five
      Python readers re-interpreting the decision log. Settled as a
      metadata-schema view (with an as-at form) built only from decisions
      that CHANGE a slot; every reader and each period's `_manifest` go
      through it (REQ-PIPE-130). It fixes post-build-review #75 by
      construction. **Revised order:** REQ-DOCS-143 (retired status) ->
      the slot view + resolving/annotating split (with #75's test) -> 134,
      131, 132, 133, 122, 118, 120, 128+129, re-file (140-142), the rest of
      130, 123, 121, 126, 127. A planted scenario shows a reader re-checked
      after both a newer-file supersession and an automatic replacement
      (REQ-GEN-136).
    - **REQ-PIPE-144 SIGNED, 2026-10-04 (Keith)** - the qa schema states
      each fact once; slotted straight after REQ-PIPE-131, before re-file.
      Order now: REQ-DOCS-143 -> slot view + withheld fix -> 134, 131,
      **144**, 132, 133, 122, 118, 120, 128+129, re-file (140-142), the
      rest of 130, 123, 121, 126, 127.
    - **079 LEFTOVERS RE-POINTED, 2026-10-04.** Five built requirements
      still named REQ-PIPE-079 as their blocker. Re-tested, not cleared:
      REQ-PIPE-035 criterion 6 is now MET (red-for-unrun produced in a real
      run); its criteria 7-8 (temporal reference) were never 079's and are
      now UNOWNED, the drift reference REQ-QAC-108 the likely home.
      REQ-PIPE-075 crit 17 -> 140/141; REQ-GHUB-082 crit 2 -> 141;
      REQ-PIPE-084 crits 6/14 and REQ-PIPE-099 crit 11 -> 121/140. Sprint
      tags moved to match: 11 blocked, 13 and 18 in-progress.
    - **CALENDAR DRAFTS 110-113, PART-SETTLED 2026-10-04 (Keith).**
      110: `participates` REPLACES `delivery_months`; `not_expected` STAYS
      as its own thing - "a once-off decision, or a series of once-off
      decisions we might make ahead of time", where participation is an
      ongoing one. 111: point 1 MATCHES CALENDARS (a past date can be
      corrected when the change adds a changelog line; 111's "a changelog
      never licenses it" is dropped); point 2 (refusing ADDED past-dated
      entries, and freezing every effective-dated setting) still with
      Keith. 112: the timezone STAYS in `data-asset.yaml` (wider than the
      calendar) and IS worth versioning now. 113: deduplicated - its
      overlap check is REQ-PIPE-134's; it keeps only where a due instant
      comes from. Still open: slaProperties' `frequency`, 111 point 2.
      Then all four go back to the scoper.
    - **PARKED, 2026-10-04 afternoon (Keith): CHANGING A PAST DELIVERY
      AGREEMENT.** "This calendar thing is doing my head in ... we'll come
      back to it once we've built the stuff that we've been scoping today.
      I need a clear head." NOT DECIDED - recorded so it is not re-derived
      or quietly settled. Calendar drafts REQ-PIPE-110-113 are NOT sent to
      the scoper until it is.

      THE QUESTION: may a past date (or setting/timezone version) ever
      change, given due instants are COMPUTED from config on every read, so
      a change re-judges history (lateness flips, the previous period's
      close moves, worst case a filed supply now "belongs" to another
      period)?

      WHERE EACH POSITION CAME FROM:
      - REQ-PIPE-050 (built 2026-09-23): "say what you did" - a past date
        may change if the change ADDS a changelog line.
      - REQ-PIPE-111 (drafted 2026-09-28, Keith explicit): NO ESCAPE HATCH;
        a correction is a new version from a date forward only.
      - This morning Keith chose "match calendars" (= 050's rule) and "no
        synthetic exception" on a framing that described 050's rule as how
        calendars work WITHOUT saying 111 recorded his decision to drop it.
        Owned as the main session's mistake; both answers are written into
        signed REQ-PIPE-122 (its criterion protecting past setting versions,
        and its 'NO SYNTHETIC EXCEPTION' decision) and are NOW IN QUESTION.
        Resolve before building 122.
        **RESOLVED FOR SETTINGS THE SAME AFTERNOON (Keith):** a setting's
        past is RECORDED on every decision, so a past version is inert and
        never needs correcting - REQ-PIPE-122/123 now freeze past setting
        versions outright (no changelog route), allow new versions only
        from today, and let only a synthetic asset add past-dated ones (for
        REQ-GEN-136's eras). 122 no longer waits on the calendar question.

      THE SCENARIO WALKED THROUGH: Q3 authored 1 Aug, agreement says 2 Aug.
      Noticed ON 1 Aug: 111 allows it (the date has not passed), but it
      quietly moves Q2's close a day into the past. Noticed ON 2 Aug: 111
      refuses, a new version cannot reach Q3, and the files show LATE
      forever with no way to say the calendar was wrong.

      OPTIONS ON THE TABLE (none chosen):
      (a) 111 strict, plus a recorded "excuse lateness" decision - config
          never changes its past; a person corrects the JUDGEMENT.
      (b) 111 strict by default plus a DECLARED CORRECTION route - Keith's
          instinct ("we do need to offer an escape hatch, with the
          acknowledgement that it will change history"): a changelog entry
          `kind: correction` naming what it corrects; `mothman schedule
          correction-impact` previews every consequence; the commit hook
          and CI refuse a past change without one; the next pipeline run
          records it in the decision log, re-judges, flags the dashboard,
          and raises a re-file item for any supply now in the wrong period
          (needs REQ-PIPE-141). BACKSTOP against bypassing git (--no-verify,
          unprotected branch, force-push, edits on a server): the database
          remembers what the calendar said about each judged period and the
          pipeline refuses a dataset whose past changed undeclared.
          Settings, timezone and synthetic eras would use the same route.
      (c) 050's rule as built - correctable with any added changelog line.
      Keith's lean when parked: strict by default with an escape hatch,
      i.e. (b), but "not sure which way to go".

      **KEITH'S NEW LEAN, 2026-10-05 (logged mid-sprint, to pick up AFTER
      sprints 9-14; not decided, not scoped):** make it STRICT with NO
      escape hatch - REQ-PIPE-111 as drafted, dropping (b)'s correction
      route. His reasoning, in his own words: "what's the worst that can
      happen? Something legit gets demoted and we have to refile two
      datasets and re-run QA on them?" The fix for a wrong calendar is
      then not a config route at all but the ordinary decision tools:
      "make sure that we're giving humans all of the tools they need to
      set everything back to rights" - which points at re-file
      (REQ-PIPE-141), re-run on demand (REQ-PIPE-140), demote/promote and
      un-supersede, all being built in this run of sprints.
      To walk through when it is picked up: the "noticed ON 2 Aug"
      scenario above (a new version cannot reach Q3, so its files read
      LATE forever) - does strict-plus-tools answer it, or does it still
      want something like (a)'s recorded "excuse lateness" decision, since
      re-filing moves a supply between periods but does not change when
      the period was due? And confirm REQ-PIPE-050's built changelog
      route is then removed, and what that means for REQ-PIPE-122/123's
      settings rules, which were settled separately.

      SETTLED THE SAME AFTERNOON AND NOT IN QUESTION: 110 - `participates`
      replaces `delivery_months`, `not_expected` stays (one-off decisions);
      `slaProperties` deleted entirely including `frequency`. 112 - the
      timezone stays in data-asset.yaml and is versioned now. 113 -
      deduplicated against REQ-PIPE-134.
    - **REQ-PIPE-115 SIGNED, REQ-QAC-145 PARKED, 2026-10-04 (Keith).** 115:
      a dataset whose own table cannot be read shows ONE red for the period
      that rolls up (REVERSING the earlier per-check choice - "all I really
      want to see is ... a data set level quite clearly that it's red
      because it's contested"); held reuses REQ-DASH-070's item, contested
      gets a new 'Two files, choose one' kind. 145 (CI: every dbt test
      dropped with a table declares it reads it): "we may or may not decide
      to keep dbt, but I would like to keep the shape of this check" -
      registered unsigned with a PARKED open question.
    - **REQ-PIPE-081 JOINS THE BATCH, 2026-10-04 (Keith).** Build order
      now: REQ-DOCS-143 -> slot view + withheld fix -> 134, 131, 144,
      132, then **133 together with 081's page switch** (both replace
      clipDatasetToAsOf; 081 reads the slot view's as-at form), 122, 118,
      120, 128+129, **081's census**, re-file (140-142), the rest of 130,
      123, 121, 126, 127, then **081's "In place on" rename** as a
      standalone change; REQ-PIPE-115 alongside where it fits.
    - **BUILD ORDER, 2026-10-04 late afternoon (Keith).** Step 1
      (REQ-DOCS-143, retired status) is BUILT. Step 2 (the slot view + the
      withheld fix) waits for Keith's go - "not yet". The environment-safety
      group signed today (REQ-PIPE-093, 107, 146, REQ-TEST-114) goes AFTER
      the batch. Placed the same afternoon: REQ-PIPE-103's amendment
      (stated original arrival) and the new REQ-PIPE-147 (who filed it) go
      RIGHT AFTER 144, which they both build on; REQ-QAC-108's amendment
      (compare with the older accepted supply and flag it) goes ALONGSIDE
      REQ-PIPE-115.
    - **086 REFRESH ANSWERS, 2026-10-04 (Keith), not yet signed.** The
      delivery-scoper found most of REQ-PIPE-086 already covered (chiefly
      by REQ-PIPE-103) and narrowed it to the terminal routes that still
      skip the shared per-arrival lifecycle. Keith's answers: keep the 086
      id, narrowed; synthetic "Record" on an already-recorded arrival is
      not offered until REQ-PIPE-140 exists and then goes only through it;
      aws/lambda_handlers/ move onto the shared lifecycle now; a kept file
      belonging to the other collection is refused before anything is
      written; a new REQ-TEST-150 reports what the lifecycle decided, and
      a trial says what recognition would do (display only); and a NEW
      requirement for an incremental "process" command (Thread L) that
      finishes owed work and reconciles tickets without generating data -
      because "the next pipeline run" the signed batch relies on is today
      a synthetic regenerate nobody would run in production. Defects found
      on the way: post-build-review #81 (automatic promotions record the
      operator's git identity, not the rule) and #82 (the real hand-filed
      routes never offer the decision afterwards).
      **SIGNED later the same evening**: REQ-PIPE-086 (12 criteria),
      REQ-TEST-150 (10), REQ-PIPE-151 `mothman pipeline process` (19) and
      REQ-PIPE-152 the Lambda handlers (11), plus the re-pointing of
      REQ-PIPE-121 criterion 16, REQ-PIPE-140 criterion 8 and REQ-PIPE-120's
      NFR at 151. PLACED the same evening (Keith): AFTER the batch -
      post-build-review #81 (promotion actor) first, then 151, then 086,
      150 and 152 - since 151 finishes the owed work 121, 140 and 120
      create and logs every gate outcome under the rule's name.
    - **PRE-BUILD REVIEWS, 2026-10-04 evening (Keith's ask).** delivery-architect
      (three passes), delivery-dashboard-ux and delivery-cli-ux reviewed
      everything scoper-refreshed today: 093/107/146/114, 103-amendment/147,
      096/097/148/153, 115, 108-amendment, 086/150/151/152. ANSWERED SO
      FAR (Keith):
      - DASHBOARD: a blocked dataset's own columns read the existing grey
        "No data"; the "waiting for a person" panel, markers and red are
        all judged at the SAME as-of instant (the build carries raised and
        resolved instants); a rejected failed load leaves a supply-history
        row ("Could not be loaded - rejected by X, when: why"); the label
        is "Could not be loaded" everywhere, replacing "Failed load".
      - CLI: in a confirming environment the typed id REPLACES the y/N and
        is asked ONCE PER FLOW; keep-or-trial is asked before the drift
        reference, which is asked for (and required as a flag) only for a
        trial; an already-recorded synthetic arrival is marked "recorded"
        in the picker, runs as a trial with one line why, and `--commit`
        on it is refused naming `--trial`; `pipeline process` is on the
        TUI menu and a PERSON starting it in production types the id
        (Keith chose this over the reviewer's "no typed id").
      - ROUND 2 (Keith): the single per-arrival function (086 criterion 2)
        is extracted FIRST, before the batch, as a behaviour-preserving
        refactor proven by regenerate-and-diff, so every later rule lands
        once; a recorded failed-load reason is OUR OWN WORDS ONLY (kind,
        line, field count, column) - the library's message goes to the
        operator's terminal and is never recorded; the Lambda handler only
        RECORDS the delivery rows and then runs the processing pass, so one
        processor keeps global receipt order; 107's newer-schema refusal
        (criteria 13-14) is built INSIDE 144's change, and 093/107 go
        before 151/152, with 114 alongside 150.
      - ROUND 3 (Keith): a failed arrival in a processing pass skips the
        REST OF ITS COLLECTION for that pass (other collections continue,
        exit non-zero, retried next pass); ONE pass lock taken by
        `pipeline process`, `run`, `bootstrap` and `regenerate-history`,
        each refusing while another holds it and saying which and since
        when; `pipeline run` on a database with history REFUSES, pointing
        at `mothman env reset-synthetic`; a supply with no slot counts as
        gated by its OPEN ASSIGNMENT HOLD (REQ-PIPE-064), and 144
        criterion 13 is to be reworded to match built 105 criterion 6
        (contested pairs ARE filed, under #1) - wording to Keith to sign.
      - ROUND 4 (Keith): an S3-only delivery stores its object's
        STORAGE URI on qa.delivery_file (152, bump coordinated with 144)
        and the processing pass gets READ-ONLY access to the arriving
        bucket (151's security NFR corrected); test databases are marked
        with a new `test` ENVIRONMENT that only fixtures set (publishes,
        confirmation and ticketing off); the ticket REPOSITORY lives in
        data-asset.yaml, with ticketing a yes/no per environment and
        refused loudly when on with no repository; and 128's "one prompt"
        holds - in a confirming environment the warning panel sits above
        the typed id, which is the only confirmation.
      - ROUND 5 (Keith): `regenerate-history` is refused wherever the
        asset is not declared synthetic, and is a candidate to retire into
        144's `reset-synthetic` plus a bootstrap; 093 and 107 cover the DEV
        CONTAINER (MOTHMAN_ENVIRONMENT=local in devcontainer.json, a mark
        in post-create.sh); the TUI keeps the environment visible with a
        PERSISTENT BOTTOM TOOLBAR (Keith's pick over prefixing prompts -
        the reviewer flagged it as unverified with questionary and the
        cast recorder, so it needs a quick spike before 114's criterion is
        reworded); and a Child Protection S3 prefix offers EACH OBJECT'S
        OWN LastModified, confirmed as a set in one step - an amendment to
        103's "state once" decision, wording to Keith to sign.
      - ROUND 6 (Keith): file-check results keep EVERY ATTEMPT, tagged with
        the load attempt (096 criterion 7 amended); a failed-load item and a
        hold OPEN AT THE SUPPLY'S RECEIPT INSTANT, not the wall clock (148
        criterion 3, 115 criterion 12, 153 criterion 2); 108's "no earlier
        accepted supply" record is written by EVIDENTLY itself, not under
        `unrunnable`; and REQ-DASH-070 criteria 5 and 7 get AMENDED wording
        for Keith to sign.
      - ROUND 7 (Keith): exit codes are DISTINCT - 0 ok, 1 red checks, 2 a
        stage or arrival failed, 75 another pass is running; a kept
        multi-arrival run shows failing and warning checks in full and
        passes as a count per dataset (`--all-checks` for everything),
        ending on the lifecycle summary; a fixed and RELOADED failed file
        becomes OWED and the next processing pass checks it THROUGH
        REQ-PIPE-140's re-check, as a new run that keeps the first; a
        contested pair where one file is refused STAYS CONTESTED; the
        synthetic history IS INJECTED with a refused file and a
        column-order warning (Keith's pick over test-only fixtures - it
        changes every bootstrap's output and 144's before/after proof, so
        it needs its own REQ-GEN amendment and its own regenerate); 151's
        refusal reasons gain "could not be loaded"; and 148/115 gain the
        dashboard reviewer's three must-fixes (the queue copy that says
        items never change status; a reason row instead of the previous
        supply's figures; a supply-history row for a refused or failed
        supply).
      NEXT: draft every resulting amendment as exact before/after wording
      for Keith to sign - a large batch touching roughly 086, 093, 096,
      097, 103, 107, 108, 114, 115, 128, 144, 147, 148, 151, 152, 153,
      REQ-DASH-070 and a REQ-GEN item - via delivery-scoper, then place
      the extraction of 086's per-arrival function FIRST in the build
      order.
      **HOW THOSE AMENDMENTS ARE SIGNED (Keith, 2026-10-04 evening):**
      "I'm happy for you to turn it into exact amendment wording, but I
      don't feel a need to review all of it. Only bring me the really high
      value stuff." So each amendment is classed HIGH VALUE (shown to
      Keith: changes what a person sees or must do beyond what he chose,
      touches privacy or security, reverses or narrows an earlier
      decision of his, changes a BUILT requirement's claims, or needed a
      choice between readings) or ROUTINE (a faithful transcription of an
      answer he gave), applied on this blanket approval and recorded as
      such in each requirement's decisions. When unsure, HIGH VALUE.
      **DONE THE SAME EVENING.** 78 amendments across 21 requirements: 53
      routine applied on the blanket approval; 25 high-value presented as
      eight questions and signed, with these answers - REQ-DASH-070's
      three changes signed as worded; choosing one file of a contested
      pair RE-FILES it where its own receipt gives a different period or
      classification; the privacy and S3 read-access wording signed; a
      scripted S3 keep takes `--originally-received storage`; a drift
      reference passed with `--commit` is REFUSED; "a person" starting
      `pipeline process` means a terminal is attached; the `test`
      environment and the corrected reason-row wording signed. DEFERRED by
      Keith: what a Lambda does when its pass is refused as busy ("decide
      when we focus on building the aws side later"), kept as an open
      question on REQ-PIPE-152.
    - **OVERNIGHT SPRINT PLAN, 2026-10-04 ~20:00 Perth (Keith's go: "Yes,
      all in order").** REQ-PIPE-153 goes straight after REQ-DASH-148.
      Scope: every requirement signed 2026-10-03/04 still unbuilt (~38,
      ~500 criteria). NOT all of it fits one night; done in this order,
      each sprint complete (gates, selective tests, critics, CI checked)
      and pushed before the next starts, so the night stops at a clean
      boundary wherever it ends:
      1. REQ-PIPE-086 criterion 2 only - extract the one per-arrival
         function, behaviour-preserving, proven by REQ-TEST-116's
         bootstrap equivalence test.
      2. REQ-PIPE-130's slot view (+ as-at form), the withheld fix
         (post-build-review #75), and #85 (drift reference) on it.
      3. REQ-PIPE-134, REQ-PIPE-131.
      4. REQ-PIPE-144, with REQ-PIPE-107 criteria 13-14 inside it.
      5. REQ-PIPE-103's amendment and REQ-PIPE-147.
      6. REQ-PIPE-115 + REQ-QAC-108's amendment, then REQ-DASH-148, then
         REQ-PIPE-153.
      7. REQ-PIPE-132, REQ-DASH-133 with REQ-PIPE-081's page switch.
      8. REQ-PIPE-122, 118, 120, 128+129, then 081's census.
      9. REQ-PIPE-140-142 (re-file).
      10. The rest of REQ-PIPE-130, then 123, 121, REQ-DASH-126, 127,
          then 081's "In place on" rename.
      11. REQ-GEN-135-139 (batch scenarios).
      12. REQ-QAC-096, REQ-DASH-097, REQ-GEN-044's injections (own
          regenerate).
      13. REQ-PIPE-093, 107, 146, then REQ-TEST-114 with REQ-TEST-150.
      14. REQ-PIPE-151, the rest of REQ-PIPE-086.
      OUT: REQ-PIPE-152 (its busy-case question is deferred to the AWS
      work), REQ-QAC-145 and the calendar drafts (parked), REQ-TEST-117
      (parked CI cache).
      STANDING PERMISSIONS FOR THE NIGHT (Keith): rebootstrap the local
      database as needed; commit, push and write CHANGELOG entries; run
      delivery-critic and the UX critics after each build, fix minor
      findings and log significant ones; flip status to built and delete
      superseded plans prose. FORKS: take the recommended option, mark it
      PROVISIONAL in the requirement's decisions, and list it in the
      morning report below. Three open questions settled the same
      evening: 115 - one contested item carries a file's load failure;
      144 - regenerate-history is retired; 114 - if the toolbar spike
      fails, prompts are prefixed with the environment label.
      CI (Keith, later the same evening): NOT checked after each sprint -
      once, at the very end of all the sprints. A 10-minute self wake-up
      (send_later) is re-armed before every turn ends, so the night does
      not stall between turns.
      MORNING REPORT: written here as the night goes - per sprint what was
      built, the commit, CI's result, and every PROVISIONAL choice.
      - SPRINT 1 DONE (commits 45ebb77 + this one): REQ-PIPE-086 criteria 2
        and 13. qa_tools/common/arrival_lifecycle.py; both batches and both
        hand-filed paths call it. Proof: full bootstraps before/after into
        two empty databases, ZERO differences across 7,210 check results,
        82 decisions, 150 filings, 151 supply tables. PROVISIONAL: staging
        stays outside the function (moving it in would change the batch);
        the hand-filed BDM path now checks a contested file as the batch
        does instead of refusing it. Post-build-review #75's test added -
        it passes since #84's fix.
      - SPRINT 2 DONE: REQ-PIPE-130 criterion 8 and criterion 9 for every
        reader but _manifest. `qa.slot_holds(dataset, as_at)` (schema v15)
        is the one definition of what a slot holds; promoted_into,
        latest_for_slot, promoted_supply, slot_state, the drift reference
        and the dashboard's slot timeline all read it. Fixes #85 (drift
        reference) and closes #75. Parity test: 40 random decision
        sequences, every instant, against the Python rule it replaced.
        ALSO FIXED: #88 - two different cross-table checks sharing a name
        were merged into one dashboard card (an older defect my gap-1 fix
        surfaced as a duplicate key). PROVISIONAL: the view is a SQL
        function (needed for the as-at parameter). NOTED for Keith: #89 -
        a withheld supply's slot now reads "awaiting a decision" instead
        of "returned".
      - SPRINT 1 CRITIC (delivery-critic): criterion 2 MET; criterion 13
        met in code, its one-off proof not re-runnable (the "before"
        database was dropped after comparing - noted, not hidden). No
        defects. Minor findings FIXED: stale comments naming run_manifest's
        hooks; the lifecycle docstring overstated a drift that was latent
        (every kept BDM route passes one file); a stronger structural test
        (no batch or hand-filed path calls a step directly); CP's `among`
        pass-through now tested. LEFT: parallel_orchestrate.run_manifest
        and its hooks are dead in production (only their own tests use
        them) - deleting them is a tidy-up for later. The critic also saw
        3 intermittent failures in one of three runs of a CLI subset,
        unattributed; the full suite since then ran clean (3,169 passed).
      - SPRINT 3a DONE: REQ-PIPE-134 BUILT - a dataset's periods never
        overlap, checked in the schedule gate from configuration alone
        (qa_tools/common/period_overlap.py). Today's configuration passes
        all seven datasets; ~1.6s. PROVISIONAL: the cadence-rule horizon is
        the end of next year (the runway warning has none to share). No
        plans prose removed: its source thread still feeds unbuilt batch
        requirements and goes whole when the batch is built.
      - SPRINT 2 CRITIC, AND THE FIX (same night): the critic found
        REQ-PIPE-130 criterion 9 NOT met as first committed and reproduced
        four wrong answers - three readers still walked the log, and three
        that called the view re-read the action, so a re-file OUT left an
        emptied period reading as promoted (queue), as a real supply
        (substitution) and as the drift reference. FIXED with the critic's
        option (b): the view now returns HOW a slot is held (held_as), every
        reader asks that, latest_for_slot is gone, and the view reads an
        include-list of slot-changing decisions. A NULL-comparison bug in my
        own SQL (a reject never skipped) was caught by the parity test.
        Regression tests for each reproduced defect in
        tests/test_slot_holds.py. Schema v17 (three bumps tonight: 15, 16,
        17 - each additive, applied on connect; nothing needed a rebuild).
        Critic minors NOTED, not fixed: the publisher role's ability to run
        qa.slot_holds is untested, and the view is asked per slot in two
        readers where one read would do (fine at today's volumes).
      - SPRINT 3b: REQ-PIPE-131 - a slot closes when the next CALENDAR
        period's claim window opens, and a supply is filed only to the
        slot open at its receipt instant (fill / resupply / held).
        RETIRED (REQ-DOCS-143 records): REQ-PIPE-063, REQ-PIPE-077,
        REQ-PIPE-065 c1-2. AMENDED: 062 c2-4, 064 c1 as signed, and
        PROVISIONAL - REQ-PIPE-052 c5 ("SHALL NOT close it"), which
        contradicted 131 but was not in its amendment list. Scenario
        register (TS-1, 2, 5, 6a-c, 7, 10, 33a/b) rewritten, each with a
        test. Thread E marked SUPERSEDED (candidate for deletion whole).
        ALSO FIXED: post-build-review #90 - the validator demanded a
        RETIRED requirement's code still exist. GAPS until later sprints:
        the queue has no closed-unfilled-slot item until REQ-PIPE-132
        (sprint 7). **NEEDS KEITH: the real `supply` database still holds
        PRE-131 filings** - filings are write-once and `bootstrap --force`
        does not re-derive them (REQ-PIPE-062 c10), and dropping the
        database was refused by this session's permission classifier. It
        needs a drop-and-rebuild by you (or permission to do it). The
        evidence below is from a fresh scratch database, `supply131`.
        EVIDENCE (scratch `supply131`, from empty): 150 filings - 137
        open-slot-unfilled, 4 resupply, 9 held (all cp-case-workers,
        off-cycle). 14 supplies moved against the pre-131 corpus, incl.
        Case Workers' Aug-2024 file, which the old rule had filed to
        2023-Q1 - over a year backward. The first real holds exposed two
        latent defects, both FIXED with failing tests first
        (post-build-review #91 duplicate held+unrunnable records, #92 a
        raw ISO instant in a hold's reason). Scratch databases `supply131`
        and `supply131b` are left behind for you to drop.
      - SPRINT 3b CRITIC: core rule CORRECT - the critic re-derived all 150
        real filings with the new rule at their receipt instants, 0
        mismatches. FIXED (post-build-review #94): a latent slot cache in
        file_arrivals, a bisection test that could not tell a linear scan,
        an authored-to-daily calendar edge, and stale rule wording in the
        scenario register, plans, CLAUDE.md and three requirements
        (REQ-PIPE-151 c3's amendment is PROVISIONAL). **NEEDS KEITH (#93):
        an authored calendar's last period never closes** - a 2030 file is
        filed to 2027-Q4. Keep, or hold such arrivals? Also: TS-4a, named by
        131 c15, does not exist.
      - SPRINT 3b CLOSED (4fb77a2, bd2f9d0, 0a9ac43): evidence from a
        bootstrap on the final code (`supply131b`): same 137/4/9, no check
        with two results, no raw instant in a hold, 277 of 278
        deployed-database tests green; the arrival golden moved for exactly
        the 9 held Case Workers arrivals and was re-captured. A SLIP, said
        plainly: bd2f9d0 went out with that module's distribution backstop
        still red - its commit was gated on the gate's exit code, not the
        test run's. Fixed in 0a9ac43; commits are gated on both from here.
      - SPRINT 4 DONE: REQ-PIPE-144 BUILT (+ REQ-PIPE-107 c13-14). Schema v18:
        a filing links to its delivery and keeps no receipt; each delivered
        file keeps its own; ONE view gives a supply's receipt, another a
        delivery's contested files. ensure_schema refuses an older reshaped
        schema and a newer one (the 99 -> 17 downgrade reproduced first).
        Delivery records are permanent (prune gone); `pipeline run` and
        `bootstrap --force` refuse over existing history; `mothman env
        reset-synthetic` is the one deletion path; regenerate-history and
        delete_history retired; arrival history fixed (#76). PROOF: two
        bootstraps from empty, before/after, compared field by field
        (dashboard data, queue, supply filings/deliveries, 125 ticket
        bodies) - ZERO content differences. 276 deployed-database tests and
        2,906 others green. PROVISIONAL (five, on 144's decisions): the
        `synthetic: true` key; reset also drops supply schemas; what counts
        as "history"; plain bootstrap refused over history too; reset
        refuses non-synthetic AND production. **NEEDS KEITH: 144 c14/c42
        are UNOWNED** - nothing lets a person choose a file of a contested
        pair yet. **AND THE REAL `supply` DATABASE IS NOW REFUSED** (v17):
        `mothman env reset-synthetic` then `mothman pipeline bootstrap`
        rebuilds it - I have not run the reset on it. Scratch databases to
        drop: supply131, supply131b, equiv144_before, equiv144_after,
        gate144, equiv_after.
      - SPRINT 4 CRITIC (post-build-review #95): the storage change held for
        every filing, hold and delivery record. FIXED: reset-synthetic's
        schema matching (it dropped any schema sharing a prefix, and CASCADE
        reached views elsewhere - now exact names, the modules' own listers,
        and a refusal if anything outside depends on it); a publish hint
        pointing at a command that now refuses; a raw traceback on an old
        schema; the publisher grant lost on reset (now said); three missing
        tests. Requirement wording for the retired command updated (038 c5
        PROVISIONAL). FOR KEITH: criterion 16's classification still has two
        definitions of the contested-pair rule (they agree today).
      - SPRINT 5 DONE: REQ-PIPE-103 criteria 9-20 and REQ-PIPE-147 BUILT.
        A kept hand-filed supply asks when it was ORIGINALLY received (S3
        offers each object's LastModified as one set to confirm), records
        the answer beside each file's receipt - marked as a person's,
        never used - and every delivery records automated, or person + route
        + who (schema 19, additive). Shown in `supply deliveries`, the
        closing message and the dashboard's arrival detail. Refusals: a time
        after our receipt, `storage` off S3, no answer from a script (the
        flag named), no identity. PROVISIONAL (on the requirements): the
        accepted spellings of "not known"; where the prompt appears in flag
        mode; one-answer-for-all when the S3 set is declined; people.yaml
        name shown where one exists, else the identity.
      - SPRINT 5 CRITIC (post-build-review #96): core sound. FIXED: prompts
        drawn under the live progress bar (unreadable, typed time not
        echoed); a bare date recorded as midnight; receipts disagreeing
        about who filed accepted; the receipt instant taken before the
        person answered; `--keep` named instead of `--commit`; #52 not
        deleted. FOR KEITH (#96): a GitHub Actions identity hand-filing is
        recorded as a PERSON (rec: refuse); the stated time has no instant
        column (rec: amend the NFR); schema 19 was an additive migration,
        not "regenerate, never migrate".
      - SPRINT 6 DONE: REQ-PIPE-115, REQ-QAC-108's amendment, REQ-DASH-148
        and REQ-PIPE-153 BUILT (148 and 153 with criteria waiting on the
        unbuilt REQ-DASH-133/REQ-PIPE-132/140/151; 108 c17's "accepted as
        not supplied" half waits on 132). A held, contested or unloadable
        supply now runs NO tool and its dataset reads RED, once, with the
        reason, rolled up, judged as at the date on show from the supply's
        receipt; siblings say held/contested/could-not-be-loaded ahead of
        slot reasons; each run reconciles what its tools left out against
        its not-evaluated records; a failed load can be rejected from the
        queue (and promotion is refused); its reason is in our own words.
        Proved on a fresh bootstrap (supply6): 0 tool verdicts on the nine
        held supplies (18 each before).
        **HIGH-VALUE, PLEASE READ FIRST - THE GAP CASCADE (REQ-QAC-108).**
        Built as signed, and it changes the demo corpus drastically: once
        one owed period has no accepted supply, the next supply's drift and
        volume checks are red "compared across a gap" (c8), red is not
        auto-promoted (c15), so the period after has a gap too - every later
        supply of that dataset waits for a person. Nobody acts in a
        bootstrap, so it promoted 9 supplies where it promoted 67 before,
        and 172 of 193 Evidently results are gap reds (the measurement kept
        beside each). Birth Registrations stops at its first red day. Two
        e2e tests that needed ambers now read gap reds at their measured
        verdict. Options: (a) keep - it is what a person would see in real
        life, and the corpus needs a simulated person; (b) let a gap red
        NOT count against promotion (drop c15's half), so the red is
        information only; (c) count a gap only once its slot has CLOSED
        (REQ-PIPE-131's sense) rather than when merely overdue - softens a
        daily feed, not a quarterly one. Recommendation: (b) - a red that
        explains a comparison, without blocking, keeps the warning and
        stops one missed period freezing a dataset; but it reverses a
        signed criterion, so it is yours.
        ALSO FOR KEITH: Case Workers reads red from May 2023 on - its nine
        May/November supplies are held (it only takes Feb/Aug) and a hold
        is red until resolved (115 c10); PROVISIONAL choices on 115 (held
        outranks an ended schedule; a sibling says held only when it cannot
        read the table; unrunnable keeps one record per check while c2 says
        per table - #91's invariant says per check); the reconciliation
        caught a REAL defect on its first bootstrap (#97, two checks
        silently missing when a contested table fell through).
      - SPRINT 6 CRITICS (post-build-review #98 UX, #99 delivery). The
        delivery critic found a CRITICAL false green, now FIXED: a hold on
        one supply withheld the table from every later supply of that
        dataset, so with 115's guard eight on-time Case Workers supplies
        got NO QA and showed green. A hold now applies to its own arrival
        only (re-bootstrapped, supply7). Also fixed: check panel showed the
        last run's numbers as "current" for a blocked dataset; the queue's
        lede said nothing in it changes a status; nine holds named as one;
        "Latest arrival" naming the oldest hold. QUESTIONS FOR KEITH:
        (1) should an open hold from 2023 blank out a later period's real,
        checked results (115 c10-11 as signed say yes)? rec: no - keep the
        dataset red with the reason, show the period's own verdicts;
        (2) should a gap-rule red look different from a measured red? rec:
        yes, same red, labelled at the check group; (3) 115 c2 - one
        not-evaluated record per CHECK (as built, matching #91's invariant)
        or per (check, table) as signed? rec: per check, amend c2; (4) 115
        c17's reconciliation skips runs with no period (trials) - extend
        unrunnable to them, or accept? rec: accept; (5) the sprint-5 critic's
        three (#96): refuse a GitHub-Actions identity hand-filing (rec: yes),
        amend the stated-time instant NFR (rec: yes), note schema 19 was
        additive.
      - SPRINT 7: REQ-PIPE-132 and REQ-DASH-133 BUILT; REQ-PIPE-081's page
        switch NOT BUILT - held for you, see below. 132: a slot that closed
        unfilled reads closed, and a person can accept it as not supplied
        (`mothman supply decide --operation mark-not-supplied`, the TUI's
        ninth filing decision, schema 20 additive); the queue lists
        consecutive closed gaps of a dataset as ONE item; a mark changes no
        data and is superseded by a later re-file or substitution. 133: an
        unmarked gap is RED in words ("No supply - 2 periods with no
        supply, 2025-Q2 to 2025-Q3"), rolls up, and is counted on the agency
        card in one line broken out by kind; an accepted gap is quiet and
        names its reason; both sit in supply history; all judged as at the
        date on show from instants the build embeds. PROVISIONAL: a dataset
        whose latest run is fine keeps its row and carries the gap beneath
        its pill (it does not get the blocked-style reason row); a gap
        outranks an ended schedule. Found and fixed while gating it
        (post-build-review #100-#102): a mark crashed the outstanding queue
        (it carries no supply); a period whose only supply was rejected
        never read as unfilled; a new test promoted into the shared CP
        fixture's period. The sprint-6 hold fix is confirmed on a fresh
        bootstrap (supply7, 21 minutes): every filed Case Workers supply has
        its 18 verdicts, every held one none; 10 promotions.
        **NEEDS KEITH - 081's PAGE SWITCH (criteria 1, 2, 5-8, 11).** Built
        as signed, the as-of view answers ONLY with what was PROMOTED. But
        a red supply is never auto-promoted, so the newest supply of a
        dataset - the one QA exists to judge - would vanish from the
        dataset's verdict while it waits for a person, and the page would
        show the older green one: a false green, the thing this project
        guards hardest against. With the gap cascade above, 9 of ~150
        supplies are promoted, so most dates would also read "nothing in
        place". Options: (a) build as signed and add a red "waiting for a
        decision" item per awaiting supply (needs a new outstanding kind
        and its own requirement); (b) the verdict shows the newest supply
        that is in place OR awaiting a decision, labelled which, and only
        withdrawn ones (rejected, demoted, re-filed out) leave the view -
        satisfies c2 and c6, bends c1 and c8; (c) wait for your answer on
        the gap cascade first. Recommendation: (c) then (b). Left unbuilt
        rather than taken on my recommendation because either answer
        changes what every dataset page shows.
      - SPRINT 7 CLOSED (0f96148) AND ITS CRITICS (post-build-review #104
        UX, #105 delivery). The delivery critic found a HIGH FALSE GREEN, now
        FIXED: a closed period filled and then emptied again (substituted then
        de-substituted, promoted then demoted) read as filled on the page for
        ever - the build had recorded only the first fill. It now embeds every
        change to what the slot holds, from qa.slot_holds. Also fixed: a
        resupply waiting in a closed period was listed as "no supply" and could
        be marked not supplied; the page's to-do queue was judged as at the
        build (past dates listed periods not yet closed) and said those items
        change no status; a daily feed's row hid the late-but-open day behind
        an old gap; red notices were drawn in the all-clear grey; the banner's
        command lacked --reason; marking a substituted period named the wrong
        undo. FOR KEITH (#104): which route the no-supply banner should name
        (mark-not-supplied alone, all three, the wizard, or "chase the
        supplier" first), and whether a daily feed's late-but-open day should
        be named on the row beside an old gap.
      - SPRINT 8 (in progress): REQ-PIPE-122 BUILT - one amber setting, three
        values (hold / promote-and-acknowledge / promote), at asset,
        collection or dataset level, effective-dated and frozen in the past
        (schema gate refuses altering or removing a past version, or adding
        one dated before today unless the asset is synthetic). Hold records a
        withheld note and the supply reads "amber, waiting for a person";
        promote-and-acknowledge promotes and asks for ACKNOWLEDGE - the tenth
        filing decision, person and reason, both routes - which lapses if the
        supply leaves its period. Every amber promotion records the setting,
        level and version (schema 21, additive). REQ-QAC-017 RETIRED: the
        per-run /accept, acceptance_sync.py and `mothman github
        sync-acceptances` are gone; the dashboard shows "awaiting
        acknowledgement" / "Acknowledged by" instead. PROVISIONAL: the asset
        states promote (unchanged behaviour); a second acknowledgement is
        refused rather than "already so" (criterion 14 over 082 c26).
      - REQ-PIPE-122 PUSHED (1798c63) AND ITS CRITICS (#106 delivery, #107
        CLI UX). Fixed: an amber supply under hold read as the red supply's
        "awaiting-decision" where an earlier decision had emptied its slot;
        an asset level with only future versions, and two versions sharing a
        date, now refused by the gate; the old per-dataset ticket still
        invited `/accept`. FOR KEITH: (1) one YAML indentation slip in
        data-asset.yaml crashes EVERY mothman command with a traceback,
        before the validator's own message can run - predates 122, but 122
        is the first thing asking people to hand-edit nested levels there;
        (2) the resolved amber setting and its level are visible nowhere in
        the terminal or dashboard - the NFR that answered REQ-PIPE-075's
        "set once and forgotten" objection is not built; (3) criterion 7's
        "not dated before the day it is added" is judged on the day the gate
        RUNS, so a late-night commit pushed after midnight goes red.
      - REQ-PIPE-118 (in progress): a newer file for a table supersedes every
        earlier unaccepted version in its period at FILING, in the filing's
        own transaction - moved to `period_<p>_superseded`, recorded by the
        rule naming the newer supply (schema 22). The overlay needed no
        change (it reads siblings from staging). Fast suite green with it.
        Baseline from supply7: 140 refusals, 131 red verdicts (the gap
        cascade), 9 no-slot, NONE for a contest - so this corpus no longer
        shows the pile-up 118 was written for; the bootstrap measurement is
        mostly a check that nothing got worse. MEASURED (supply8 against
        supply7): 20m58s vs 21m03s, 28 supersessions, identical promotions
        (10) and refusals (140), staged tables 141 -> 113. PROVISIONAL: a
        contested pair supersedes earlier versions too (decision 12, a
        literal reading); the CLI UX critic's mediums on 122 are fixed.
      - REQ-PIPE-118 PUSHED (5063641). REQ-PIPE-120 BUILT: a person can
        supersede a waiting supply (set aside, kept) or un-supersede one
        (back to staging, and the gate may promote it again); un-supersede
        beside a waiting version is refused naming it; promoting a
        superseded supply is refused naming what replaced it and the
        un-supersede command; `mothman supply superseded` lists them, one
        pasteable line each (28 on the supply8 bootstrap). DEFERRED, with
        its owner recorded: criterion 3's QA RE-RUN after an un-supersede
        waits on REQ-PIPE-151's processing pass, as its own decision 7 says.
        The TUI reaches un-supersede from a REJECTED slot (Keith's worked
        example), asking which version.
      - REQ-PIPE-120 PUSHED (99abafd). CI CHECKED AT THE END, as asked:
        "Validate committed configuration" is green on every push tonight.
        "Run test suite" was red on fbf5a57/0f96148/1798c63 - 0f96148's fast
        half was the order-dependent reconciliation test fixed in 1798c63,
        and 1798c63's deployment half died in CI's bootstrap on a REAL,
        INTERMITTENT DDL race between the two collections' parallel
        processes (post-build-review #108), reproduced with threads and
        fixed in ba70fcb. CI GREEN ON e09390f (run 37233111156, the
        first full run since): all four jobs - fast half, JS, deployment
        half (bootstrap 22m36s, no race) and the coverage threshold.
      - REQ-PIPE-118/120 CRITIC (post-build-review #109): a PERSON'S
        SUPERSESSION WAS INVISIBLE as first committed - every one unseen,
        promotable and stranded - and five readers did not know about
        superseded supplies. All fixed with failing tests first, on the
        commit after ba70fcb. ONE QUESTION FOR YOU (F8): demoting a
        promoted supply into a period where a newer version is waiting
        leaves two waiting versions of one table - should that demote
        supersede the demoted supply, or be refused?
      - WHERE THE NIGHT ENDED (Perth ~04:30). BUILT: sprints 1-7 and, of
        sprint 8, REQ-PIPE-122, 118 and 120. NOT STARTED: the rest of sprint
        8 (REQ-PIPE-128 one version per period, 129 plain base names and its
        database guards, 081's census) and sprints 9-14 (140-142 re-file,
        the rest of 130, 123, 121, 126, 127, the 081 rename, REQ-GEN-135-139,
        096/097/GEN-044 injections, 093/107/146/114+150, 151 and the rest of
        086). 128 and 129 were left rather than started: each is large
        (event-trigger guards, warning panels, a GitHub second-comment
        confirmation), and half of one is worse than none.
        HELD FOR YOU, in order of what they block: (1) the GAP CASCADE
        (REQ-QAC-108) - 10 promotions in a whole bootstrap; (2) 081's PAGE
        SWITCH (a false green as signed); (3) 122's invisible setting and
        the YAML-slip crash (#106, #107); (4) the open questions under
        sprints 6 and 7 above; (5) #109's F8 (demote beside a newer
        waiting version).
      - KEITH'S ANSWERS, 2026-10-05 morning (working through the five held
        items so the build can continue; each to be carried into its
        requirement as an amendment before it is built):
        (1) GAP CASCADE: WARN, DON'T BLOCK. A gap red keeps its red label
            and its reason on the check, but REQ-QAC-108 c15 is dropped -
            the promotion rule judges the supply on its MEASURED verdict,
            so a real drift still blocks and one undecided supply no
            longer freezes every later one. Chosen after the full account
            (the waiting supply counts as a gap; a person promoting it
            later still leaves every later supply's recorded red in place
            until REQ-PIPE-151 re-judges). Rejected: block-until-resolved
            (waits on 151), only-an-empty-gap, keep-as-signed.
        (2) 081 PAGE SWITCH: THE NEWEST SUPPLY IN PLACE OR AWAITING A
            DECISION, labelled which; only withdrawn supplies (rejected,
            demoted, re-filed out) leave the view. Bends c1 and c8.
        (5) F8: REFUSE THE DEMOTE where a newer version of the table is
            waiting in the period, naming it and saying to reject or
            supersede it first. Rejected: demote-then-supersede (my
            recommendation), and allowing two to wait.
        (3) REQ-PIPE-122: (a) a malformed data-asset.yaml stops EVERY
            command with one line - file, line, what is wrong - and a
            non-zero exit, never a traceback (a defect fix, failing test
            first); (b) BUILD THE VISIBILITY NFR NOW, in both places: one
            line on each dataset page ("Amber supplies: promote and
            acknowledge (set for Child Protection, since 5 Oct 2026)"),
            the same in `mothman supply slots`, and a new `mothman supply
            amber-setting` listing every dataset; (c) criterion 7's "the
            day it is added" is the date, on the asset clock, of the COMMIT
            that introduced the version, not the day the gate runs.
        (4a) REQ-PIPE-115: an open hold does NOT blank out later periods -
            the dataset stays red with the hold's reason, each period shows
            its own checked results (amend c10-11); a check reading two
            unreadable tables gets ONE not-evaluated record naming both
            (amend c2); TRIAL RUNS GET THE c17 RECONCILIATION TOO (Keith
            chose this over my "accept"). A gap red (now warn-only) is the
            same red, labelled at the check group with its measured verdict.
        (4b) SPRINT 5 / #93 / MIGRATIONS: the stated original-receipt
            time GETS AN INSTANT COLUMN beside its text, as the NFR asked
            (Keith chose this over my "amend the NFR"); a file arriving
            after an authored calendar runs out is HELD for a person (the
            last period closes when its claim window would have ended);
            ALWAYS WIPE AND REBUILD on a schema change (Keith chose this
            over my "allow additive in place") - so ensure_schema refuses
            ANY older version with the reset-then-bootstrap message, and
            the additive-migration DDL path goes; a service identity
            hand-filing is DROPPED as moot - Keith: "why would it?", and
            nothing does (only the critic's faked GITHUB_ACTIONS test).
        (4c) SPRINT 7 / 144 / DATABASES: the no-supply banner says CHASE
            THE SUPPLIER FIRST, then names the wizard (`mothman supply
            decide`), which offers all three decisions; a daily feed's row
            names TODAY'S LATE-BUT-OPEN FILE beside an old gap; the
            contested-pair choice (144 c14/c42) goes to SPRINT 9's re-file
            requirements (REQ-PIPE-140-142) as an amendment for sign-off, a
            new filing decision on both routes; PERMISSION GIVEN to reset
            and rebuild the real `supply` database and to drop the seven
            scratch databases (supply131, supply131b, equiv144_before,
            equiv144_after, equiv_after, supply6, supply7). A batch drop
            was refused by this session's permission classifier; Keith then
            asked for them one at a time, and all seven are dropped. Also
            left over and NOT in the yes: boot_par, boot_seq, ov_overlap,
            ov_sequential, supply115 - and now supply8 and gate144, both on
            a refused schema since schema 24 (gate24 replaces gate144).
      - BUILT, 2026-10-05 MORNING, from those answers (amendments written
        into the requirements first; REQ-QAC-108 c15 and REQ-PIPE-081 c1/c2/c8
        in the wording Keith approved, the rest transcribed): a gap red no
        longer blocks promotion (promotion._gating_status reads the
        measurement); a demote beside a newer waiting version is refused;
        an old hold no longer blanks later periods (only a contested or
        unloadable supply newer than the latest checked run does); one
        not-evaluated record per check NAMING EVERY unreadable table (it
        named the first only - found while building); trial runs are
        reconciled; any older schema is refused (schema 24 - the stated
        original arrival's instant column); a malformed data-asset.yaml is
        one line, exit 2; criterion 7 judged by the commit's date, looked up
        only when a new version is back-dated (the gate keeps its single
        `git show`); the amber setting shown on each dataset page, in
        `supply slots` and in a new `supply amber-setting`; an authored
        calendar's last slot closes; the banner says chase first and names
        the filing wizard; a late-but-open slot is named on the row; and
        081's PAGE SWITCH - the newest supply promoted or awaiting on the
        date on show, labelled, a withdrawn one leaving the view. The real
        `supply` database was reset and rebootstrapped on the final code.
        SIGHTING, logged as #17: one trial gave 19 failures once, then 177
        passes on four runs - not reproduced.
      STILL TO ASK: CLI Q5-Q8 (exit codes; check table for a big kept
      delivery; how "fix and reprocess" reaches a check; an S3 prefix's
      default arrival time), architect C Q1-Q7 (Lambda/backstop receipt
      order; what continues after a failed arrival; which commands take
      the pass lock; `pipeline run` on a populated database; gating a
      supply with no slot, incl. 144 c13 vs 105 c6; extracting the
      per-arrival function BEFORE the batch; where an S3-only delivery's
      object location lives), architect A Q1-Q8 (a test environment for
      test databases; the ticket repository; 128's one prompt vs 093's
      typed id; regenerate-history in production; moving 107's downgrade
      fix into 144 and 093/107 before 151/152; the dev container; keeping
      the environment visible in the TUI; an S3 prefix's default), and
      architect B Q1-Q8 (file-check history on reprocess; which instant
      opens a failed-load item or hold - receipt vs wall clock; failed-load
      REASONS CAN LEAK ROW VALUES to the public page; where 108's
      no-earlier-supply record goes; synthetic fixtures; 070 c5/c7
      contradictions; contested pair with one refused file; a gate
      refusal reason for a failed load). Defects found: #85 (drift
      reference, a third copy of #84), plus two to log - `_redact` misses
      keyword-form DSNs; test_devcontainer checks only the first CI
      postgres service.
      - SPRINT 9 PUSHED (11eb18e): REQ-PIPE-140 (a decision runs a supply's
        QA again, as a run of its own), REQ-PIPE-141 (re-file) and
        REQ-GHUB-142 (its warning) BUILT. Both critics run: the delivery
        critic's six findings fixed before that commit (post-build-review
        #114); the CLI UX critic, driving it for real, found a reject
        landing on a supply's OLD period after a re-file - fixed in sprint
        10 with the rest of its defects (#115). Also fixed: the sprints
        gate read a wrapped **Owns:** line one line deep, and supply-model
        sprint 26 had read `done` since 2026-09-27 on 96/112 criteria.
      - SPRINT 10: REQ-PIPE-130 (every period's _manifest), REQ-PIPE-123
        (the replacement setting, `never` as shipped), REQ-PIPE-121 (the
        knock-on of a table arriving in or leaving a period - one hook in
        the decision log, owed in the decision's transaction, cheap path
        first), REQ-DASH-126 (red promoted) and REQ-DASH-127 (each supply's
        outcome in its history) BUILT; REQ-PIPE-081 BUILT with the "In place
        on" rename. Schema 27 carries every new decision-log column in one
        bump.
        FOR KEITH: REQ-PIPE-081 CRITERION 6 IS NOT BUILT - "where a decision
        has changed what an earlier date now shows, say so and name it".
        The data is there (effective_at and recorded_at on every entry), but
        in a bootstrap replay EVERY decision is recorded after the date it
        took effect, so the plain reading would flag every past date on a
        synthetic asset. What should count as "changed"?
        SPRINT 10 PUSHED (8040a69). #115 D4 retried on the rebuilt database
        and not reproducible - closed as the critic's environment.
        SPRINT 10 CRITIC (#116): a real HIGH - runs were ordered partly by
        the batch's wall clock, so in a replay a re-evaluation never
        outranked its arrival and a false "red promoted" showed - fixed with
        D3-D6. TWO MORE FOR KEITH: (D2) for a promoted supply, should the
        status pill on its history row be its arrival verdict or its newest
        result per check? they disagree on screen; (D8) REQ-PIPE-123
        criterion 3 says a replacement is "one decision" - it is two
        entries (supersede + promote) in one transaction; amend the wording?
      - SPRINT 11: REQ-GEN-135 (scripted person decisions, played back into
        the synthetic history through the one decision path), REQ-DASH-139
        (the scenario map as its own tab), REQ-GEN-138 (register rewritten,
        TS-41..TS-56). THE PLAYBACK EARNED ITS KEEP ON ITS FIRST RUNS: its
        loud refusal caught two scenarios that did not show what they said.
        (a) TS-47 - an earlier day's resend landed on the "empty" day and
        filled it, so the scripted mark-not-supplied was rightly refused.
        Fixed: an injection can name QUIET days no other day's arrival may
        land on. (b) TS-43/44/45 - the 'amber' dirtying preset makes a RED
        supply (it trips checks that fail on one bad value), and a plain
        truncation into the row-count warn band still read red (it splits
        twins; consecutive days compound). PARKED at Keith's call
        (18:20) - the register says what planting them needs.
      - OVERNIGHT 2026-10-05 -> 06, KEITH'S TERMS (21:50): carry on through
        sprints 13 and 14, REQ-TEST-150 moved after REQ-PIPE-086 (it
        depends on it). Forks: recommended option, PROVISIONAL, listed
        here. And in his words: "happy for you to skip or batch the full
        rebuilds that take half an hour" - so one rebuild per sprint at
        most, verdict probes by trial or a one-collection scratch rebuild
        in between, and any commit gated without a fresh rebuild says so
        in its message. ALSO (21:55): "happy for you to upgrade the database
        schema in place during development" - scoped, at his choice, to MY
        dev and scratch databases only: brought forward by hand (the newer
        DDL applied, the version set), no code change; the code still
        refuses an older schema everywhere else, so this morning's
        "regenerate, never migrate" holds for any real or shared database.
        A proper dev command is plans/running-thoughts.md #66.
      - SPRINT 12: REQ-QAC-096 and REQ-DASH-097 built; TS-12 (a ragged
        cp_clients, refused) and TS-56 (cp_carers' columns reordered,
        warned) planted. ONE COST, FOUND AFTER THE REBUILD, TO PUT RIGHT:
        TS-56 replaced 2024-Q3's chain, and 2024-Q3 was the ONLY quarter
        whose late siblings re-evaluated an already-promoted table - so
        the generated history no longer contains a knock-on re-evaluation
        (REQ-PIPE-121) at all. The fix is moving TS-56 to a quarter with
        no resend, in the next batched rebuild (sprint 13's).
      - SPRINT 13: REQ-PIPE-093 (stated environment; criterion 15 waits on
        REQ-PIPE-151), REQ-PIPE-107, REQ-PIPE-146 and REQ-TEST-114 built;
        sprint 26 now reads `blocked` on REQ-PIPE-151. THREE PROVISIONALS
        FOR YOU, each recorded in its requirement's decisions:
        (1) a database's identity is two database-level settings read from
        the catalogue, not a table - so a reset keeps it and a DSN cannot
        fake it (REQ-PIPE-107);
        (2) `mothman env mark --confirm <id>` counts as typing the id, for
        the hook, CI and dev container, which have no terminal (107);
        (3) a one-off command names its environment at its FIRST DATABASE
        CONNECTION rather than at start, so commands that never connect stay
        quiet (REQ-TEST-114).
        THINGS THAT WILL BITE ONCE: every existing database now refuses until
        marked - `mothman env mark` - and CI marks its own as a new step. The
        TS-56 move is in: -9 -> -8, a clean quarter, giving the red chain at
        -9 (the knock-on re-evaluation) back.
        The sprint 12 critic is written up as post-build-review #118: seven
        findings fixed, two for you (D-E's "what is a header row" and #117
        D1's email fallback for someone not in people.yaml).
      - SPRINT 14 (2026-10-06 small hours): REQ-PIPE-151 (`mothman pipeline
        process`), the rest of REQ-PIPE-086 and REQ-TEST-150 built; schema
        30 (a `promotion-refused` decision-log entry for every gate outcome
        that is not a promotion). Run against a hand-upgraded copy of the
        deployment: 63 checked-but-ungated arrivals given their gate in 51s,
        nothing promoted that the batch had not, then "Nothing to process"
        on the second pass. THREE DEFECTS FOUND AND FIXED ON THE WAY, each
        with a failing test: the gate-only path dropped every result (run_key
        vs run_id); a gate re-run over a promoted supply recorded a refusal
        (the first sprint-14 rebuild was KILLED and restarted for it); the
        pass lock named a holder in another database.
        UNMET, FOR YOU: REQ-PIPE-086 criterion 11 (the terminal-vs-batch
        equivalence TEST - not written; holds by construction) and criterion
        10 (guarding run_single waits on REQ-PIPE-152's Lambda move);
        REQ-PIPE-151 criterion 1's storage-only half (REQ-PIPE-152);
        REQ-DASH-148 criterion 12 is now only missing the reload OWING its
        re-check.
        PROVISIONALS: a recorded arrival kept from the picker is REFUSED
        (pass --trial) rather than routed into a re-check - a person asking
        is not a cause the owed-run record accepts; the pass leaves an
        arrival another process holds rather than waiting; it stages every
        unchecked arrival first, as the batch does; it never plays scripted
        decisions; a kept run's inheritances are attributed by time.
        THE SPRINT 13 CRITIC (post-build-review #119): D1 FIXED as a defect
        - `env mark` could relabel a database, production included, with
        flags alone; now --confirm only marks an UNMARKED database and a
        replacement needs a person typing it. QUESTIONS: (a) should `supply
        tidy` and `supply discard-sample` need production's typed id with
        --yes unable to skip it (they now name the environment, nothing
        more)? (b) in production, should the typed id REPLACE hand-filing's
        "keep this?" y/N rather than follow it?
      - THE SPRINT 14 CRITIC (post-build-review #120): nine findings FIXED,
        each with a failing test first. The two that mattered:
        - D1: a terminal keep and a processing pass could process the same
          arrival at once. The critic reproduced it, and both failed. Hand
          filing now takes the arrival's lock and refuses one that is held
          or already finished. PROVISIONAL: it refuses rather than waits.
        - D2: a failure outside the per-arrival step exited 1 ("red") instead
          of 2. A staging failure stopped the whole pass instead of only its
          own collection.
        Also fixed: a kept synthetic run now reports what the lifecycle
        decided; a TUI trial that filing refused now asks for its reference
        instead of naming a flag; a refusal is now logged even if the supply
        was promoted and later demoted; the report names datasets instead of
        "its dataset"; every spelling of the password is now scrubbed; stale
        help texts; a duplicate header.
        QUESTIONS FOR YOU:
        Q1. Tickets that could not be reconciled: should
            `pipeline process` exit 2? Today it prints them and exits on the
            arrivals alone. (a) yes, a failed stage per criterion 20; (b) no,
            the slot state is durable and the next pass retries - amend
            criterion 20.
        Q2. An arrival whose run never completed (a crash) is re-run under its
            own run id, which REPLACES its partial results. That reads against
            REQ-PIPE-086 c8. (a) keep that, as an explicit crash exception;
            (b) re-run it under a new identity and leave the partial run as an
            incomplete one.
        Q3. When another process holds an arrival, do later arrivals of
            the same collection wait in that pass, as they do after a failure
            (receipt order), or go ahead as today?
        Q4. A kept folder holding files no dataset recognises (a renamed
            extract): (a) keep the rest and NAME what was left behind, as the
            batch's "supply on the floor" warning does; (b) refuse the whole
            keep until they are renamed or removed; (c) silent, as today.
        Q5. `backlog.unprocessed` has no caller left, and now reads the
            pass's own definition of processed. Delete it (REQ-PIPE-061 owns
            it), or keep it for the Lambda?
        Q6 (predates this sprint). A TRIAL leaves a completed run and its
            results in the database, which the visible-results view shows,
            while printing "nothing was recorded". `trial.discard` does this
            on purpose, but REQ-PIPE-103 c6 says nothing should outlive a
            trial. Which is right?
 All the old unsigned
      drafts have now been refreshed except the parked calendar group
      (110-113) and REQ-QAC-145.

17. **[investigate, 2026-10-05]** **[Pipeline & publishing]** **The same
    trial gave different verdicts once.** `mothman cp qa --trial --table
    cp_clients --file "data/deliveries/Data Extract 01 Feb 2023/cp_clients.csv"`
    against `supply8` reported **153 pass / 5 warn / 19 fail-or-error** (184
    checks) the first time, and **177 pass / 0 / 0** on each of four runs
    after it. The only code change between the first and second was the
    trial reconciliation (REQ-PIPE-115 c17), which cannot change a verdict.
    NOT REPRODUCED. One candidate, unconfirmed: the first run was the first
    connection to `supply8` since the schema went from 22 to 23, so it
    migrated the schema in place on that connection. Another: some
    leftover state from an earlier session that the first run consumed.
    The first run's per-check output was not kept, so which 19 failed is
    unknown. Next step if it recurs: keep the full output (COLUMNS=250) and
    compare the failing check ids against a stable run.
