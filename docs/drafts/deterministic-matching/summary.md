# REQ-PIPE-279 - deterministic matching: sign-off brief (v3, final)

Drafted by delivery-scoper on 2026-10-22 (Perth), from
plans/running-thoughts.md #117. delivery-architect reviewed it the same day
(`review-architect.md`). This version, 2026-10-23, folds in Keith's answers to
K1-K7 and the split question, given 2026-10-22 and kept verbatim at the end of
this file.

This is still a PROPOSAL. Nothing is in requirements.yaml and nothing is signed.
The YAML is `requirements-draft.yaml`, beside this file:
- On its own, it gives only the cross-reference errors a draft is expected to
  give (the seven requirements it depends on).
- Merged into a copy of the register, it validates clean.

Two new questions remain (N1, N2, at the end). Both are small, but each
changes what gets built, so they are open rather than settled.

## The idea in one paragraph

Today the dashboard decides where a result recorded under another table's run
belongs by guessing. It reads stamps out of run ids, compares calendar days,
breaks ties by recording time, run index or run-id text, and uses whatever the
check's declarations say today. The gate meanwhile orders by a decision's
effective time. This requirement records four facts at run time:
- **which supply each table was read as**, for every table a cross-table check
  read, including its own, and in what state;
- **an evaluation order** (`qa.run.run_seq`) that cannot tie;
- **the run's cause**: the arrival (its group of same-instant siblings), or the
  decision or load that caused it;
- **every attempt of a run**: when it began, when it ended, how it ended.

The page, the promotion gate and #95's counting rule all place and order
results from those facts, through one function, in one order, and from
nothing else. Every evaluation is its own point; nothing is re-dated or
overwritten.

## Story

As someone reading a dataset's page, I want every check result recorded under
another table's run placed on the supply it actually read, as a point of its
own for each thing that caused it to be checked, and ordered by when it was
evaluated, from recorded facts alone, so that the page, the list's counts and
the promotion gate agree on what each result is about and which is newest,
and no two people building from the same history can get a different answer.

## What it would do (24 criteria, in prose)

**Recorded at run time**
1. **What each check read.** Every cross-table result gets one row in a new
   `qa.check_read` table for each table it reads, its own included. Each row
   gives that table's state and supply: read (a contested table that fell
   through to the promoted supply is flagged contested); held (always the held
   supply's id); absent; no-supply (a sample or trial table). Written and
   replaced together with the result.
2. **Staged tables carry their supply**, taken from the filing records, with
   "read from staging or from the period" as its own field. `qa.tables_read`
   gets the supply for staged tables too.
3. **Single-table results** are about the run's own supply. The writer
   refuses one recorded under another dataset's run.
4. **No read, no record.** The writer refuses a cross-table result whose read
   can't be recorded. Today that exception is swallowed.
5. **`run_seq`** is drawn when the orchestrator opens a run, after its
   resolution is recorded and before any tool runs, and **drawn again each time
   the same run key is opened again** - a reopen, or an owed re-check retried
   under its own key - so a retry ranks after everything opened in between
   *(K5)*. Other writers never set it; a run can't complete without one.
6. **Every attempt is recorded** *(new, Keith under K5)*. A new `qa.run_attempt`
   row per opening: the run key, the `run_seq` it drew, when it began; and when
   it ends, when and how - **completed**, **timed out** (a PostgreSQL lock or
   statement timeout) or **crashed** (any other exception, with its type and
   message). An attempt is never changed once ended and never removed by a
   reopen, a retry or re-recorded results, so a run retried after a timeout
   keeps both. Nothing displays it here - that is running-thoughts #121's UX
   review - and #120's check durations can read it later. *(A killed process
   records no end: N2.)*

**What "newer" and "one point" mean**

7. **Newer means a higher `run_seq`, for the gate and the page alike** *(K1)*.
   This replaces the gate's order by a decision's effective time.
8. **Each result belongs to one point: (dataset, supply read, cause).**
   - An arrival run's cause is **its arrival** - its group of same-instant
     siblings (criterion 19); a lone arrival is a group of one. A re-check,
     readers-only or knock-on run's cause is its decision or load.
   - So two files of one delivery checked at different instants are **two
     causes and two points, whatever the gap** *(K3)*.
   - Every run one decision or load causes adds **one** point per supply it
     read *(K4)*.
   - A supply's own point is the point whose cause is that of its current run
     (REQ-PIPE-140 criterion 5).
