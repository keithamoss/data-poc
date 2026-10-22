# REQ-PIPE-279 - deterministic matching: sign-off brief (v2)

Drafted by delivery-scoper on 2026-10-22 (Perth), from
plans/running-thoughts.md #117. delivery-architect reviewed it the same day
(`review-architect.md`). This version folds in every finding from that review.

This is a PROPOSAL. Nothing is in requirements.yaml and nothing is signed. The
YAML is `requirements-draft.yaml`, which sits beside this file:
- On its own, it gives only the cross-reference errors a draft is expected to
  give.
- Merged into a copy of the register, it validates clean (249 requirements,
  zero errors).

## The idea in one paragraph

Today the dashboard decides where a result recorded under another table's run
belongs by guessing. It reads stamps out of run ids, compares calendar days,
breaks ties by recording time, run index or run-id text, and uses whatever
the check's declarations say today. This requirement records three facts at
run time:
- **which supply each table was read as**, for every table a cross-table check
  read, including its own, and in what state;
- **an evaluation order** (`qa.run.run_seq`) that cannot tie;
- **the run's cause**: its delivery, or the decision or load that caused it.
  The delivery is already on `qa.filing`.

The page, the promotion gate and #95's counting rule all place and order
results from those facts, through one function, and from nothing else.

## Story

As someone reading a dataset's page, I want every check result recorded under
another table's run placed on the supply it actually read, and counted with
that supply's own delivery or as a re-check of it from recorded facts alone,
so that the page, the list's counts and the promotion gate agree on what each
result is about, and no two people building from the same history can get a
different answer.

## What it would do (21 criteria, in prose)

**Recorded at run time**
1. **What each check read.** Every cross-table result gets one row in a new
   `qa.check_read` table for each table it reads. Each row gives that table's
   state and supply:
   - read: the supply it read; a contested table that fell through to the
     promoted supply is flagged as contested;
   - held: always the held supply's id;
   - absent;
   - no-supply: a sample or trial table.

   These rows are written and replaced together with the result.
2. **Staged tables carry their supply.** The run's resolution carries the
   supply of staged tables too, taken from the filing records. Whether a table
   came from staging or from the period becomes its own field. `qa.tables_read`
   gets the supply for staged tables too.
3. **Single-table results.** These are about the run's own supply. The writer
   refuses one recorded under another dataset's run.
4. **No read, no record.** The writer refuses a cross-table result whose read
   can't be recorded. Today that exception is swallowed.
5. **`run_seq`.** It is drawn only in `open_run`, in the same transaction as
   the resolution, and drawn again each time the run is reopened *(K5)*. Other
   writers never set it, and a run can't complete without one.

**What "newer" and "one point" mean**

6. **Newer means a higher `run_seq`**, for the gate and the page alike
   *(K1)*.
7. **Each result belongs to one point:** (dataset, supply read, cause).
   - The cause is the delivery for an arrival run, and the decision or load
     for a re-check, readers-only or knock-on run.
   - If the result came from an arrival in the same delivery that brought the
     supply, it is that supply's own point, whatever the days *(K3)*.
     Otherwise it is a re-check point, one per cause *(K4)*.
8. **Within a point, each check shows its highest-`run_seq` result.** This
   replaces "another table's result replaces the own verdict".
9. **Absent or no-supply results** show only on the page of the table the
   check is declared on *(K2)*.
10. **The held page** shows results that read the held supply, and nothing
    else.

**What the build emits and reads**

11. **What the build writes out:**
    - each own point's supply id;
    - a dense per-collection rank for every point and every history entry;
    - never `run_seq` itself.

    The template sorts on the rank alone. Dates and the as-of clip still use
    the recording time.
12. **Which dataset and what kind of run** come from `qa.run`'s `dataset_id`
    and `scope`, never from the run id.
13. **Which pages a result is shared to** comes from the recorded reads, not
    from today's check declarations.
14. **The full removal list.** Every day, time, run-index or run-id comparison
    in placement and ordering is removed, across the build, the template, the
    gate and `carried`.
15. **A guard test.** One architecture-rule test fails if any of that code
    reads `recorded_at`, run-id text or a day.

**The gate side**

16. **One function for all readers.** The build, the gate, `carried.decide`
    and #95 all use one function to answer "which results are about this
    supply". Its tie-break is `run_seq` *(K1)*.
17. **REQ-PIPE-265 siblings** are read from `qa.filing` and
    `qa.delivery_file`, never parsed out of run ids.

**Schema, determinism, tests**

18. **Schema 45 to 46.** The existing refusal of another version forces a
    reset and bootstrap. There is no migration.
