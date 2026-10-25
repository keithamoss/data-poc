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
`requirements.yaml`, and the entry's prose comes out when it lands - its feedback card stays (below).

**EVERY ENTRY CARRIES A FEEDBACK CARD** (REQ-DOCS-219). Directly after its opening paragraph, each numbered entry carries a short labelled list: `You told us:` (something a reviewer raised) or `We noticed:` (something we found ourselves), `What we heard:` (our reading, in our own words), `What we built:` once something is (or, for a parked, won't-do or not-reproduced card, why not), `Evidence:` (requirement ids, `sprint <n>`, or relative dashboard links) and, where needed, `Card status:`. A new sighting is filed with at least its first line and `What we heard`. When an entry lands, its title line and its card stay, its status goes to `done`, and the rest of its prose goes as for any other plans entry. A card never names, describes or quotes the reviewer. The date in an entry's `[status, date]` tag is the date it was first raised, and does not change when its status does. `mothman dashboard validate-feedback` checks every card; the dashboard's Feedback tab shows them.

**SECOND SWEEP, 2026-10-12** (the same method). Tags tidied the same
night at Keith's go-ahead: #12 to parked, #16 to blocked (built, waiting
on its decisions moving into requirements), #5 (done, REQ-DASH-071)
deleted. DELETED as fixed:
#11, supply-history columns out of
line (5c5a616's shared colgroup, asserted in tests-js/supply-history);
#14, "Client reference" three times with nothing to tell them apart
(REQ-QAC-037: a cross-table row names its table, column and tool); and
#8, closing a check panel landing on the agency view - FIXED the same
day: Close stepped back through history even when the entry beneath was
not the app's (a check reached by its URL had the previous page there,
and a fresh tab had nothing), so it now steps to the parent view in place
unless the app itself pushed that entry (tests/test_dashboard_e2e.py
TestClosingAPanelReachedByItsUrl, three failing first). #16's
resupply pile-up is built too (REQ-PIPE-118 onward); its design log was
checked into the requirements that own it and deleted 2026-10-25, its
card kept.
#3 was deleted in this sweep as fixed by REQ-PIPE-167 and REOPENED the
same evening by Keith - it is a different concept, not yet scoped.

**PROPOSED SPRINTS FOR WHAT IS LEFT, 2026-10-12** - ORDER 1-2-3-4
CONFIRMED by Keith 2026-10-13. Still none of sprints 1, 3 or 4 has a requirement yet, so
each goes through delivery-scoper and his sign-off before anything is
built. Ordered by value to a busy data-team leader at the dashboard.