9. **Within a point, each check shows its highest-`run_seq` result.** Under K3
   this only bites within a sibling group (the later sibling's verdict beats
   the earlier one's not-evaluated record) or one decision's fan-out.
10. **Each point counts once** - in the list's counts and sparklines and in a
    panel's run count. A point that is not a supply's own carries every other
    check's verdict from the point before. A later point never re-dates,
    merges into or overwrites an earlier one. **REQ-DASH-264 criterion 12 is
    retired** in favour of this *(K3)*.
11. **Absent or no-supply results** show only on the page of the table the
    check is declared on *(K2)*.
12. **The held page** shows results that read the held supply, and nothing
    else.

**What the build emits and reads**

13. **What the build writes out:** each own point's supply id, each result's
    read supplies (so the period-clarity work can word them later, K7), and a
    dense per-collection rank for every point and history entry - never
    `run_seq` itself. The template sorts on the rank alone. A result is still
    dated by when it was recorded, a point by its first result, and the as-of
    clip still applies per result.
14. **Which dataset and what kind of run** come from `qa.run`, never the run id.
15. **Which pages a result is shared to** comes from the recorded reads, not
    from today's check declarations.
16. **The full removal list.** Every day, time, run-index or run-id comparison
    in placement and ordering goes, across the build, the template, the gate
    and `carried`.
17. **A guard test** fails if any of that code reads `recorded_at`, run-id
    text or a day.

**The gate side**

18. **One function for all readers** - the build, the gate, `carried.decide`
    and #95 - answers "which results are about this supply", tie-break
    `run_seq` *(K1)*.
19. **REQ-PIPE-265 siblings** are read from `qa.filing` and `qa.delivery_file`,
    never parsed out of run ids.

**Schema, determinism, tests**

20. **Schema 45 to 46**, through the existing refusal: reset and bootstrap, no
    migration.
21. **Determinism.** Building twice from the same history gives byte-identical
    output, even with another collection's runs interleaved differently.
    **There is no before/after comparison** *(K6)*.
22-24. **Twenty tests, each written first and seen to fail:**
    - placement and order: two same-day Clients supplies; a delivery across
      midnight (now **two points**); **a delivery staggered within one day
      (two points, new)**; shared run instants with badly sorting keys; a
      retried re-check; interleaved collections; edited declarations; a
      contested own table; a settled pair; the writer's refusal; the JS rank
      order; a 15:00 Clients re-check; the held Case Workers case; a carried
      same-instant zip (one point);
    - **one per answer (new):** K2's Q3 Notifications with Clients absent; K1's
      Wednesday re-check of a Monday-effective decision, newest for gate and
      page; K4's one re-file fanning into two readers runs, one point;
    - **attempts (new):** a lock timeout then a completed retry; a crash then
      a completed retry, the crash kept; a killed process then a retry (N2).

## Non-functional requirements

All in the YAML.
- **Determinism.** Every query orders by a recorded key; no ordering by
  recording time, effective time, run instant, run index or run-id text.
- **The build emits a rank, never `run_seq`** - raw numbers interleave across
  parallel collection bootstraps; a per-collection rank does not.
- **Order within a collection** needs re-checks and knock-ons sequential, as
  today. The resolution is recorded before `open_run` draws the number, and
  only that sequencing keeps a decision from landing between the two; if #95's
  concurrency lands, the number is drawn under its per-(collection, period)
  lock.
- **A build reads recorded QA results only.**
- **An attempt is history, never state to tidy** - append-only, never pruned
  by a re-run; nothing here displays it.
- **Scale.** Linear in results. About 1.9k `qa.check_read` rows on ed_probe;
  about one attempt row per run plus retries. K3 adds points only where a
  delivery's files are checked at different instants (five deliveries on
  ed_probe).
- **Auditability.** Reads, causes, evaluation order and every attempt are
  answerable from the qa schema alone.
- **One fact, one function, one order, three readers.**
- **Project extractions.** Nothing depends on a cadence.
- **Cost.** One reset and bootstrap here (about 21 minutes from empty) - no
  second one, since there is no comparison. The first push is a CI cache miss
  (about 39 billable minutes), so it ships in one push.
- **No new dependency, command or CLI change.**

How I covered the NFR angles: answered myself - performance and scale,
reliability (criteria 4-6), compatibility, maintainability, observability,
cost. Ruled out - security and privacy (supply ids only, never rows or
staging), compliance and retention (an attempt row holds no data; retention is
the qa schema's, unchanged). Put to Keith - K7 (answered), N2 (an observability
detail of his own attempt record).

## Decisions Keith made (2026-10-22)

- **K1 = A.** One order for "newest", page and gate: `run_seq`. The gate's
  effective-time order goes. *Rejected B:* `run_seq` for the page, effective
  time for the gate.
- **K2 = A.** A result that read no supply of a table shows only on the
  declaring table's page. *Rejected B:* also on the absent table's newest point.