19. **Determinism.**
    - Building twice from the same history gives byte-identical output, even
      with another collection's runs interleaved differently.
    - The before/after bootstrap comparison lists every difference, each with
      the tie or order that changed it *(K6)*.
20. **Thirteen tests, each written first and seen to fail:**
    - the architect's ten: two same-day Clients supplies; a delivery across
      midnight; shared run instants with badly sorting keys; a retried re-check;
      interleaved collections; edited declarations; a contested own table; a
      settled pair; the writer's refusal; the JS rank order;
    - my three: a 15:00 Clients re-check decision; the held Case Workers case
      of 1 May 2025; a carried check in a same-instant zip.

## What the architect's review changed

- **B1, `run_seq`.** It is no longer a column DEFAULT frozen at insert. A run
  is first inserted at staging, and the same run key gets evaluated again on a
  retry or reopen. So the number is drawn in `open_run` with the resolution,
  and drawn again on reopen (criterion 5, K5).
- **B2, the removal list.** Criterion 14 now names every site, plus the guard
  test (criterion 15) and the writer's refusal (criterion 4). Placement no
  longer reads today's declarations (criterion 13).
- **B3, the point key.** The cause key is defined to include an arrival run of
  another delivery (criterion 7). Highest sequence wins within a point
  (criterion 8). Each own point's supply id is emitted (criterion 11).
- **B4, the gate's order.** The old Q3 offered "sequence for the page, effective
  time for the gate" as though it were harmless. In fact the page and the gate
  would then name different results as newest. It is now re-put as K1.
- **S1 to S8**, in order:
  - recorded states with supply ids (criterion 1);
  - an explicit staging-or-period field (criterion 2);
  - a table rather than jsonb;
  - the single-table refusal (criterion 3);
  - differences listed, not zero (criterion 19);
  - a distinct name, `run_seq`, with each surviving order's job written into
    `decisions:`;
  - a dense rank (criterion 11);
  - the schema bump through existing machinery (criterion 18).
- **First draft Q5** (whether the gate side is included) is **dropped as
  settled**. Leaving the gate out would keep `carried.siblings` parsing run ids
  and `runs_about` matching table names, which is the guessing Keith ruled out.
  The gate needs criterion 2's supply on `qa.tables_read` anyway. Recorded in
  `decisions:`.

**A size note.** 21 criteria is large for a "small" requirement. If Keith
prefers, it splits cleanly in two:
- **(i) the record:** criteria 1-5, 18, and tests 4 and 9;
- **(ii) placement, order and the gate:** everything else, depending on (i).

The architect judged it right as one requirement. I haven't split it, but it
is a mechanical change if he wants it split.

## Amendments to signed wording (old -> new)

