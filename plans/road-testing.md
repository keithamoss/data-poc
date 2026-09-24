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
