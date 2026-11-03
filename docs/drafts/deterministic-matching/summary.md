# REQ-PIPE-279 - deterministic matching: sign-off brief (v4, final)

Drafted by delivery-scoper on 2026-10-22 (Perth), from
plans/running-thoughts.md #117. History of this draft:
- delivery-architect reviewed it the same day (`review-architect.md`);
- v3 folded in Keith's answers to K1-K7 and the split;
- delivery-architect, delivery-dashboard-ux and delivery-cli-ux then reviewed
  v3 (`docs/drafts/review-*-279v3-95v5.md`);
- this version, v4 (2026-10-23), folds in those reviews and Keith's answers to
  N1 and N2.

Keith's answers are kept word for word at the end of this file.

This is still a PROPOSAL. Nothing is in requirements.yaml and nothing is signed.
The YAML is `requirements-draft.yaml`, beside this file:
- On its own, it gives only the expected cross-reference errors (the nine
  requirements it depends on).
- Merged into a copy of the register, it validates clean (249 requirements,
  zero errors).

**No question is open.**

## The idea in one paragraph

Today the dashboard guesses where a result recorded under another table's run
belongs. It reads stamps out of run ids, compares calendar days, breaks ties by
recording time, run index or run-id text, and uses whatever the check's
declarations say today. The gate, meanwhile, orders by a decision's effective
time.

This requirement records four facts at run time:
- **which supply each table was read as**, for every table a cross-table check
  read, its own included, and in what state;
