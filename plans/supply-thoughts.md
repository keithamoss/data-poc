# Supply thoughts - the transport layer, not yet scoped

A capture buffer for questions about **how a supply physically gets to
us**, opened 2026-10-01 at Keith's own ask after a long conversation
about REQ-PIPE-077 kept running into them. Everything here is a
question or a sketch; nothing in it is agreed, and nothing should be
built from it without going through `delivery-scoper` and a sign-off
the way any other requirement does.

**How this differs from the other buffers**, since there are now three
and a fourth would be a mess rather than a filing system:

- `plans/running-thoughts.md` is Keith's own forward-looking ideas,
  landed in a batch and not yet scoped - ticketing, gamification, an
  AWS MVP. Where an idea came from HIM, unprompted, it goes there.
- `plans/road-testing.md` is what turns up while USING the dashboard or
  the CLI. A sighting rather than a diagnosis.
- **This file** is the transport layer specifically: what a delivery
  IS, what carries it, what signals its boundaries, where it lands and
  where it goes afterwards. It exists because `plans/supply-model.md`
  is about the LIFECYCLE of a supply once we have it - arrival
  classification, filing, promotion, the decision log - and that file
  is already very large. This is the layer underneath it.

A thing here graduates by becoming a requirement, at which point the
entry is deleted rather than marked done - the standing rule in
CLAUDE.md, and the reason `decisions:` exists on a requirement.

**THIS FILE IS PARKED UNTIL THE SIGNED SPRINT QUEUE IS CLOSED OUT -
Keith, 2026-10-01, and it is a sequencing instruction rather than a
loss of interest.** His words: he does not want to hold up finishing
the sprints from the other day at the cost of going down this road.
So nothing here is built, scoped or researched until that queue is
done, with ONE carve-out he named himself: where a decision recorded
here genuinely CHANGES one of those requirements, it lands with that
requirement rather than waiting.

Two such carve-outs exist as of 2026-10-01, both settled by him and
both listed in #0: `REQ-PIPE-077`'s criterion 1 (only the off-cycle
supply is withheld) and `REQ-PIPE-079`'s revision (105 takes
precedence). Neither is optional - leaving them would mean building
the rest of the queue against a register that records a decision he
has already reversed.

Worth knowing before picking work off that queue, because it is not
obvious from the outside: THREE of the six signed-and-unbuilt
requirements cannot close without opening a door this file or the
unsigned calendar work owns. `REQ-PIPE-105`'s unbuilt half IS the
arrival unit, which is the substance of this file; `REQ-PIPE-078`'s
last two criteria moved to `REQ-PIPE-115`, which is parked pending
research; and `REQ-GEN-044`'s criteria 8-11 are repointed at
`REQ-PIPE-110`/`113`, which are unsigned. That leaves
`REQ-PIPE-080` and `REQ-PIPE-081` as the genuinely clean ones.

---

0. **[todo, 2026-10-01]** **[Docs & process]** The open threads from
   the 2026-09-30 conversation, written down so they survive the
   session that produced them.

   Not design work - a register of what is genuinely waiting, because
   several of these are decisions only Keith can make and they were
   accumulating in chat.

   **SETTLED BY KEITH, 2026-10-01 - two of these are now answers
   rather than questions, and both need the register changed to
   match:**
   - **`REQ-PIPE-077`: only the OFF-CYCLE SUPPLY is withheld, never
     the whole delivery.** His reasoning is the one that dissolves the
     gate rather than tuning it: once every file is its own arrival,
     there is no delivery unit to withhold - case-workers' Q1 is
     assessed on its merits and the other five on theirs. So there is
     NO hard block on a cross-period delivery; a delivery CAN span
     periods and the rules already in place handle it, because we know
     the cadences and we already know what fills, what holds and what
     is off-cycle. An off-cycle partial-participation arrival is still
     flagged, still QA'd, and still kept from auto-promotion so a
     person decides whether it belongs in its own period or is an
     off-schedule supply for the current one. **This amends criterion
     1 of a BUILT requirement** and needs doing properly.
   - **`REQ-PIPE-079` vs `REQ-PIPE-105`: 105 TAKES PRECEDENCE.** A run
     overlays what is staged for the PERIOD, regardless of the
     delivery it arrived in. 079 needs revising to say so - either
     directly, or by the route criterion 9 already uses for
     `REQ-PIPE-035` and `036`, naming it for amendment with the new
     wording stated rather than implied.

   **Still waiting on Keith:**
   - **`REQ-PIPE-079` risk call.** Swapping `borrow_views()` for
     `create_overlay_views()` changes what every CP cross-table check
     reads, so recorded verdicts will move. Happy for them to shift,
     or want a before/after comparison first?
   - **`REQ-PIPE-110`-`113`** remain unsigned, 64 criteria, and
     `REQ-GEN-044` criteria 8-11 wait on them.

   **Recorded, not blocking:**
   - `REQ-PIPE-077`'s **blind spot**: the catch-up drop it exists to
     catch trips it only while the older period is unfilled AND not
     closed by monotonic filling. Once that period is filled - the
     commoner case - the older table files into the current period as
     a resupply and nothing notices. A limit of the signed criteria,
     not a build defect.
   - `REQ-PIPE-115` (an unreadable table is red and never stops the
     run) is drafted, unsigned, parked pending research, and has NOT
     been through `delivery-scoper`.
   - `REQ-PIPE-078` criteria 9 and 10 are now 115's.
   - `plans/data-generation.md` #11 - the generator ignores
     `delivery_months`, so the synthetic corpus contradicts its own
     configured participation.
   - CI speed-ups, deferred by Keith to "later today" on 2026-09-30
     and not picked up.

