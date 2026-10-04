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

15. **[todo, 2026-10-02]** **[Testing & dev tooling]** **`mothman
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