- **an opening order** (`qa.run.run_seq`) that cannot tie;
- **the run's cause**: its arrival (its group of same-instant siblings), or the
  decision, load or (with #95) gate application that caused it;
- **every attempt of a run**: when it began, when and how it ended. Each attempt
  holds a lock, so "still running?" has a deterministic answer.

The page, the promotion gate and #95's counting rule all place and order
results from those facts, through one function, in one order, and from nothing
else. Every evaluation is its own point. Nothing is re-dated or overwritten.

## Story

As someone reading a dataset's page, I want every check result recorded under
another table's run placed on the supply it actually read, as a point of its
own for each thing that caused it to be checked, and ordered by when it was
evaluated, from recorded facts alone, so that the page, the list's counts and
the promotion gate agree on what each result is about and which is newest,
and no two people building from the same history can get a different answer.

## What it would do (28 criteria, in prose)

**Recorded at run time**

1. **What each check read.** Every cross-table result gets one row in a new
   `qa.check_read` table for each table it reads, its own included. Each row
   gives the table's state and supply:
   - read (a contested table that fell through to the promoted supply is
     flagged contested);
   - held (always the held supply's id);
   - absent;
   - no-supply (a sample or trial table).

   The rows are written and replaced together with the result.
2. **Staged tables carry their supply**, with "read from staging or from the
   period" as a field of its own. `qa.tables_read` gets the supply for staged
   tables too.
3. **Single-table results** are about the run's own supply. The writer refuses
   one recorded under another dataset's run.
4. **No read, no record.** The writer refuses a cross-table result whose read
   can't be recorded. Today that exception is swallowed.
5. **`run_seq`** is drawn when the orchestrator opens a run, and drawn again
   each time the same run key is opened again *(K5)*.
   - **It is the order runs were opened, not a claim about what they saw.**
     What a run saw is its `qa.check_read` rows, and nothing may infer it from
     `run_seq` *(architect S1)*.
6. **Every attempt is recorded** in a new `qa.run_attempt` table. Each row holds
   the run key, the `run_seq` the attempt drew, when it began, and when and how
   it ended:
   - **completed**;
   - **timed out** (a lock or statement timeout on our own connections);
   - **interrupted** (Ctrl-C, SIGTERM or a stopped pass, end time known);
   - **crashed** (anything else, including a dbt or Soda timeout, with its
     message truncated to 1,000 characters).

   The end is written in a `finally` that catches everything, on a fresh
   connection. An attempt is never changed once ended and never removed, except
   by `trial.discard`, which deletes a trial run with everything under it.
7. **Every attempt holds a lock for as long as it runs** *(N2, your lock rule)*.
   It is a PostgreSQL session advisory lock keyed on the run key.
   - An attempt with no recorded end is **running** while its lock is held.
   - When the next attempt takes the lock and finds an earlier one with no end,
     it closes that one as **interrupted, end time unknown**.
   - Nothing that doesn't hold the lock (`incomplete_runs` included) ever
     closes an attempt.
8. **`mothman debug run-*` is refused against an already-evaluated run.**
   Otherwise it would replace results under an old `run_seq`, with no attempt
   recorded *(architect S3)*.

**What "newer" and "one point" mean**

9. **Newer means a higher `run_seq`, for the gate and the page alike** *(K1)*.
10. **Each result belongs to one point: (dataset, supply read, cause).**
    - The cause of an arrival run is its arrival group. A re-check, readers-only
      or knock-on run's cause is its decision or load.
    - Once #95's REQ-PIPE-267 is built, a run inside a gate application has the
      application as its cause.
    - Two files of one delivery checked at different instants are two points
      *(K3)*.
    - One cause adds one point per supply it read *(K4)*.
    - A run with no supply (a trial's or a fixture's) is placed on no point
      *(architect S6)*.
11. **Within a point, each check shows its highest-`run_seq` result.**
12. **Each point counts once**, through one function shared by the list's
    counts, its sparklines and the panel's run count *(dashboard UX)*. A later
    point never re-dates, merges into or overwrites an earlier one.
    **REQ-DASH-264 criterion 12 is retired.**
13. **The default comparison** is the newest earlier point that has an
    evaluated result for that check *(N1)*.
    - One function decides both the default and whether `?cmp=` is written.
      This fixes an existing deep-link defect, test first.
    - Every compare and history entry names its cause, and so does the
      sparkline tooltip of every point that isn't a supply's own.
14. **Absent or no-supply results** show only on the declaring table's page
    *(K2)*.
15. **The held page** shows results that read the held supply, and nothing
    else.

**What the build emits and reads**

16. **What the build writes out:**
    - each own point's supply id;
    - each result's read supplies;
    - each point's cause;
    - a dense per-collection rank, never `run_seq` itself.

    The template sorts on the rank alone. Dates and the as-of clip still use
    recording time.
17. **Which dataset and what kind of run** come from `qa.run`, never from the
    run id.
18. **Which pages a result is shared to** comes from the recorded reads, not
    from today's declarations.
19. **The full removal list.** It now also names the readers the architect
    found still ordering by run id: `list_run_ids`, `runs_for`, the manifest
    sort by `run_index` with the stamp `recheck` writes for it, and
    `drift_reference`'s fallback. `drift_reference` follows `run_seq`.
20. **A guard test** fails if any placement or ordering code reads
    `recorded_at`, run-id text or a day. It covers those readers too.

**The gate side**

21. **One function for all readers:** the build, the gate, `carried.decide`
    and #95.
22. **REQ-PIPE-265 siblings** are read from `qa.filing` and `qa.delivery_file`.

**Schema, determinism, pins, tests**

23. **Schema 45 to 46.** Reset and bootstrap, no migration.
24. **Determinism.** The build is byte-identical from the same history. There
    is no before/after comparison *(K6)*.
25. **Pins.** If the bootstrap moves REQ-PIPE-262 criterion 12's pinned
    inheritances, TS-63 or REQ-GEN-251 criterion 3, each comes to you with its
    cause. Nothing is re-pinned silently (carried from #95's REQ-PIPE-271
    criterion 9).

26-28. **Twenty-six tests, each written first and seen to fail.** The v3
twenty are kept, and v4 adds six:
- a decision landing between the overlay and `open_run`, with the gate's
  choice unchanged;
- Ctrl-C and SIGTERM recorded as interrupted, never crashed;
- a killed process closed by the next attempt's lock;
- a live attempt in another process left alone by `incomplete_runs`;
- `debug run-dbt` refused;
- `trial.discard` with attempts;
- the default comparison and `?cmp=` deciding the same thing.

## Non-functional requirements

All of these are in the YAML.
- **Determinism.** Everything orders by a recorded key.
- **The build emits a rank, never `run_seq`.**
- **Opened is not saw.** A person's decision can land between a run's overlay
  and its `open_run`. Placement filters on recorded supplies, so the only
  possible effect is the order of two results about one supply. #95's period
  lock closes the gap inside gate applications. (This replaces v3's
  sequencing NFR, which the architect showed was false.)
- **A build reads recorded QA results only.**
- **An attempt is history**: written at its start and its end, never pruned.
- **Liveness is a lock, never a timeout**: no clock, heartbeat or staleness
  threshold.
- **Security**: exception messages are truncated before they are stored.
- **Scale**: linear in results. About 1.9k `qa.check_read` rows; about one
  attempt row and one lock per run.
- **Auditability**: everything above is answerable from the qa schema alone.
- **One fact, one function**, for both placement and counting.
- **Project extractions**: nothing depends on a cadence.
- **Cost**: one reset and bootstrap (about 21 minutes from empty), and one CI
  cache miss (about 39 billable minutes), so it ships in one push.
- **No new dependency or command.** The only CLI-visible change is the
  `debug run-*` refusal.

How I covered the NFR angles:
- Answered myself: performance and scale, reliability (criteria 4-8),
  compatibility, maintainability, observability, security (message
  truncation), cost.
- Ruled out: privacy (supply ids only, never rows), and compliance and
  retention (an attempt row holds no data).
- Put to you: N2 (answered).

## Decisions Keith made (2026-10-22)

- **K1 = A.** One order for "newest", page and gate: `run_seq`. The gate's
  effective-time order goes.
  - *Rejected B:* `run_seq` for the page and effective time for the gate.
- **K2 = A.** A result that read no supply of a table shows only on the
  declaring table's page.
  - *Rejected B:* also showing it on the absent table's newest point.
- **K3 = C (your own option).** Every evaluation is its own point, ordered by
  `run_seq`.
  - A later file of the same delivery is a second, newer point.
  - Nothing is re-dated or overwritten, and the same-day rule is retired.
  - Same-instant siblings are still one point.
  - *Rejected A:* the delivery decides. *Rejected B:* the delivery and the
    same day.
- **K4 = A.** One point per supply and cause.
  - *Rejected B:* one point per run.
- **K5 = A, plus your addition.** A retry draws a new `run_seq`, and every
  attempt is recorded. How attempts are displayed goes to #121.
  - *Rejected B:* keep the first number and refuse a retry whose resolution
    changed.
- **K6 = C (your own option).** No before/after equivalence comparison for 279.
  REQ-TEST-239 is not touched here (#122).
  - *Rejected A:* accept differences once listed. *Rejected B:* require zero
    differences.
- **K7 = A.** This requirement doesn't word which supply a result read. The
  build carries it, and the period-clarity work words it by extending #95's
  REQ-PIPE-272 notes rather than adding a second vocabulary.
  - *Rejected B:* add the wording now.
- **Split = A.** One requirement, built in two chunks.
  - *Rejected B:* two requirements.
- **N1 = B.** The default comparison is the newest earlier point with an
  evaluated result for that check. The conditions you accepted:
  - one function for the default and `?cmp=`;
  - each entry names its cause;
  - once #95's grid lands, comparison stays within one bucket (#95's REQ-PIPE-272
    will say so).
  - *Rejected A:* the point just before. *Rejected C:* the previous supply's
    newest point.
- **N2 = A, with your lock rule.** Every attempt holds a lock named after its
  run key.
  - The states are running, completed, timed out, crashed and interrupted.
  - Interrupted covers a stop we saw (end time known) and a death found when
    the next attempt takes the lock (end time unknown).
  - An attempt is never closed from `incomplete_runs` or any other reader that
    doesn't hold the lock.
  - *Rejected B:* "crashed" with no end time.
- **Two technical answers you accepted with V5-Q1 (#95):**
  - REQ-DASH-264 criterion 1 is amended by 279 in its own words, then amended
    again by #95's REQ-PIPE-269, quoting 279's wording as OLD.
  - Runs inside a gate application have the application as their cause
    (279 criterion 10, conditional on REQ-PIPE-267).
  - *Rejected:* 269 owning criterion 1 alone; each hold-back decision as its
    own cause.

Every rejected option is in the YAML's `decisions:`.

## What changed from v3 to v4

- **From your answers:**
  - criterion 13 (N1);
  - criteria 6-7 and tests 21-23 (N2 and the lock rule);
  - the gate-application cause in criterion 10;
  - the two-step REQ-DASH-264 criterion 1 decision.
- **From the architect:**
  - **S1** - criterion 5's "opened is not saw", the rewritten NFR, and test 18.
  - **S2** - criteria 19-20's readers and `drift_reference`.
  - **S3** - criterion 8 and test 24.
  - **S4** - the `trial.discard` exception and test 25.
  - **S5** - the outcome definitions in criterion 6.
  - **S6** - no-supply runs in criterion 10.
  - **The notes:**
    - criterion 25's pin rule;
    - the attempt row and `run_seq` written in one transaction;
    - message truncation;
    - #95's package versus 279's cause, now in `decisions:`.
- **From dashboard UX:**
  - the sparkline tooltip and the one counting function (criteria 12-13);
  - the K7 note about #95's REQ-PIPE-272;
  - the `?cmp=` defect as test 26.
- **From CLI UX:**
  - Ctrl-C and SIGTERM are interrupted, never crashed (criterion 6, test 21);
  - the #122 note that comparing across the schema bump shows differences
    everywhere, which is not a regression;
  - CLI display of times stays as it is.
- **Not part of 279:** post-build-review #261 (the compare card overflow) is a
  separate defect fix. Criterion 13 doesn't contradict it. It adds no label
  text beyond the cause that REQ-DASH-264 already names, and `decisions:` says
  so.
- **Small choices of my own, flagged for you to strike if wrong:**
  - exception messages truncated at 1,000 characters;
  - a `debug run-*` re-run refused rather than given its own `run_seq` (which
    would let a debug run outrank the real ones).

## Amendments and retirements of signed wording (old -> new)

**REQ-DASH-264 criterion 12 - RETIRED** (Keith, #258 Q4; retired by K3 = C):
- OLD: "THE SYSTEM SHALL count a result recorded under another table's run, in
  the dataset list's counts and sparklines, on the dataset's own run only where
  it was recorded the same day; one recorded on a later day is a point of its
  own on that day, every other check carrying its verdict into it from the point
  before."
- NEW: struck, and marked "RETIRED 2026-10-2x (Keith, REQ-PIPE-279 K3 = C) - see
  REQ-PIPE-279 criteria 10 and 12". The part of Q4 that survives (a point of
  its own, every other check carrying its verdict from the point before) lives
  on in 279 criterion 12, without the day.

**REQ-DASH-264 criterion 11** (Keith, #258 Q3). The same-day merge goes, the
labels stay, and N1 sets the default:
- OLD: "WHERE two results in a check's history were recorded on the same day
  and either came from another table's run - one delivery checked once by each
  table - THE SYSTEM SHALL count them as one run in the panel's run count,
  compare by default against the newest result of the delivery before, and
  label each such row in the history table and the compare list with where it
  came from ("from the <table>'s run", "from the <table>'s re-check"). A
  same-day resupply of the dataset's own stays two runs."
- NEW: "WHERE a result in a check's history came from another table's run, THE
  SYSTEM SHALL label its row in the history table and the compare list, and the
  sparkline tooltip of its point, with where it came from ("from the <table>'s
  run, <time>", "from the <table>'s re-check, <time>"), count each point of
  REQ-PIPE-279 once in the panel's run count, and compare a point by default
  against the newest earlier point with an evaluated result for that check,
  one function deciding both that default and the ?cmp= URL state
  (REQ-PIPE-279 criterion 13)."

**REQ-DASH-264 criterion 1** (K2 = A). #95's REQ-PIPE-269 amends it again
afterwards, quoting this NEW wording as its OLD:
- OLD: "... the newest result recorded for that dataset on or before the
  in-place-on date, whichever table's run recorded it ..."
- NEW: "... the newest result, by evaluation order (REQ-PIPE-279), about a
  supply of that dataset and recorded on or before the in-place-on date,
  whichever table's run recorded it ..."

**REQ-DASH-264 criterion 3** (held table):
- OLD: "... with its result where one was recorded at or after the held
  supply's receipt, and as not run ... where none was ..."
- NEW: "... with its result where one read the held supply (REQ-PIPE-279), and
  as not run ... where none did ..."

**REQ-DASH-264 decisions marked superseded by REQ-PIPE-279** (five):
- "A re-check is told apart by its run id's `__r<N>`". Superseded by
  `qa.run.scope` (criterion 17).
- "A result from another table's run counts ... on the dataset's own run it
  follows, replacing that run's verdict for the check". Superseded by
  criteria 11 and 12.
- "A result recorded under another table's run is placed in a check's history
  by the time it was recorded ...; the dataset's own entries keep their receipt
  order". Superseded by the rank (criterion 16).
- In "Option 2 for a held table": "kept by counting only results recorded at or
  after the held receipt". Superseded by the read supply (criterion 15).
- In "Keith's four answers on #258": the Q3 sentence, about same-day pairs and
  the day's newest. Superseded by the retirement above and N1. Q4's
  carry-forward stands.

**REQ-PIPE-265 criterion 1:**
- OLD: "THE SYSTEM SHALL treat as SIBLINGS the arrival runs of one collection
  whose run ids share one receipt instant (the run id after its table name,
  REQ-PIPE-105 criterion 1) - files filed together before the first of them is
  checked (REQ-PIPE-105 criterion 5) - reading that from the record, and SHALL
  treat no other pair of runs as siblings. ..."
- NEW: "THE SYSTEM SHALL treat as SIBLINGS the arrival runs of one collection
  whose supplies were filed from one delivery with one receipt instant
  (qa.filing, qa.delivery_file) - files filed together before the first of them
  is checked (REQ-PIPE-105 criterion 5) - reading that from the record and never
  from run ids, and SHALL treat no other pair of runs as siblings. ..." The
  rest is unchanged. #95's REQ-PIPE-266 criterion 1 inherits this.

**A REQ-PIPE-265 decision marked superseded:** "Siblings are read from the run
ids on record rather than passed through the run step". Superseded by
criterion 22. REQ-PIPE-265 criterion 9 is not touched.

**#95 knock-ons, for #95's next draft:**
- REQ-PIPE-267 criterion 1 and REQ-PIPE-269 criteria 1, 2 and 4 cite 279
  criterion 1 (architect v5 B1).
- REQ-PIPE-269 criterion 7's selection function is 279 criterion 21's.
- REQ-PIPE-269 amends REQ-DASH-264 criterion 1, quoting 279's wording as OLD.
- REQ-PIPE-267 owns the gate-application id that 279 criterion 10 reads.
- REQ-PIPE-272 says that comparison stays within one bucket, and its notes are
  where period-clarity names read supplies.
- #95's "newest" is `run_seq`, and its points are 279's.

## Draft for plans/running-thoughts.md #117 (for a human to apply)

> 117. **[in-progress, 2026-10-22]** **[QA Pipeline]** **[Dashboard UI]**
> **Deterministic matching of a result to the supply it is about - no ties,
> no guessing.** *(The existing first paragraph is kept.)* Scoped
> 2026-10-22 as **REQ-PIPE-279** (docs/drafts/deterministic-matching/):
> delivery-scoper drafted it, delivery-architect reviewed it twice, the
> dashboard and CLI UX reviewers once; Keith answered K1-K7, N1 and N2
> (K3, K6 his own options; the attempt record and its lock rule his
> additions). v4 folded in 2026-10-23; no question open.
> - **What gets recorded:** which supply each table was read as
>   (`qa.check_read`); an opening order (`qa.run.run_seq`, redrawn on a
>   retry); the cause (arrival group, decision, load, gate application);
>   every attempt of a run, each holding a lock on its run key
>   (`qa.run_attempt`).
> - **Who reads it:** the page, the gate and #95, through one function, in one
>   order. Every evaluation is its own point.
> - **What it changes:** retires REQ-DASH-264 criterion 12; amends its criteria
>   1, 3 and 11 and five of its decisions, and REQ-PIPE-265 criterion 1 and one
>   decision.
> - Attempt display is #121; check durations #120; REQ-TEST-239's retirement
>   #122; the compare-card overflow post-build-review #261 (separate).
>
> To be built before REQ-PIPE-265 is flipped to built. The entry goes once
> REQ-PIPE-279 is built.

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

**N1 = B: a check's compare card defaults to the newest earlier point with an evaluated result for that check** (earlier = lower emitted rank; "evaluated" = the existing `carried.not_evaluated_reason` / `NOT_EVALUATED_KEYS` definition). Shown the real panel first (post-build-review #261 found on the way: the "Latest result" half is pushed out of the panel by a long compared-run label). Conditions from the reviewers: one function decides both the default and the `?cmp=` URL rule (dashboard UX S7 - an existing defect, test-first); each compare/history entry names its cause; once #95's grid lands, compare within one bucket (staged or warehouse). Rejected: A, the point just before (often "could not be checked"); C, the previous supply's newest point (hides what a re-check changed).

**N2 = A, with a lock rule added: an attempt whose process died is closed as "interrupted", end time unknown, only when the next attempt of that run takes the run's lock.** Keith asked how we would know it had died rather than still running. Answer, from the code: PostgreSQL releases a session advisory lock when its connection dies (crash, kill, machine restart); `processing_pass.arrival_lock` already holds one per arrival for the whole run. Keith approved adding: EVERY attempt holds a session advisory lock named after its run key for as long as it runs (today re-checks and knock-ons are serialised by locks some of which last only for the claim). So "still running?" = "is its lock held?" - deterministic, no timeout. Attempt states: running (lock held); completed / timed out / crashed (end recorded); interrupted - a stop we saw (Ctrl-C/KeyboardInterrupt, SIGTERM, a stopped pass: end known) or a death found when the next attempt takes the lock (end unknown). Never closed from `incomplete_runs` or any reader that does not take the lock (architect v3 N2). Rejected: B, "crashed" with no end time.

**Keith, 2026-10-23 (Perth): both of the scoper's v4 calls stand** - exception messages in `qa.run_attempt` truncated at 1,000 characters (security NFR), and `mothman debug run-*` refused against an evaluated run rather than given its own `run_seq` (c8).