1. **[investigate, 2026-10-01]** **[Pipeline & publishing]** What IS a
   delivery, now that the answer has moved twice?

   **Today** it is a directory. `delivery.py`'s own spec: "A DELIVERY
   IS ONE PHYSICAL ARRIVAL of one or more files, and one directory
   under `data/deliveries/` is one delivery. The boundary is the
   directory, observable from a listing without opening anything -
   which is what a real transport gives you: one S3 prefix, one SFTP
   session, one folder drop." One receipt instant per delivery, ours,
   recorded outside the delivery so a supplier cannot set our clock.

   **`REQ-PIPE-105` replaces that with the file**, and drops
   delivery-level completeness rather than replacing it - nothing
   waits for a folder to be finished, because nothing can know when it
   is. Four alternatives are recorded as rejected there: a
   supplier-written marker, the DynamoDB arrival counter (built and
   tested, then discarded), a quiet period, and a deadline backstop.

   **What is unresolved is what the word then MEANS.** Three things
   currently lean on it and each would need re-pointing: the receipt
   (one per delivery today, one per file after), `REQ-PIPE-059`'s hold
   (defined "within ONE arrival", which may become unreachable - see
   `REQ-PIPE-105`'s own open questions), and `REQ-PIPE-077`'s
   mixed-period gate (whose whole premise is that a delivery is a unit
   that can span periods).

   Worth deciding explicitly rather than by accident: is "delivery"
   retired as a concept, or does it survive as a *grouping* that
   carries no completeness claim - a label on a set of arrivals rather
   than a thing that has to be finished?

2. **[todo, 2026-10-01]** **[Pipeline & publishing]** Zip file support.

   **Nothing in this system understands an archive.** Checked
   2026-09-30: neither `docs/delivery-format.md`,
   `contract/data-asset.yaml`, `delivery.py` nor
   `arrival_patterns.py` mentions zip, tar or any container, and every
   arrival pattern matches a bare `.csv`. A zip arriving today matches
   no dataset and is reported as an unrecognised artefact - which is
   at least honest, but it is not support.

   **Why it is more interesting than a format convenience.** A zip is
   the one thing that gives an atomic multi-file boundary a transport
   can actually guarantee: our storage either took the object or it
   did not, so "the whole package arrived" needs no signal, no
   counter and no timeout. It is `REQ-PIPE-105`'s completeness problem
   solved by the supplier's own packaging rather than by us inferring
   anything. It also restores a case for `REQ-PIPE-059`'s hold, which
   may otherwise have no producer once every file is its own arrival.

   **KEITH, 2026-10-01: this is a batch of work rather than a flag** -
   either one large requirement or a few together, and he wants the
   ADJUSTMENTS tracked alongside the feature rather than discovered
   during it. What it touches, from this conversation: arrival
   patterns (which match a bare `.csv` today), the receipt instant and
   which object owns it, `Arrival.held` and REQ-PIPE-059's whole case
   (#10), the bundling RULE that #5 and #7 both want to lean on, and
   a real security surface he explicitly agreed needs dealing with.

   **Questions to settle**: whether the zip or its members get the
   receipt instant; whether a member is an arrival or the zip is;
   whether the arrival patterns match member names, the archive name,
   or both; what happens to a zip carrying files for two collections
   (a delivery may already span collections, settled 2026-09-24); and
   the security surface, which is real - zip bombs, path traversal on
   extraction, and a member whose name is potentially identifying
   before anything is read.

3. **[investigate, 2026-10-01]** **[Pipeline & publishing]** An
   "upload beginning" / "upload complete" signal from suppliers who
   automate.

   **Keith's framing, 2026-10-01**: suppliers who automate their
   uploads could bracket a batch with signals either side - which he
   noted might just BE zipping the package, or might need to allow
   several files or zips between the two signals.

   **This reopens something `REQ-PIPE-105` explicitly rejected**, and
   the difference is worth being precise about rather than assuming it
   is either the same idea or a new one. What was rejected was a
   supplier-written COMPLETION MARKER, and the reason was an unbounded
   wait: a signal that never comes leaves a real supply sitting
   unQA'd, unreported, with nothing to say it is stuck. The DynamoDB
   counter was rejected for the identical failure one door along - a
   genuine five-of-six partial never completes.

   **A bracketed session is a different shape from a marker**, and
   might survive the same objection: an OPENING signal means we know a
   batch is in flight from the start, so a batch that never closes is
   VISIBLE rather than silent. That is the whole difference. The marker
   had no opening signal, so a delivery that never finished was
   indistinguishable from one that never started.

   **So the question is not "should suppliers signal" but "what do we
   do when the closing signal never arrives"** - and it has to be
   answered before this is worth building. A session that can be
   reported as open-and-stale is a queue item somebody drains; one
   that cannot is the same dead end under a new name. Note
   `in_flight_log` already reports a delivery present with no receipt
   record, which is a thin version of exactly this.

   **Also unresolved**: whether a session is per supplier, per
   collection or per asset; what an overlapping pair of sessions
   means; and whether the signals are files, API calls, or S3 object
   tags. Keith's own instinct that "it could just be a zip" is worth
   taking seriously as the cheap answer that needs no protocol at all.

4. **[todo, 2026-10-01]** **[Pipeline & publishing]** Data moving out
   of the place it was uploaded to.

   Today `data/deliveries/` accumulates and nothing ever removes it.
   CLAUDE.md already flags it, with `data/receipts/`, as arguably
   state that ought not live in the repository - `REQ-PIPE-104` and
   `REQ-PIPE-105` own the filing and receipt records, and the
   supplier's own files are the part with no home yet.

   **It has already bitten once.** Twenty-six `handfiled-*` directories
   left behind by a CLI test became REAL RUNS, two of them captured
   into a committed characterisation fixture - so a landing zone that
   nobody clears is not just untidy, it changes what the pipeline
   thinks arrived.

   **The real questions are retention and reach**, and they are
   governance rather than plumbing: does the raw supplier file survive
   staging at all, and for how long; who can read the landing zone
   once the data is in the warehouse; and what the answer is for a
   Child Protection extract specifically, where a FILENAME is
   potentially identifying before anything is opened (`arrivals.py`
   already states that rule for unmatched files).

   A separate, smaller thread: once a supply is promoted its staged
   table MOVES rather than being copied (`REQ-PIPE-075`), and the same
   reasoning arguably applies one layer up - the landing zone should
   empty as things are taken from it, rather than being swept on a
   schedule nobody remembers to run.

5. **[investigate, 2026-10-01]** **[QA checks & contract]** The
   cross-table flicker, if files arrive one by one.

   `REQ-PIPE-105`'s own NFR 1 already names it: during the minutes a
   delivery is landing, a viewer can see a cross-table check red for a
   table that has not arrived yet. Criterion 13 is what keeps it
   legible rather than merely loud, and `REQ-QAC-037` criterion 4
   re-evaluates a cross-table check whenever a dataset it reads
   receives an arrival, so the reds are transient by construction.

   **It is smaller than it first sounds**, and the correction is
   recorded on 105: because a run reads the one version staged for the
   PERIOD rather than only its own arrival, the run triggered by the
   last file of a six-file delivery sees all six and resolves
   normally, with nothing promoted at all.

   **What is left is a display question more than a pipeline one.**
   Options worth weighing: let it flicker and label the reason
   (criterion 13's line); render "not yet evaluated" as its own state
   rather than as red, which is REQ-PIPE-115's territory and probably
   the same mechanism; suppress re-evaluation until a batch is known
   complete, which needs #3 and inherits its unbounded-wait problem;
   or simply do not publish a dashboard build mid-batch, which is free
   and may be enough.

   The thing to avoid is stated already and is the reason this is not
   cosmetic: a dashboard red for reasons about our own timing rather
   than about the data is how people learn to ignore red.

   **AND KEITH RAISED THE STAKE THAT SETTLES IT, 2026-10-01: under
   full automation a red SENDS EMAILS AND SMS.** A transient red is
   then not a display blemish, it is a false alarm waking somebody up
   - and a false alarm is how an alerting channel gets muted, which
   costs the real alert later. So "let it flicker and label it" drops
   off the list of acceptable answers.

   **His direction**: require any delivery whose tables take part in
   cross-table checks (#11 is the map) to arrive as ONE arrival -
   bracketed by markers (#3) or as a zip (#2) - so there is one QA run
   and no intermediate state exists to alarm on.

   **DOES BUNDLING SOLVE IT? PARTLY, AND IT IS NOT THE MAIN ANSWER**
   (Keith asked, 2026-10-01). It closes exactly one cause - the
   partial arrival - and leaves four standing:
   - **Nothing promoted yet**, early in a period or for a new dataset.
     Red regardless of how the files arrived.
   - **A held or contested table**, red because nobody has decided,
     which no transport rule touches.
   - **A supplier who does not comply.** The rule binds the ones who
     adopt it, and a supplier trickling files is the least likely to.
   - **A cross-PERIOD dependency**, where a check reads an earlier
     period through a declared temporal reference.

   **THE REAL ANSWER IS ALREADY BUILT, and it is REQ-PIPE-079's
   decision layer.** Criteria 14, 15 and 16 exist for precisely this:
   a table with no promoted supply whose slot is NOT YET DUE is not
   red at all; one whose slot is PAST DUE is red and says "overdue";
   one with a supply staged awaiting a decision is red and says so.
   Three different reds for three different people to act on, and one
   case that stops being red entirely.

   **So the alerting rule should key on the READINESS REASON rather
   than on the colour** - which makes most of the false positives
   disappear with no supplier rule at all, and is available the moment
   079's wiring lands. Bundling then narrows the residual window
   rather than carrying the whole load, and a rule suppliers must
   follow gets bought for a smaller, honest reason.

   Still worth costing separately, and independent of both: alerting
   on a SETTLED verdict rather than on every evaluation.

   **TWO FACTS KEITH ASKED FOR DIRECTLY, 2026-10-02, and both are
   better news than the discussion implied.**

   **BUNDLING IS NOT WRITTEN UP ANYWHERE - it is not a requirement,
   not a criterion, and nothing is built.** Checked against the whole
   register: no acceptance criterion mentions a zip, an archive, a
   delivery-start or delivery-end marker, or an upload-complete
   signal. He was right not to remember discussing it. It is HIS OWN
   idea from the 2026-10-01 conversation, it lives only in this file
   (#2, #3 and here), and it is a proposal rather than a plan.

   **AND NO, TRICKLING WOULD NOT FIRE REPEATED ALERTS - today, and
   structurally rather than by luck.** Two reasons, both already
   decided:
   - **There is no email or SMS alerting at all.** The only
     notification path that exists is GitHub tickets.
   - **Tickets are per SLOT and RECONCILED, never per check result
     and never reactive.** `ticket_reconciler`'s own first line is
     "One ticket per slot, reconciled to its current state", and its
     governing rule is "RECONCILE, NEVER REACT - every pass computes
     where each slot IS and makes the ticket say that. Running it
     twice over an unchanged world changes nothing." On top of that,
     `REQ-GHUB-109` is post-on-change.
   - **And a slot's state does not depend on a check verdict at all** -
     verified, `slot_state.py` reads the decision log, the filings and
     the clock, and never a check result. So a cross-table check going
     transiently red cannot move a slot, cannot change a ticket, and
     cannot raise anything.

   **WHAT WOULD FLICKER IS THE DASHBOARD**, because a dataset's status
   rolls up its check results - so a viewer watching during the ten
   minutes sees colour move. That is a display question, and the
   readiness distinction above is what makes it legible.

   **AND THE PARAGRAPH THAT USED TO SIT HERE WAS WRONG - CORRECTED
   2026-10-02, Keith caught it.** It claimed that an alerting layer
   keyed on SLOT STATE would inherit the ticket design's answer and
   have the problem solved before it was built. It would not, and the
   reason is one step removed from where this was looking.

   "`slot_state.py` never reads a check result" is TRUE AND
   IRRELEVANT. The red does not move the slot directly - it moves the
   slot by BLOCKING THE PROMOTION THAT WOULD HAVE MOVED IT. Traced
   through the real code:
   - a cross-table check reading an absent table goes red;
   - `promotion.status_of()` counts it against the READING dataset,
     explicitly and by design - "a CROSS-TABLE check filed under
     another dataset that declares it reads one of this dataset's
     tables... belongs to both";
   - `should_promote()` then refuses, because the status is red rather
     than green or amber;
   - so the slot stays `awaiting-decision` instead of becoming
     `promoted`, and the reconciler quite correctly raises a ticket
     saying somebody is needed.

   A transient red therefore DOES produce a ticket, and under
   automation would produce an alert. Keith's own words: "as soon as
   it goes red, it will trigger an email or an SMS".

   **ONE THING THE SLOT-KEYED DESIGN STILL BUYS, and it is worth
   keeping for it rather than for what was claimed: VOLUME.** Keyed on
   check results, thirty cross-table checks going red is thirty
   alerts. Keyed on slot state, it is ONE - the dataset's slot needs a
   person. That bounds the blast radius and it does not stop the alarm
   going off.

   **WHICH PUTS BUNDLING BACK AS A REAL ANSWER rather than a deflated
   one.** The earlier conclusion here - that 079's readiness
   distinction mostly solved this and bundling only narrowed a
   residual window - rested on the wrong claim above. The readiness
   distinction is still worth having and still makes a red legible;
   it does not prevent the promotion being blocked. So the live
   options are genuinely: bundle the arrival (#2, #3), alert on a
   SETTLED verdict rather than on every evaluation, or hold alerting
   until a period's arrivals are judged complete - which is the
   completeness problem again, from the alerting side.

   **IN TODAY'S BATCH PIPELINE IT STILL WOULD NOT FLAP**, which is
   worth separating from the above so nobody reads a present-tense
   bug into it: `ticket_reconciler` runs ONCE at the end of
   `run_manifest`, after every arrival has been processed, so the
   intermediate states are never reconciled. It is the EVENT-DRIVEN
   shape - one run per arrival, reconcile after each - where every
   intermediate state becomes a ticket and then an alert.

6. **[investigate, 2026-10-01]** **[Pipeline & publishing]** Parquet
   support for uploads - and no, one file cannot hold several tables.

   **The direct answer to Keith's question**: a single Parquet file is
   ONE table - one schema, one set of row groups. There is no
   multi-table Parquet file. What people mean by "a Parquet dataset"
   is a DIRECTORY of files sharing a schema, usually partitioned,
   which is several files again rather than one. Formats that do hold
   several tables in one file are a different family: a DuckDB
   database file, SQLite, or HDF5 - and a zip of Parquets, which is
   #2 rather than this.

   **Worth wanting anyway**, for reasons that have nothing to do with
   bundling: the schema travels WITH the data, so column types stop
   being something the loader infers and gets wrong. This project has
   already been bitten by CSV's typelessness - `csv_io.py` exists to
   carry explicit nulls through a read, and the `"N/A"`-becomes-NULL
   bug is in this repo's own history. Parquet would make a whole class
   of that go away, and DuckDB reads it natively so the staging path
   would barely change.

   **What it would cost**: arrival patterns currently match `\.csv`;
   `dirty.py`'s injected defects assume text; and a supplier sending
   Parquet is asserting a schema, which raises an interesting question
   for the contract - is a file whose declared types disagree with the
   ODCS contract a failed load, or a check result? Probably the
   latter, and probably a good check to have.

7. **[todo, 2026-10-01]** **[Pipeline & publishing]** THE RACE:
   promotion physically MOVES a table out of staging while another
   run may be reading it.

   **Keith's own find, 2026-10-01**, and it is the sharpest consequence
   of six runs where there was one. Promotion is `ALTER TABLE ... SET
   SCHEMA` - the table LEAVES staging. So with six files trickling in
   over ten minutes, each triggering its own run: run 4 resolves
   `cp_clients` to the staged table, and run 3's promotion moves that
   same table into the period schema partway through. The view
   underneath run 4 is now pointing at something that is not there.

   **AND THE EXPERIMENT SAYS IT DOES NOT BREAK - CORRECTED
   2026-10-01, the same day this item was written.** The paragraph
   above was reasoned rather than tested, and testing it against a
   real PostgreSQL changes the conclusion: **a view binds to its table
   by OID, not by name, so moving the table's schema MOVES THE VIEW
   WITH IT.** Measured - a view over `stg_probe.cp_clients__2026`
   returned 2 rows, the table was `ALTER TABLE ... SET SCHEMA`'d into
   another schema, and the view returned 2 rows still, with
   `pg_get_viewdef` rewriting itself to name the new schema. The run
   goes on reading the same physical table; it has simply moved house.

   **WHAT SURVIVES THE CORRECTION, because it is not nothing:**
   - **Lock contention, not a wrong answer.** `SET SCHEMA` takes an
     ACCESS EXCLUSIVE lock, so a promotion waits behind a running
     query and a long QA run can hold one up - a latency and deadlock
     question rather than a correctness one, and the kind this project
     already has a diagnostic recipe for (CLAUDE.md's `log_lock_waits`
     note).
   - **A provenance wrinkle.** The run records that it read
     `staging.<table>`, and by the time anybody looks, that table is
     in a period schema. Same table, same OID, same rows - so "what
     did this run read" is still answerable, but the schema-qualified
     name in the record has gone stale.
   - **The semantic oddity.** Run 4 resolved the table as a STAGED
     candidate and, by the time its tools executed, that supply had
     been promoted. The verdict is identical because the rows are, so
     this is about what the record MEANS rather than whether it is
     right.

   **IS THE LOCK CONTENTION SOLVED BY REQ-PIPE-079? NO - AND IT IS
   NOT LIVE TODAY EITHER** (Keith asked, 2026-10-01). Two separate
   facts, and both are worth having rather than the reassuring half.

   079 changes WHAT a run reads, never WHEN a promotion happens, so it
   neither fixes nor worsens this. If anything it enlarges the lock
   surface slightly - a run now touches the period's promoted tables
   as well as its own staged candidate - while making more of what it
   reads STABLE, since a promoted table does not move again unless
   somebody demotes or re-files it.

   **It cannot happen today, and the reason is structural rather than
   lucky.** `parallel_orchestrate.run_manifest()` FORCES SEQUENTIAL
   EXECUTION whenever `before_each`/`after_each` are passed, which is
   exactly how the orchestrators wire filing and promotion. So within
   a collection it is strictly file -> run -> promote, one arrival at
   a time, and a promotion can never overlap a QA run. Across
   collections the tables are disjoint, so there is nothing to
   contend for.

   **IT IS A THING TO SOLVE FOR REAL - Keith, 2026-10-02**, and it
   comes with automation but NOT only with it.

   **TWO HUMANS CAN CAUSE IT, which he pointed out and this file had
   wrong.** The serialisation above is WITHIN ONE ORCHESTRATOR
   PROCESS: `run_manifest` chains file, run and promote for the
   arrivals in its own manifest. It says nothing about two people
   running `mothman cp qa` against the same dataset at the same time,
   which are two processes with nothing between them. So "humans will
   not trigger it" was wrong, and the honest statement is that
   automation makes it ROUTINE rather than making it possible. **It becomes live the moment arrivals are
   processed CONCURRENTLY**: the trickle scenario in #1, and the
   event-driven AWS MVP where each object's arrival fires its own
   handler with nothing serialising them.

   So this is OPEN WORK rather than an observation - it needs a real
   answer before the automation side ships, and it is not a blocker
   for `REQ-PIPE-079`. The candidates, in rough order of how much they
   cost: a repeatable-read transaction for the duration of a run; an
   advisory lock per dataset held across promote; a statement timeout
   on the promotion so it backs off rather than queueing behind a long
   run; or accepting the wait and only MEASURING it, since a blocked
   promotion is correct, just slow. Worth costing properly rather than
   picking - and note the first two are the ones that also answer the
   provenance wrinkle above, because they fix WHEN rather than
   patching WHAT gets recorded.

   **SO THE BUNDLING RULE IS NOT NEEDED FOR CORRECTNESS**, which is
   the part that matters for #2, #3 and #5. It is still wanted for the
   alerting reason in #5 - transient reds firing emails and SMS - and
   that argument stands on its own feet without this one. Worth
   keeping the distinction: a rule suppliers must follow is expensive,
   and it should be bought for the reason that actually needs it.

   **HIS PROPOSED RESOLUTION, and he reasoned himself into it in one
   pass**: require any delivery carrying tables that participate in
   CROSS-TABLE checks to arrive either bracketed by delivery-start and
   delivery-end markers (#3) or as a single zip (#2), so the whole set
   is ONE QA run. He then checked it against himself and it holds - in
   a single run over all six Child Protection tables, if the first were
   already promoted, that table resolves to its promoted version and
   the rest to staging, which is exactly what criterion 5 of
   `REQ-PIPE-105` already specifies. One run, one consistent read.

   **What still needs deciding rather than assuming.** A single run
   narrows the window; it does not close it, because a run still holds
   its resolution across the four tools and a promotion from some other
   collection's run could still land inside it. The database has real
   answers here that are worth costing before a policy is written - a
   repeatable-read transaction for the duration of a run, or an
   advisory lock per dataset around promote, or resolving views against
   a snapshot rather than live names. Code may be the cheaper fix than
   a rule suppliers have to follow.

   Note what makes this tractable at all: a run already records which
   physical table it read (`Resolution`, REQ-PIPE-068 criterion 5), so
   "did this run read something that has since moved" is answerable
   after the fact even before it is preventable.

8. **[todo, 2026-10-01]** **[Pipeline & publishing]** Guardrails when
   promoting into a slot something else DEPENDS on.

   **Keith, 2026-10-01.** A period can resolve to an earlier period's
   supply by INHERITANCE (nothing was owed) or by SUBSTITUTION (a
   person decided). Promoting a new supply into that earlier slot
   changes what those later periods stand on, and today nothing warns.

   **His MVP**: warn the operator and require them to de-inherit or
   de-substitute BEFORE the promotion is allowed. **His preferred end
   state**: warn, let them continue if they choose, and then offer to
   RE-POINT the inheriting or substituting periods at the newly
   promoted table.

   Worth knowing before building either: the decision log already
   refuses to let a supply MOVE while a later period stands on it
   (`REQ-PIPE-084` criterion 11, judged in `decision_log._judge` for
   reject, demote and re-file, and it names every blocking period with
   the right remedy per period). So the machinery for "what stands on
   this" exists and is tested; what is missing is the same question
   asked of a PROMOTION rather than a move, and the re-pointing offer.

9. **[todo, 2026-10-01]** **[Testing & dev tooling]** Model the
   off-cycle partial-participation supply end to end, as a real test
   case with tests.

   **Keith's own ask, 2026-10-01**: take a partial-participation
   dataset arriving off schedule and walk the whole thing, so the model
   is shown to work rather than argued to work. Both operator paths,
   because they end somewhere different:

   - **Treat it as an off-schedule supply for the CURRENT period**:
     un-inherit that period, promote the supply into it, done.
   - **Treat it as a resupply of its own designated period**: promote
     it there (a supersession, so the log requires a reason), then
     un-inherit the later period and re-inherit it onto the new table.

   Both belong in `plans/supply-model.md`'s own test scenario register
   as numbered scenarios, not only as unit tests - that register is
   what `REQ-GEN-044` generates real history against, and a scenario
   that exists only as a test never appears on the dashboard where
   somebody could look at it.

   This is also where #8's guardrail gets exercised for real: the
   second path promotes into a slot a later period is standing on,
   which is precisely the case that should warn.

10. **[todo, 2026-10-01]** **[Pipeline & publishing]** Work through
    `REQ-PIPE-105`'s three open questions here rather than in the
    register.

    Keith's own call, 2026-10-01 - they are transport questions and
    this is the transport file. Recorded on the requirement
    2026-09-30 and repeated here so they are worked rather than
    filed:

    - **Is `REQ-PIPE-059`'s hold reachable after criterion 1?** The
      hold is defined "within ONE arrival"; criterion 1 says every
      arriving FILE is its own arrival; `Arrival.held` is the datasets
      where more than one file matched, which under one file per
      arrival can never be non-empty. **Keith, 2026-10-01: he does not
      follow the question yet and expects it to be puzzle-able.** It
      probably dissolves the moment #2 lands - a zip restores an
      arrival that can hold several files, and that is the only shape
      where "two files, nothing to tell them apart" can occur.
    - **Nothing understands an archive.** #2.
    - **The packaging decides the outcome** - two files claiming one
      dataset are held when bundled and not when separate.

11. **[todo, 2026-10-01]** **[QA checks & contract]** The dependency
    map: there are TWO classes of cross-table check, not one.

    **Keith asked, 2026-10-01, whether referential integrity is the
    only kind. It is not** - counted from the real declarations
    (`tables_read.declared_by_check_id`), 30 checks read a table other
    than their own:

    - **21 REFERENTIAL INTEGRITY** - 7 foreign keys, each implemented
      three times (dbt `relationships`, Soda `values in ... must exist
      in`, and the ODCS contract). "Does this id exist over there."
    - **9 CROSS-TABLE BUSINESS RULES** - 3 rules, each implemented
      three times, and these are the second class he remembered. They
      are claims about the STATE of a row given a row in another
      table, which is a different thing from existence:
      - *escalation_completeness* - every notification escalated to an
        investigation must have that investigation recorded
        (notifications ← investigations)
      - *closed_case_investigation_hygiene* - an investigation must not
        still be open once its client's case has been closed
        (investigations ← clients)
      - *placement_carer_approval* - a placement's carer must hold an
        approved status (placements ← carers)

    **AND A THIRD KIND OF DEPENDENCY THAT IS NOT CROSS-TABLE AT ALL**,
    worth naming here because it has the same exposure to #7 and gets
    forgotten: Evidently's drift checks compare a supply against a
    REFERENCE RUN - another period's data. The dependency runs across
    TIME rather than across tables, so a promotion that changes what a
    period resolves to can change a drift verdict without any table in
    this run moving.

    Why this belongs in a transport file: #7's race, #5's flicker and
    #2's bundling rule all need to know WHICH tables depend on which,
    and the answer is a real, queryable declaration rather than a
    guess. Any rule of the form "tables in a cross-table relationship
    must arrive together" is defined by this map.

12. **[todo, 2026-10-02]** **[Pipeline & publishing]** A way to UNDO a
    QA run - take its results out of the reporting.

    **Keith's own idea, 2026-10-02**, arrived at from the lock
    contention above: if two people can run QA against the same
    dataset at once, a person can also simply make a mistake - run the
    wrong file, run against the wrong period, run a trial they meant
    to throw away - and there is currently no way to take the results
    back out.

    **What exists today and why it is not enough.** `mothman supply
    tidy` clears orphaned SCHEMAS, not recorded runs. Deleting a
    delivery directory does NOT remove its run: CLAUDE.md records the
    real incident where two orphaned Child Protection runs survived
    both a directory deletion and a `--force` bootstrap, went on
    feeding the dashboard, and broke a committed golden fixture - the
    check is a query comparing `qa.run` against what
    `arrivals.arrivals_for()` recognises, and there is no command for
    it.

    **The hard part is not deletion, it is what deletion MEANS.** A
    run's results are evidence about a moment, and this project's
    whole stance is that recorded history is not rewritten - the
    decision log is append-only by a database trigger for exactly that
    reason. So the likely shape is WITHDRAWN rather than DELETED: the
    run stays, carrying who withdrew it and why, and every reader -
    dashboard, promotion gate, tickets, the activity feed - excludes
    it. That is the same move `check_lifecycle` already makes for a
    retired check, and the same reasoning the reconciler uses for
    never closing a ticket.

    **Questions it raises**: whether a withdrawal cascades to a
    PROMOTION the withdrawn run justified (it must, or the warehouse
    holds a supply promoted on evidence nobody stands behind); whether
    an operator can withdraw a run a decision now depends on at all,
    or has to undo the decision first, which is REQ-PIPE-084 criterion
    11's shape; and whether this is the same mechanism as a trial
    (REQ-PIPE-103) seen from the other end - a trial is a run that was
    never going to count, and this is one that stopped counting.