**REQ-DASH-264 criterion 12** (Keith, #258 Q4):
- OLD: "THE SYSTEM SHALL count a result recorded under another table's run, in
  the dataset list's counts and sparklines, on the dataset's own run only where
  it was recorded the same day; one recorded on a later day is a point of its
  own on that day, every other check carrying its verdict into it from the point
  before."
- NEW: "THE SYSTEM SHALL count a result recorded under another table's run, in
  the dataset list's counts and sparklines, on the own point of the supply it
  read only where the run that recorded it is an arrival of the delivery that
  brought that supply (REQ-PIPE-279); otherwise on a re-check point of that
  supply for its run's cause, dated by when it was recorded, every other check
  carrying its verdict into it from the point before. Within a point, each check
  takes its newest result by evaluation order."

**REQ-DASH-264 criterion 11** (Keith, #258 Q3). Its trigger changes; the rest
stands:
- OLD: "WHERE two results in a check's history were recorded on the same day
  and either came from another table's run - one delivery checked once by each
  table - ..."
- NEW: "WHERE two results in a check's history belong to one point of
  REQ-PIPE-279 - one delivery checked once by each table, or one re-check cause
  - ..." The rest is unchanged. "A same-day resupply of the dataset's own stays
  two runs" now holds because the two are different supplies.

**REQ-DASH-264 criterion 3** (held table):
- OLD: "... with its result where one was recorded at or after the held
  supply's receipt, and as not run ... where none was ..."
- NEW: "... with its result where one read the held supply (REQ-PIPE-279), and
  as not run ... where none did ..."

**REQ-DASH-264 criterion 1**, only if K2 is answered (a):
- OLD: "... the newest result recorded for that dataset on or before the
  in-place-on date, whichever table's run recorded it ..."
- NEW: "... the newest result about a supply of that dataset on or before the
  in-place-on date, whichever table's run recorded it ..."

**Two REQ-DASH-264 decisions are superseded:**
- "A re-check is told apart by its run id's `__r<N>`". The kind of run now
  comes from `qa.run.scope` (criterion 12).
- "A result from another table's run ... replacing that run's verdict for the
  check". Highest sequence now wins within a point (criterion 8).

**REQ-PIPE-265 criterion 1:**
- OLD: "THE SYSTEM SHALL treat as SIBLINGS the arrival runs of one collection
  whose run ids share one receipt instant (the run id after its table name,
  REQ-PIPE-105 criterion 1) - files filed together before the first of them is
  checked (REQ-PIPE-105 criterion 5) - reading that from the record, and SHALL
  treat no other pair of runs as siblings. ..."
- NEW: "THE SYSTEM SHALL treat as SIBLINGS the arrival runs of one collection
  whose supplies were filed from one delivery with one receipt instant (qa.filing,
  qa.delivery_file) - files filed together before the first of them is checked
  (REQ-PIPE-105 criterion 5) - reading that from the record and never from run
  ids, and SHALL treat no other pair of runs as siblings. ..." The rest is
  unchanged. #95 v4's REQ-PIPE-266 criterion 1 inherits this.

**#95 v4 knock-ons, to apply when #95 v5 is drafted:**
- REQ-PIPE-267 criterion 1 and REQ-PIPE-269 criteria 1-2 cite REQ-PIPE-279
  criterion 1, not `qa.tables_read`.
- REQ-PIPE-269 criterion 7's single selection function is criterion 16's
  function.

## Non-functional requirements

All of these are in the YAML.

- **Determinism.** Every query orders by a recorded key.
- **The build emits a rank, never `run_seq`.** Raw numbers interleave
  differently across collections that bootstrap in parallel; a per-collection
  rank does not.
- **Order within a collection.** It needs re-checks and knock-ons to run one
  at a time, as they do today. If #95's concurrent applications land, `run_seq`
  is drawn under its per-(collection, period) lock.
- **A build reads recorded QA results only.**
- **Scale.** Work grows in step with the number of results. About 1.9k new
  rows on ed_probe.
- **Auditability.** Answerable from the qa schema alone.
- **One fact, one function, three readers:** the page, the gate and #95's
  counting rule.
- **Project extractions.** Nothing here depends on a cadence.
- **Cost.**
  - One reset and bootstrap here, about 21 minutes from empty, and two for the
    before/after comparison.
  - The first push takes a CI cache miss, about 39 billable minutes, so the
    work ships in a single push.
- **No new dependency, command or CLI change.**

**How I covered the NFR angles:**
- Answered myself: performance and scale, reliability (criteria 4-5),
  compatibility, maintainability, observability, cost.
- Ruled out: security and privacy (only supply-id names, never rows, and never
  staging), and compliance and retention.
- Put to Keith: one auditability question (K7).

## Questions for Keith - one list, in order of how much each changes the build

Keith takes these one at a time. Each has a scenario and a recommended answer.

**K1. One order for "newest", or two?** *(architect B4; this replaces the first
draft's Q3)*

Scenario: on Wednesday a person records a decision about Clients that took
effect on Monday, and its re-check of Client reference runs on Wednesday. On
Tuesday, Notifications arrived and checked Client reference against Clients,
before the decision existed.
- **(a) Recommended: evaluation order (`run_seq`) for both the page and the
  gate.**
  - Wednesday's re-check is newest everywhere, because it is the only result
    that saw the decision.
  - Post-build-review #116 D1 still holds: a re-evaluation never outranks the
    arrival it re-evaluates, because it is always opened after it. Replays don't
    distort the order runs are opened in.
  - This changes the gate's existing effective-time order, so expect listed
    differences in the before/after comparison (see K6) wherever scripted
    decisions carry a back-dated effective time.
- **(b) Evaluation order for the page; the gate keeps effective time.** A
  criterion would state the disagreement. In this scenario the gate's newest
  result is Tuesday's, which never saw the decision, while the page shows
  Wednesday's. The "page agrees with the gate" story then has a named
  exception.

**K2. A result that read no Clients supply at all.**

Scenario: Notifications' 2024-Q3 supply arrives while Clients has no filled
slot for Q3. Its Client reference check records "could not run - cp_clients
has no filled slot".
- **(a) Recommended: it shows red on Notifications' page and does not appear on
  Clients' page.** Clients' page keeps its Q2 supply's result as its newest.
  This is what #95's B2 fix needs, and it brings the criterion 1 amendment
  above.
- **(b) It also shows on Clients' page as "could not be checked", on Clients'
  newest point.** That point is one the result never read, which is the guess
  being removed. 174 results on ed_probe have this shape.

**K3. One delivery that crosses midnight.**

Scenario: in one delivery the Notifications file arrives at 23:50 Monday and
the Clients file at 00:10 Tuesday. Clients' run then checks Client reference
against that delivery's Notifications.
- **(a) Recommended: the delivery decides.**
  - The Tuesday result counts on the Notifications supply's own Monday point.
  - Viewed as at Monday, that point shows Notifications' own result, because
    the as-of clip still uses recording time. From Tuesday it shows the newer
    one.
  - This amends your #258 Q4 "never re-dating the earlier one": the point keeps
    its date, but its value can change once a later file of the same delivery
    arrives.
- **(b) The delivery AND the same day.** Tuesday's result becomes a separate
  re-check point. That brings back the day rule, and a test that depends on
  the time zone.

**K4. How fine-grained re-check points are.**

Scenario: a person re-files the 2024-Q3 Clients supply. That one decision
re-runs Notifications' and Investigations' readers checks against it, two runs
a few seconds apart.
- **(a) Recommended: one point per supply and cause.** Clients' sparkline gains
  one re-check point for the decision. On ed_probe, 7 decisions each caused
  more than one readers run.
- **(b) One point per run.** Clients' sparkline gains two points seconds apart.
  How many points a hub table gets would then depend on how many tables read
  it, and at thirty collections that is mostly noise.

**K5. A run that is evaluated again under the same key.** *(architect B1)*

Scenario: a Clients re-check is owed. Its first attempt times out. Meanwhile a
Notifications arrival runs and reads Clients. Then the re-check is retried
under its original key and reads the newer state.
- **(a) Recommended: the retry draws a new `run_seq`.** It ranks after the
  Notifications run, which is true: it saw more.
- **(b) It keeps its first number, and a re-run whose resolution has changed is
  refused.** The retry fails and needs a new run key and a new path.

**K6. What the before/after bootstrap comparison must show.** *(architect S5)*

Scenario: before this change, `cp_notifications__X` and `cp_clients__X__r1`
share a run instant, and run-key text order makes Notifications current. After
it, evaluation order makes the Clients re-check current. Promotions and
refusals could then differ.
- **(a) Recommended: accept the differences once each one is listed with the
  tie or order that changed it** (62 groups on ed_probe share a run instant).
- **(b) Require zero differences.** That would mean keeping the run-key
  tie-break the requirement removes.

**K7 (auditability). Should the page say which supply a result read?**

Scenario: Notifications' Client reference row reads "Checked 8:20am ..., when
the Notifications supply arrived."
- **(a) Recommended: not in this requirement.** The build carries the read
  supply in the data either way, and the wording belongs to a later dashboard
  requirement.
- **(b) Add it now.** The row would end, for example, "... against the Client
  Register supply received 1 November 2020". That is new signed wording and
  would need a UX review.

## Draft for plans/running-thoughts.md #117 (for a human to apply)

> 117. **[in-progress, 2026-10-22]** **[QA Pipeline]** **[Dashboard UI]**
> **Deterministic matching of a result to the supply it is about - no ties,
> no guessing.** *(The existing first paragraph is kept.)* Scoped
> 2026-10-22 as **REQ-PIPE-279** (docs/drafts/deterministic-matching/):
> delivery-scoper drafted it, delivery-architect reviewed it, and the review
> is folded in.
> - **What gets recorded:**
>   - which supply each table was read as, for every cross-table result, in
>     `qa.check_read`;
>   - an evaluation order, `qa.run.run_seq`, drawn in `open_run`;
>   - the cause: the delivery (from `qa.filing`, no new column), decision or
>     load.
> - **Who reads it:** the page, the gate and #95, through one function.
> - **What it amends:** REQ-DASH-264 criteria 1 (if K2 = a), 3, 11 and 12, two
>   REQ-DASH-264 decisions, and REQ-PIPE-265 criterion 1.
> - **Open:** seven questions to Keith, K1-K7.
>
> This is to be built before REQ-PIPE-265 is flipped to built. The entry goes
> once REQ-PIPE-279 is built.

## Keith's answers, 2026-10-22 (Perth)

**K1 = A: one order for "newest", page and gate alike - evaluation order (`run_seq`).** Wednesday's re-check of a Monday-effective decision is newest everywhere, because it is the only result that saw the decision. The gate's effective-time order is replaced; post-build-review #116 D1 still holds because a re-run is always opened after what it re-runs. Expect listed differences in the before/after comparison wherever scripted decisions carry a back-dated effective time (K6). Rejected: B, evaluation order for the page and effective time for the gate with the disagreement named in a criterion.

**K2 = A: a result that read no supply of a table shows only on the page of the table its check is declared on.** Notifications' Q3 "every notification has a client", with no Clients filed for Q3, reads red on Notifications' page and does not appear on Clients' page, which keeps its Q2 supply's result as newest. Amends REQ-DASH-264 c1. Rejected: B, also showing it on Clients' newest point (a point it never read). Keith raised alongside it whether a page makes clear WHICH PERIOD it is showing - logged as plans/running-thoughts.md #118 and sent to the dashboard UX critic, not part of this requirement.

**K3 = C (Keith's own option): every evaluation is its own point, ordered by `run_seq`.** Keith: "an answer C that means we record/show two points for notifications - one for what was checked on Monday and another for what was re-checked on Tuesday. And that means we see two versions of its results in the dashboard too." In a delivery whose files are checked at different times (23:50 Monday Notifications, 00:10 Tuesday Clients - or any gap, not just across midnight; five deliveries on ed_probe, up to 2h50m apart), Notifications' own Monday evaluation is one point and Clients' Tuesday re-check of the shared check is a second, newer point; the gate reads the same newest (K1). Nothing is re-dated or overwritten, so #258 Q4's "never re-dating the earlier one" stands, and REQ-DASH-264's same-day rule is RETIRED rather than amended - "part of the same delivery" stops being a placement rule. Same-instant siblings still give one point (REQ-PIPE-265 evaluates once and carries). Keith noted it becomes an edge case once the transport layer gives real package boundaries ("this is a package of files to wait and process together"). Rejected: A (the delivery decides - merges the Tuesday result into Monday's point, re-dating its value) and B (delivery and same day - brings the day rule back).

**K4 = A: one point per supply and cause.** One re-file of Clients that re-runs Notifications' and Investigations' readers checks against it gives Clients' trend one re-check point, not two seconds apart; consistent with K3 = C read as "each thing that happened is its own point" (an arrival, another arrival, a decision). Asked first why Clients' page shows checks declared on Notifications at all: answered from REQ-QAC-037 c6-7 (a cross-table result is about every table it reads, shared not copied - Keith confirmed on 2026-10-21 that a red Notifications→Clients check shows red on Clients' page), bounded by Q13 = B (could-not-run counts only toward the declaring table) and K2 = A (a result that read no supply of a table is not shown on its page). Rejected: B, one point per run (point count would depend on how many tables read a hub table).

**K5 = A: a retried run draws a new `run_seq` when it starts again**, ranking after anything opened in between (it saw more). Rejected: B, keep the first number and refuse a retry whose resolution changed. Keith added: "it should also be obvious somewhere that it did time out or crash. Maybe that one for the UX review." Checked 2026-10-22: today nothing would be left to show - `reopen_run` only clears `completed_at` and `record_results` replaces a tool's results, so a failed attempt leaves no trace. Proposed to Keith: 279 records each attempt of a run (when it began, when it ended, how it ended) so the fact survives the retry; how it is shown goes to the UX review (running-thoughts #121).
Keith, same exchange: **yes, add it to 279** - a new criterion recording each attempt of a run (when it began, when it ended, how it ended: completed, timed out, crashed), kept across a retry, so both the crash's visibility (#121, display for the UX review) and check durations (#120) have their data. To be drafted into requirements-draft.yaml at the next scoper pass.

**K6 = C (Keith's own option): no before/after equivalence comparison for 279.** Keith: "I don't care about the equivalence check for this. The equivalence check is all about the refactor ... to have a single set of registration stuff. ... this is about genuine changes, so we don't need to run the equivalence check." 279 is verified by its own tests (the guess-failing scenarios in c20-21) and an ordinary bootstrap from empty; c19's comparison criterion is removed rather than relaxed. Rejected: A (accept listed differences) and B (zero differences). Keith also: the equivalence harness (REQ-TEST-239) "was a point in time thing and can be paused and retired ... but not yet deleted" - logged as plans/running-thoughts.md #122.

**K7 = A: the page does not yet say which supply a result read.** The build carries the read supply in the data either way; the wording goes to the period-clarity requirement (docs/drafts/period-clarity/review-ux-critic.md B2 asks for exactly this - every cross-table row naming both sides' period and supply), designed and UX-reviewed there as one piece. Rejected: B, adding it to REQ-DASH-264 c7's sentences inside 279.

**Split = A: keep 279 as one requirement** (built in two chunks - the record, then its readers - under one sign-off). Rejected: B, two requirements and two sign-offs; the record alone delivers nothing visible and 265 waits on both. Keith: hand 279 and #95 back to the scoper, then through the architect and both UX reviewers.