- **Sprint 1 - "where do I put my effort?" (#1, #2; M).** BUILT 2026-10-14
  as REQ-DASH-224 to REQ-DASH-228: columns not green on the dataset list,
  datasets not green on agency cards and collection headings, red and
  amber trends on the dataset and column pages, and each check's chart
  naming its measure. Entries #1 and #2 are kept as cards only; their
  decisions are on those requirements. The turned-off part is
  REQ-DASH-180 criterion 29, built with that requirement.
- **Sprint 2 - "don't mislead me" (S).** BUILT 2026-10-13 as REQ-DASH-197
  (the "not the latest file" panel as at the date on show) and REQ-DASH-198
  (the substituted/inherited qualifier, which also named a period that had
  not happened on today's cp-case-workers view). Entry #18 deleted with the
  build; its decisions are on REQ-DASH-197. #17 closed earlier the same day.
  Left open by it: post-build-review #164 (a resupply awaiting a decision is
  told it was superseded) and #19 below.
- **Sprint 3 - "what actually changed?" (#9, #10; L).** One distribution
  component in the drill-down: this supply against the last promoted one
  (REQ-QAC-108's reference), the invalid values for any check that has
  them, and an honest "no breakdown for this check" where it does not.
  The breakdown is DERIVED FROM EACH CHECK'S DECLARED RULE, retiring the
  hand-kept lists in both dataset_stats.py (Keith, 2026-10-13). Still open:
  a top-N cap for wide columns; sensitive columns.
- **Sprint 4 - new check kinds (#4, #6; M-L).** Cardinality drift (gains
  and losses separately, against the last promoted supply) and declared
  known-bad dates with percentage bands (the Soda user-defined-metric
  route already proven on 3.5.6). Questions: thresholds, which columns,
  baseline and resupply rules, band values. Last because it adds detection
  rather than making today's results readable, and its values need
  sprints 1 and 3's displays.
- **To scope first:** #3 (data arriving now that belongs in the NEXT period's schema), reopened by Keith 2026-10-12 - a concept of its own, not REQ-PIPE-167.
- **To scope (Keith, 2026-10-25):** #12, unparked, with a synthetic geocoding dataset (one row per source record per census year); #19 as decided in its entry.
- **Done 2026-10-25:** #16's ~1,140-line design log is gone, every
  decision in it now on the requirement that owns it (REQ-PIPE-118 to
  REQ-PIPE-134 and those they name); its card stays.

**STALENESS SWEEP, 2026-10-06** (a read-only agent checked every open
entry against the code; the claims below were verified before being
written here). DELETED as fixed by later work: "Arrived at" was the
earliest extract (REQ-PIPE-080, 3adb8d8), seventeen separate "missing
supply" items (REQ-DASH-133's grouped gaps, 0f96148), `bootstrap --force`
not reproducing (REQ-PIPE-144), and the old #13 - Soda Core cannot run a
change-over-time check - whose finding now lives in REQ-QAC-108's
decisions. KEITH'S ANSWERS the same morning, to be scoped into
requirements:
- #1 trend sparklines: labelled on the dataset and column pages; the
  overview cards and dataset list show "N of M checks not green" instead.
- #2 sizing a problem: the dataset list counts failing COLUMNS, in its own
  column where Trend sits today.
- #3 following-period datasets: scoped with the calendar group
  (REQ-PIPE-110 to 113), not on its own. CORRECTED 2026-10-12 (Keith): that
  scoping produced REQ-PIPE-167's `days_before`, which is NOT #3 - #3 is
  data arriving now that belongs in the next period's schema, still open.
- #4 cardinality drift: a percentage change in distinct count, gains and
  losses counted separately, against the last promoted supply.
- #6 known date outliers: declared in the contract, on any date column,
  tolerated up to a stated percentage.
- #7 a misconfigured Soda check passing silently: A DEFECT, FIXED the same
  morning and the entry deleted - every declared check Soda does not report
  is red, "could not be evaluated", with why; `mothman dashboard
  validate-soda` refuses the unparseable and Soda-Cloud-only kinds in CI
  (REQ-QAC-001/002's decisions).
- #9 and #10: one histogram component, this supply against the last
  promoted one, and a check without a breakdown SAYS so.
- #12 tall-dataset completeness: parked until the 30-dataset asset is
  closer.
Still to settle by driving the page: #8 and #17 - both since closed
(2026-10-12 and 2026-10-13).

3. **[todo, 2026-09-24]** **[Pipeline & publishing]** **A
   collection whose files go into the period AFTER the one they arrive
   in.** Restated by Keith 2026-10-25 (below); the original wording -
   data arriving in January fills Q2, not Q1, a per-dataset property -
   was read too narrowly.

- **You told us:** Most files arrive not yet linked and belong to the next period's release; files already linked belong to the current period.
- **What we heard:** Which period a collection's files go into - this one, or N after - is a property of the collection, with "next period" the usual case.

   **RESTATED BY KEITH, 2026-10-25 - this supersedes the reading below and
   the scoper drafts REQ-*-320 to 324, which are not applicable.** In
   production there are two classes of files, often from one supplier and
   arriving around the same time. NOT-YET-LINKED files - most suppliers,
   roughly 70-80% of files - go into the NEXT period: a file arriving on
   1 February belongs to the next period because the linkage product for
   that period, produced about three months later, is that period's
   release. ALREADY-LINKED files go into the CURRENT period. A COLLECTION
   ALWAYS GOES TO THE SAME PERIOD. The offset is +1 today and could be +2 or
   more in future. Linkage products are a SEPARATE dataset with their own
   files, never replacing the data already loaded, and they WILL have
   cross-table checks with the data in that period. There are no checks
   across periods, and none are in scope. For the synthetic history:
   Department of Health (Emergency Department) goes into the current
   period; every other collection goes into the next - "that's how it
   works in production now". Keith asked how to model it: a configuration
   flag or something else. Open with him (2026-10-25): what "next period"
   means for a daily collection; whether synthetic linkage products come
   now or later; refusing a change of offset until a period is declared
   not owed; and the page's wording.

   **From the road-test participant, not Keith** (Keith, 2026-10-25): the "Keith's own ask" below records who relayed it.

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

   **REOPENED 2026-10-12 (Keith).** A sweep that day deleted this entry as
   fixed by REQ-PIPE-167 (built 2026-10-07: a participation's `days_before`
   moves a slot's due instant ahead of its period's date). Keith: "that's
   literally talking about data that needs to be arriving now, but going
   into the next period schema. It's an entirely different concept that we
   need to scope. It shouldn't be closed." So this is NOT done, and it
   needs scoping with him - starting with how it differs from what
   REQ-PIPE-167 built, so the scoping says exactly what that requirement
   does not cover. No Child Protection or Birth Registrations dataset uses
   `days_before` today.


4. **[todo, 2026-09-24]** **[QA checks & contract]** **Cardinality
   drift - watch how many distinct values a column has, not which ones
   they are.** Keith's own ask, 2026-09-24, and his own worked example:
   a suburb field holding ~600 values. New suburbs appearing is normal
   and uninteresting. Fifty appearing at once is a question. What we
   want is a threshold of acceptable change that lights amber or red,
   over the COUNT of distinct values - "we don't really care what the
   values are".

- **You told us:** Watch how many distinct values a column has - a few new suburbs is normal, fifty at once is a question.
- **What we heard:** A drift check on the count of distinct values, with amber and red bands, separate from today's proportion drift.
- **Evidence:** sprint 4

   **From the road-test participant, not Keith** (Keith, 2026-10-25): the "Keith's own ask" below records who relayed it.

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

6. **[todo, 2026-09-24]** **[QA checks & contract]** **Known
   date-of-birth outliers, declared explicitly, with a tiered
   percentage tolerance.** Keith's own ask, 2026-09-24. Some bad dates
   are KNOWN - a legacy placeholder, a specific bad batch - and they
   come as individual dates or as a date RANGE. He wants those named,
   and then a tolerance on how many rows may carry one, in bands:
   roughly 1% acceptable, 2% amber, above 3% red.

- **You told us:** Some bad dates of birth are known - name them, and tolerate them up to a percentage before going amber or red.
- **What we heard:** A declared list of known-bad dates and ranges with tiered percentage bands, beside the check that tolerates no unknown bad date.
- **Evidence:** sprint 4

   **From the road-test participant, not Keith** (Keith, 2026-10-25): the "Keith's own ask" below records who relayed it.

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

9. **[todo, 2026-09-24]** **[Dashboard UI]** **A value-distribution
   histogram in the drill-down, this supply beside the previous one.**
   Keith's own ask, 2026-09-24, for categorical columns where it makes
   sense: show what is in the column now and what was in it last
   supply, side by side, so a reader gets an immediate visual sense of
   how much has shifted.

- **You told us:** Show a column's values this supply beside last supply, so you can see at a glance how much has shifted.
- **What we heard:** A side-by-side distribution in the drill-down - a picture for reassurance, not another check to configure.
- **Evidence:** sprint 3

   **From the road-test participant, not Keith** (Keith, 2026-10-25): the "Keith's own ask" below records who relayed it.

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

- **You told us:** When values are invalid, say which values they were and how many of each.
- **What we heard:** The breakdown already exists for six columns; every check that can have one should, and a check that cannot should say so.
- **Evidence:** sprint 3

   **From the road-test participant, not Keith** (Keith, 2026-10-25): the "Keith's own ask" below records who relayed it.

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

12. **[todo, 2026-09-24]** **[QA checks & contract]** **A completeness
    check for a TALL dataset: every event must have exactly one row per
    expected category.** Keith's own ask, 2026-09-24, with his own
    worked example - a geocoding dataset holding one row per geocoding
    event per ABS census year, so one geocoding event generates six
    rows for six census years. Anything that violates that, we want to
    know about.

- **You told us:** In a tall dataset every event should have exactly one row per expected category - one per census year, say.
- **What we heard:** A check that every key has exactly one row for each member of a declared set, reporting missing, duplicate and unexpected members separately.

    **UNPARKED (Keith, 2026-10-25)**, from the road-test participant: scope it now, WITH a synthetic geocoding dataset to build it against - addresses geocoded, one row per source record per ABS census year. Goes to delivery-scoper.

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

16. **[done, 2026-10-03]** **[Pipeline & publishing]** **A clean
    resupply cannot get through once a quarter has two undecided
    versions of anything.**

- **We noticed:** A clean resupply could not get through once a quarter had two undecided versions of anything.
- **What we heard:** Each resupply added another waiting version, and nothing reading a table with two of them could be checked until a person cleared the stale ones.
- **What we built:** A newer file now supersedes every earlier undecided one for its table and period, so only one version waits at a time.
- **Evidence:** REQ-PIPE-118

19. **[todo, 2026-10-13]** **[Dashboard UI]** **On a past date, the supply
    history lists supplies that arrived after it.** Found by delivery-scoper
    while scoping #18 (post-build-review #110's M4 logged it alongside the
    panel as "not clipped"). The supply-history section deliberately reads
    the raw, unclipped dataset to show the whole refresh period
    (renderDataset's own comment; REQ-PIPE-115 criterion 25 says "whatever
    the period on show"), so on 5 August 2023 it still shows 2026's
    supplies. Keith, 2026-10-13: log it as its own sighting rather than
    settle it as by design inside REQ-DASH-197. A sighting, not a decision -
    whether it should clip, mark later rows, or stay as is is still open.

- **We noticed:** On a past date, the supply history still lists supplies that arrived after it.
- **What we heard:** Whether the history should stop at the date on show, mark later rows, or stay as it is, is still open.
- **Evidence:** [Client Register on 5 Aug 2023](?in-place-on=2023-08-05#/agency/child-protection-family-support/collection/child-protection/dataset/cp-clients)

    **DECIDED (Keith, 2026-10-25)**: keep the whole history and MARK supplies that arrived after the date on show as "arrived after this date", rather than clipping or leaving them. Goes to delivery-scoper as a small requirement.

20. **[done, 2026-10-25]** **[Dashboard UI]** **The "awaiting a correction"
    line's border ignores the theme.**

- **We noticed:** The "awaiting a correction" line's border colour is the same in light and dark themes.
- **What we heard:** Every colour on the page should come from the theme's own tokens.
- **What we built:** The border now uses the theme's amber, and a test fails the page if any colour or font it names is not one the theme defines - six others were found and fixed with it.
- **Evidence:** [Client Register](#/agency/child-protection-family-support/collection/child-protection/dataset/cp-clients)
- **Card status:** fixed

## Landed entries, kept as feedback cards (REQ-DOCS-219)

Card-only entries: what was raised and what came of it. #1 and #2 landed
with road-testing sprint 1; the others were deleted as they landed and are
restored here under new numbers, each saying the number it had.

1. **[done, 2026-09-24]** **[Dashboard UI]** **A trend was drawn in two places, measuring two different things, and neither said which.**

- **You told us:** It wasn't clear what a trend line plotted - row counts, failures, supplies, something else?
- **What we heard:** Every trend should say what it measures in words, and a check's own chart should name its unit.
- **What we built:** The dataset list, dataset page and column panel chart the share of columns or checks red and amber, with titled axes and a key; a check's chart names its measure, such as 'Rows with no value (count)'.
- **Evidence:** REQ-DASH-225; REQ-DASH-227; REQ-DASH-228

2. **[done, 2026-09-24]** **[Dashboard UI]** **The overview said whether there was a problem, never how big it was.**

- **You told us:** You could see that something was wrong, but not how much - how many checks red, how many amber.
- **What we heard:** A count where you triage, so you can see where to put your effort without opening every dataset.
- **What we built:** The dataset list counts columns not green, and agency cards and collection headings count datasets not green, each with red and amber trend lines.
- **Evidence:** REQ-DASH-224; REQ-DASH-225; REQ-DASH-226; [Child Protection's datasets](#/agency/child-protection-family-support)

20. **[done, 2026-09-24]** **[Dashboard UI]** **Times were shown in UTC, not Perth time (was #5).**

- **You told us:** Times on the dashboard were in UTC rather than Perth time.
- **What we heard:** Show the asset's own clock everywhere, with no zone label, since there is only one clock.
- **What we built:** Every date and time on the page now goes through one formatter, on the asset's own clock.
- **Evidence:** REQ-DASH-071

21. **[done, 2026-09-24]** **[Dashboard UI]** **Closing a check panel jumped back two levels (was #8).**

- **You told us:** Closing a check panel landed on the agency view instead of the dataset you were on.
- **What we heard:** Closing should return you to the page you were looking at.
- **What we built:** Close now steps back only over a page the dashboard itself opened, and otherwise closes in place.
- **Evidence:** [Client Register](#/agency/child-protection-family-support/collection/child-protection/dataset/cp-clients)
- **Card status:** fixed

22. **[done, 2026-09-24]** **[Dashboard UI]** **Supply history columns did not line up, and its dates were raw (was #11).**

- **You told us:** In the supply history, columns didn't line up from one cycle to the next, and the dates were raw.
- **What we heard:** One set of column widths for the whole history, and dates written the way the rest of the page writes them.
- **What we built:** The dates use the page's one date format, and every cycle's table shares the same column widths.
- **Evidence:** REQ-DASH-071; [Client Register's supply history](#/agency/child-protection-family-support/collection/child-protection/dataset/cp-clients)

23. **[done, 2026-09-28]** **[Dashboard UI]** **"Arrived at" was the earliest row in the file, not when the supply arrived (was #14).**

- **We noticed:** 'Arrived at' showed the earliest row in the file rather than the moment the supply was received.
- **What we heard:** The two had only agreed by coincidence, and a lateness verdict needs the real time of receipt.
- **What we built:** Arrival times come from the recorded receipt of each supply.
- **Evidence:** REQ-PIPE-080

24. **[done, 2026-09-26]** **[Dashboard UI]** **"Client reference" three times in a row, with nothing to tell them apart (was #14).**

- **You told us:** The cross-table section showed 'Client reference' three times in a row with nothing to tell the rows apart.
- **What we heard:** Each row needs to say which tables, column and tool it is about.
- **What we built:** A cross-table check's row names its tables, its column and its tool.
- **Evidence:** REQ-QAC-037

25. **[done, 2026-09-24]** **[QA checks & contract]** **A misconfigured Soda check passed silently (was #7).**

- **We noticed:** A Soda check with a configuration mistake passed instead of failing.
- **What we heard:** Soda logs a bad check and carries on, so its errors have to be read rather than its results trusted.
- **What we built:** A check Soda could not run shows red as 'could not be evaluated', and every Soda check's configuration is checked in CI.
- **Evidence:** REQ-QAC-001; REQ-QAC-002

26. **[done, 2026-09-24]** **[QA checks & contract]** **Soda Core cannot run a change-over-time check (was #13).**

- **We noticed:** Soda Core has no way to express a check that compares this supply with an earlier one.
- **What we heard:** Any change-over-time check has to be computed by us.
- **What we built:** Drift and volume are computed by us, against the last supply actually promoted.
- **Evidence:** REQ-QAC-108

27. **[done, 2026-10-02]** **[Pipeline & publishing]** **A forced bootstrap no longer reproduced the same content (was #15).**

- **We noticed:** Re-running the bootstrap over a populated database gave different results from a clean run.
- **What we heard:** Recorded decisions outlive a re-run, so running again on top of history stacks a second history on the first.
- **What we built:** The bootstrap refuses to run over recorded QA history; starting again is an explicit reset first.
- **Evidence:** REQ-PIPE-144

28. **[done, 2026-09-28]** **[Dashboard UI]** **Seventeen "missing supply" items for one daily dataset, on one page (was unnumbered).**

- **We noticed:** One daily dataset's page listed seventeen separate 'missing supply' items, one for every day skipped.
- **What we heard:** At thirty datasets, that many items about one fact becomes noise people learn to ignore.
- **What we built:** A period closed with no supply is shown clearly and grouped, rather than as one line per missing day.
- **Evidence:** REQ-DASH-133

29. **[done, 2026-10-05]** **[Pipeline & publishing]** **The same trial gave different verdicts once (was #17).**

- **We noticed:** One trial run on a file gave different verdicts from four runs after it.
- **What we heard:** A trial should give the same answer every time it is run on the same file.
- **What we built:** It never happened again in four more runs, so there was nothing left to trace.
- **Card status:** not-reproduced

30. **[done, 2026-10-07]** **[Dashboard UI]** **A past date showed a warning about files received years later (was #18).**

- **We noticed:** On a past date, a dataset warned about files that arrived years after it.
- **What we heard:** A past date must show what was known then, not today's latest file.
- **What we built:** The 'not the latest file' panel and the stand-in qualifier read as at the date on show.
- **Evidence:** REQ-DASH-197; REQ-DASH-198; [Client Register on 5 Aug 2023](?in-place-on=2023-08-05#/agency/child-protection-family-support/collection/child-protection/dataset/cp-clients)