- **K3 = C (his own).** Every evaluation is its own point, ordered by
  `run_seq`; a later file of the same delivery is a second, newer point;
  nothing re-dated or overwritten; the same-day rule retired; same-instant
  siblings still one point. *Rejected A:* the delivery decides. *Rejected B:*
  delivery and same day.
- **K4 = A.** One point per supply and cause. *Rejected B:* one point per run.
- **K5 = A**, plus his addition: a retry draws a new `run_seq`; and every
  attempt is recorded (began, ended, how), its display left to #121. *Rejected
  B:* keep the first number and refuse a changed retry.
- **K6 = C (his own).** No before/after equivalence comparison for 279 -
  "this is about genuine changes". REQ-TEST-239 untouched here (#122).
  *Rejected A:* accept listed differences. *Rejected B:* zero differences.
- **K7 = A.** The page doesn't yet say which supply a result read; the build
  carries it; wording goes to period-clarity (B2). *Rejected B:* add it now.
- **Split = A.** One requirement, built in two chunks. *Rejected B:* two
  requirements.

Every rejected option is in the YAML's `decisions:`.

## What his answers changed in the draft

- **K3 = C reshaped the point.** "The delivery decides" no longer exists as a
  placement rule. The cause of an arrival run is now its **arrival** (its
  same-instant sibling group), not its delivery - so an arrival of another file
  in the same delivery is its own cause. K4's "one point per supply and cause"
  then reads as Keith put it: each thing that happened - an arrival, another
  arrival, a decision - is its own point.
- **K3 also reached REQ-DASH-264 criterion 11**, whose trigger is the same-day
  merge. I've read "the same-day rule is retired" as covering it too: its
  "count as one run" and "compare against the delivery before" go, its labels
  stay. That is the reading behind N1 - say if it's wrong.
- **K6 = C** removed criterion 19's comparison clause, REQ-TEST-239 from the
  dependencies, and the second bootstrap from the cost.
- **K5's addition** is criterion 6 and tests 18-20.
- **One correction of my own:** v2 said `run_seq` is drawn "in the same
  transaction as the resolution". It isn't - the resolution is recorded earlier,
  in the period overlay's own transaction. The criterion now says "after the
  resolution is recorded and before any tool runs", and the sequencing NFR names
  the gap.

## Amendments and retirements of signed wording (old -> new)

**REQ-DASH-264 criterion 12 - RETIRED** (Keith, #258 Q4; retired by K3 = C):
- OLD: "THE SYSTEM SHALL count a result recorded under another table's run, in
  the dataset list's counts and sparklines, on the dataset's own run only where
  it was recorded the same day; one recorded on a later day is a point of its
  own on that day, every other check carrying its verdict into it from the point
  before."
- NEW: struck, marked "RETIRED 2026-10-2x (Keith, REQ-PIPE-279 K3 = C) - see
  REQ-PIPE-279 criteria 8 and 10". What Q4 kept - a point of its own, every
  other check carrying its verdict from the point before - lives on in 279
  criterion 10, without the day.

**REQ-DASH-264 criterion 11** (Keith, #258 Q3) - the same-day merge goes, the
labels stay. *Provisional on N1.*
- OLD: "WHERE two results in a check's history were recorded on the same day
  and either came from another table's run - one delivery checked once by each
  table - THE SYSTEM SHALL count them as one run in the panel's run count,
  compare by default against the newest result of the delivery before, and
  label each such row in the history table and the compare list with where it
  came from ("from the <table>'s run", "from the <table>'s re-check"). A
  same-day resupply of the dataset's own stays two runs."
- NEW: "WHERE a result in a check's history came from another table's run, THE
  SYSTEM SHALL label its row in the history table and the compare list with
  where it came from ("from the <table>'s run", "from the <table>'s re-check"),
  count each point of REQ-PIPE-279 once in the panel's run count, and compare a
  point by default against [N1: the newest earlier point with an evaluated
  result for that check]."

**REQ-DASH-264 criterion 3** (held table):
- OLD: "... with its result where one was recorded at or after the held
  supply's receipt, and as not run ... where none was ..."
- NEW: "... with its result where one read the held supply (REQ-PIPE-279), and
  as not run ... where none did ..."

**REQ-DASH-264 criterion 1** (K2 = A):
- OLD: "... the newest result recorded for that dataset on or before the
  in-place-on date, whichever table's run recorded it ..."
- NEW: "... the newest result, by evaluation order (REQ-PIPE-279), about a
  supply of that dataset and recorded on or before the in-place-on date,
  whichever table's run recorded it ..."

**REQ-DASH-264 decisions marked superseded by REQ-PIPE-279** (five; v2 had two):
- "A re-check is told apart by its run id's `__r<N>`" - the kind of run comes
  from `qa.run.scope` (criterion 14).
- "A result from another table's run counts ... on the dataset's own run it
  follows, replacing that run's verdict for the check" - highest `run_seq`
  within a point (criterion 9), each point counted once (criterion 10).
- "A result recorded under another table's run is placed in a check's history
  by the time it was recorded, after the last of the dataset's own entries
  recorded no later; the dataset's own entries keep their receipt order" -
  ordered by rank (criterion 13). *(new)*
- In "Option 2 for a held table": "kept by counting only results recorded at or
  after the held receipt" - by the read supply (criterion 12). *(new)*
- In "Keith's four answers on #258": the Q3 sentence (same-day pairs, the day's
  newest compared against) - the same-day merge is retired; Q4's carry-forward
  stands. *(new)*

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
  rest is unchanged. #95 v4's REQ-PIPE-266 criterion 1 inherits this.

**REQ-PIPE-265 decision marked superseded:** "Siblings are read from the run
ids on record rather than passed through the run step" - read from `qa.filing`
and `qa.delivery_file` (criterion 19); the reason it gave (a later gate in
another process must find the same answer) holds better from the record.
*(new)* REQ-PIPE-265 criterion 9 (its own before/after comparison) is not
touched - K6 was about 279 only.

**#95 v4 knock-ons, to apply when #95 v5 is drafted:**
- REQ-PIPE-267 criterion 1 and REQ-PIPE-269 criteria 1-2 cite REQ-PIPE-279
  criterion 1, not `qa.tables_read`.
- REQ-PIPE-269 criterion 7's single selection function is 279 criterion 18's.
- #95's "newest" is `run_seq` (K1), and its points are 279's (K3, K4).

## Two new questions for Keith

**N1. What does a check's panel compare a point against by default?**
*(changes REQ-DASH-264 criterion 11's amendment)*

Scenario: Notifications' 2024-Q3 file arrives 09:00 Monday and Clients' at
11:50 the same day. Notifications' own run records Client reference "could not
be checked" (no Clients for Q3 yet); Clients' run at 11:50 records it passing.
Under K3 that is two points on Notifications' page. On Wednesday a Clients
re-file decision re-runs it again: a third point. You open the 11:50 result.
- **(a) The point just before it.** 11:50 compares against 09:00's "could not
  be checked" - true, but tells you nothing. This was the case in 312 of 2,508
  same-day pairs, which is why your #258 Q3 answer compared against the delivery
  before.
- **(b) Recommended: the newest earlier point with an evaluated result for
  that check.** 11:50 compares against Q2's last real verdict; Wednesday's
  compares against 11:50's. Deterministic (evaluated or not is recorded) and
  keeps your Q3 intent without the day.
- **(c) The newest point of the previous supply.** 11:50 compares against Q2,
  but so does Wednesday's re-check, which hides what the re-file changed.

**N2. An attempt whose process was killed.** *(changes criterion 6)*

Scenario: a Clients re-check is running when the machine is restarted. Nothing
gets to write the attempt's end. The next day the processing pass retries it.
- **(a) Recommended: closed as "interrupted", end time unknown,** when the
  next attempt of that run begins or `qa_store.incomplete_runs` finds it. The
  record says what is known and nothing invented.
- **(b) Recorded as "crashed", no end time.** Keeps your three outcomes, but
  "crashed" then means two things - a recorded exception, or nothing recorded at
  all.

## Draft for plans/running-thoughts.md #117 (for a human to apply)

> 117. **[in-progress, 2026-10-22]** **[QA Pipeline]** **[Dashboard UI]**
> **Deterministic matching of a result to the supply it is about - no ties,
> no guessing.** *(The existing first paragraph is kept.)* Scoped
> 2026-10-22 as **REQ-PIPE-279** (docs/drafts/deterministic-matching/):
> delivery-scoper drafted it, delivery-architect reviewed it, and Keith answered
> K1-K7 the same day (K3 and K6 his own options); folded in 2026-10-23.
> - **What gets recorded:** which supply each table was read as
>   (`qa.check_read`); an evaluation order (`qa.run.run_seq`, redrawn on a
>   retry); the cause (arrival group, decision or load); every attempt of a run
>   (`qa.run_attempt`).
> - **Who reads it:** the page, the gate and #95, through one function, in one
>   order. Every evaluation is its own point.
> - **What it changes:** retires REQ-DASH-264 criterion 12; amends its criteria
>   1, 3 and 11 and five of its decisions, and REQ-PIPE-265 criterion 1 and one
>   decision.
> - **Open:** N1 (default comparison), N2 (a killed attempt).
> - Attempt display is #121; check durations #120; REQ-TEST-239's retirement
>   #122.
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
