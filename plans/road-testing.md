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

3. **[investigate, 2026-09-24]** **[Pipeline & publishing]** **A
   delivery that belongs to the NEXT period rather than the current
   one, decided per dataset.** Keith's own ask, 2026-09-24. Some
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

5. **[todo, 2026-09-24]** **[Dashboard UI]** **The dashboard should
   display Perth time, not UTC.** Keith's own sighting, 2026-09-24.

   **The mechanism for this already exists and is used in exactly one
   place**, which is what makes this a real gap rather than a feature
   request. `contract/data-asset.yaml` carries `timezone:
   Australia/Perth`; `dashboard/embed_dashboard_data.py` embeds it into
   the template's `const ASSET_TIMEZONE` (`REQ-PIPE-048`); and the
   template reads it at exactly one call site -
   `assetTodayDateStr()` - which decides the default as-of date. That
   one use was itself introduced to fix a real, live version of this
   bug: `liveNowDateStr()` used `toISOString()`, so between midnight
   and 08:00 Perth the default as-of date was YESTERDAY, every working
   morning for eight hours, unnoticed because nobody opened the
   dashboard that early.

   **Everywhere else still ignores it.** Three separate shapes, worth
   keeping distinct because they are wrong in different ways:

   - **An hour is hard-coded as UTC and labelled as such.**
     `buildRealDataset()` builds `arrivedAt` by slicing characters
     11-16 out of an ISO timestamp and appending the literal string
     `" UTC (earliest extract, latest run)"`. So the arrival time on
     screen is a UTC clock reading, correctly labelled and eight hours
     from the time anyone in the office experienced.
   - **Dates render in the VIEWER's zone, not the asset's.** `fmtDate()`
     and `fmtDateShort()` call `toLocaleDateString("en-US", ...)` with
     no `timeZone` option at all. For a reader sitting in Perth that
     happens to give the right answer, which is exactly why it has
     survived. It is wrong for anyone else, and it makes a committed
     snapshot's rendering depend on who opens it.
   - **A `Date` built from a date-only string is UTC midnight**, so the
     same `toLocaleDateString` call renders the PREVIOUS day for any
     viewer in a zone behind UTC. Same off-by-one family as the bug
     `ASSET_TIMEZONE` was introduced to fix, in a different function.

   Also unchecked, and probably fine but worth looking at in the same
   pass: the snapshot banner formats its capture time with
   `toLocaleTimeString(..., {timeZoneName:"short"})`, which is the
   viewer's zone but at least says which zone it is - honest rather
   than correct.

   **The likely shape of the fix**, not yet decided: route every date
   and time formatter through `ASSET_TIMEZONE` the way
   `assetTodayDateStr()` already does, rather than adding a second
   mechanism. The real questions are whether the asset's zone is always
   the right one to show (it is the zone the DATA is about, which is
   the argument for it, and this PoC's own target is two assets in
   separate deployments rather than one page serving several zones),
   and whether times should carry a visible zone label once they are no
   longer saying "UTC" - a bare "14:32" that used to read "14:32 UTC"
   loses information unless it says what it now means.

   **VERIFIED 2026-09-24, and it constrains this item and any other
   "change over time" check, row counts included.** Keith asked whether
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
   declared in SodaCL - which is the same conclusion this item was
   heading for anyway, and now applies equally to row-count change.
   Note the history is already there and already committed, so the
   comparison needs no live data access; per `CLAUDE.md`'s hard rule it
   would still be computed at run time by whoever legitimately holds a
   connection, never in the dashboard build.

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
