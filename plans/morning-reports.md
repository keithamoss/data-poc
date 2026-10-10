# Morning reports

What happened on each night Keith left the build running unattended:
the plan he approved before going to bed, his standing terms for the
night, what each sprint built and committed, every PROVISIONAL choice
taken on his "take the recommended option" rule, and the questions left
for him in the morning - with his answers recorded under them as he gives
them.

Split out of `plans/road-testing.md` on 2026-10-06 at Keith's own ask. It
had been written inside that file's entry #16 because the first overnight
plan grew out of that entry's sign-off rounds, but it is a log of runs,
not a sighting, and it had become more than a third of the file.

A NEW OVERNIGHT RUN WRITES ITS REPORT HERE, as a new numbered entry, in
the same order: plan and terms first, then a line per sprint as it lands,
then the questions. A report is a record of what was done and decided -
anything still to BUILD lives in `requirements.yaml` and the other plans
files, never only here.

Same conventions as the other numbered-item plans files: a closed status,
one or more component tags, and a date.

1. **[done, 2026-10-04]** **[Docs & process]** **Overnight 2026-10-04 to
   05: sprints 1 to 12 of the signed backlog.**

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
        KEITH, 2026-10-06 midday: "why can't we just make the synthetic
        data record dates properly?" - so a replay on a synthetic asset
        stamps decisions, and (his "and the other stamps too") filings,
        load outcomes and runs, from the replay's simulated clock, and c6
        uses the plain rule. D2: the pill is the newest result (built).
        REQ-PIPE-140 c5's terminal half: amended away (no terminal reader
        of verdicts exists).
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

2. **[done, 2026-10-05]** **[Docs & process]** **Overnight 2026-10-05 to
   06: sprints 13 and 14, the critics' findings and Keith's morning
   answers.**

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
        KEITH'S ANSWERS, 2026-10-06 morning (all six as recommended):
        Q1 exit 2 - ticket reconciliation that fails is a failed stage.
        Q2 same run id - c8 gains an explicit exception: an incomplete
        run's results were never visible, so replacing them replaces
        nothing anyone saw. Q3 hold back - a locked arrival holds back
        later arrivals of its own collection, as a failure does. Q4 keep
        the rest and NAME each file left behind. Q5 delete
        backlog.unprocessed. Q6 the criterion wins - a trial's run and
        its check results are discarded with everything else.
      - KEITH'S ANSWERS TO THE STANDING PROVISIONALS, 2026-10-06 morning
        (asked while 96813c1's gate ran):
        - CHANGED: a database's identity moves from database-level settings
          to a TABLE in the qa schema (REQ-PIPE-107's provisional, over
          keeping settings). Follow-ups: `env reset-synthetic` KEEPS the
          identity row; the table lives in the qa schema itself (over its
          own owner-only schema), so anything that can write QA history can
          relabel it - accepted. To scope as an amendment to REQ-PIPE-107.
        - CHANGED: the kept-run report's inheritance lines come from a
          RECORDED LINK (each inherit entry names the arrival whose
          processing caused it), over the time window (REQ-TEST-150 c6's
          provisional). A schema change.
        - KEPT as built: `env mark --confirm` counts as typing for an
          unmarked database only; the environment is named at a command's
          first connection; the pass stages every unchecked arrival first;
          a recorded arrival picked to keep is refused with --trial
          (REQ-PIPE-086 c7).
        - #119 D2: `supply tidy` and `supply discard-sample` need
          production's typed id, and --yes cannot skip it.
        - #119 D10: in production the typed id REPLACES hand-filing's
          "Keep this check?" y/N; elsewhere the y/N stays.
        - #118 D-E: a first line is a header only if it names a contract
          column, repeats no name, and has no field shaped like a value of
          its column's type; missing columns stay the data checks' job.
        - #117 D1: someone not in people.yaml is still SHOWN BY THEIR
          RECORDED IDENTITY (email) - Keith kept today's behaviour, over
          "someone not on the people list" and refusing their action.
        - #117 D7: a re-check's promotion is stamped when it ran in a live
          deployment, at its cause instant only in a scripted replay.
        - #117 D6: one definition of a supply's current run - asset time,
          everywhere.
        - #117 D5: a replayed rule promotion's invented lag is capped at the
          next arrival of the same dataset.
        ALL EIGHT BUILT 2026-10-06 (qa schema 31; decisions recorded on
        REQ-PIPE-107, 093, 140, 081, 147, REQ-QAC-096, REQ-TEST-150). Two
        departures from the option wording, both in the decisions: the header
        rule does not refuse a REPEATED name (header_names_unique could never
        fail if it did), and it is type-free rather than per column type. D7's
        "live: when it ran, replay: the cause" is one rule with no replay flag
        (decision_log.follows), and knock-on re-evaluations use it too.
        THEN, in this order:
        REQ-TEST-117 (CI reuses a bootstrapped database), then REQ-PIPE-152
        (the S3 Lambda handlers).

3. **[in-progress, 2026-10-10]** **[Docs & process]** **Overnight 2026-10-10 to
   11: two built-code defects, the excuse, the versioned timezone, the asset
   manager, CI's cached bootstrap - and REQ-PIPE-110 signed.**

      - THE PLAN, AGREED 23:00-23:30 PERTH, in order:
        1. post-build-review #136 - a claim on each owed re-check, so no two
           runners run the same one (REQ-PIPE-163 criterion 31's rule, built
           for the code that exists today).
        2. post-build-review #135 - a group whose every dataset is left out of
           its rollup reads 'Not counted', never green. Only that half is
           reachable today; 'Turned off' waits for REQ-PIPE-179.
        3. REQ-PIPE-161 + REQ-DASH-162 - excusing a late supply, including the
           criterion Keith added tonight: an excuse does not bar the gate
           (plans/running-thoughts.md #78).
        4. REQ-PIPE-112 - the versioned timezone. Criterion 13 (the freeze)
           deferred to REQ-PIPE-111; the as-at lookup is built as the function
           REQ-PIPE-110's one loader later takes over.
        5. REQ-GHUB-171 - the people configuration names the data asset's
           manager.
        6. REQ-TEST-117 - CI reuses a bootstrapped database. Last, because each
           CI round trip is 15-30 minutes.
        If the queue finishes early: REQ-PIPE-110, signed tonight, pin first
        (NFR 3 and 4) - otherwise it is first next session.
      - KEITH'S TERMS (23:15), the same as overnight #2's: forks take the
        recommended option, marked PROVISIONAL and listed below; at most one
        full rebuild per item; my own dev and scratch database schemas may be
        upgraded in place, a shared or real one never; commit and push each
        finished item after the gate, CI checked at natural pauses; nothing
        unsigned is built, today's batch included. Post-build critics after
        each build, their fixes in before the next item.
      - SIGNED TONIGHT: REQ-PIPE-110, at Keith's choice not re-walked - he
        settled its open question (membership unversioned, #79), approved the
        amendment wording, and accepted the scoper's boundary fixes. The
        review batch's other ten requirements stay unsigned for a sign-off
        session.
      - ALSO SIGNED (23:28): REQ-PIPE-181, settled the same way - four
        amendment wordings approved (110 c33, 113 c2, 131 c2, 111 c4). With
        110 and 181 signed, the whole signed calendar chain is buildable in
        order; what stays unsigned is REQ-DASH-182 and the turn-off pair
        REQ-PIPE-179 / REQ-DASH-180, for a fresh sign-off session.
      - QUEUE REORDERED (Keith, 23:30, option B - calendar first): the two
        defects (#136, #135), then REQ-PIPE-112, then REQ-PIPE-110 with its
        behaviour-preserving pin FIRST, then REQ-PIPE-113 and REQ-PIPE-111 as
        far as the night goes. The excuse (161/162), REQ-GHUB-171 and
        REQ-TEST-117 move to the next night. Signing more of the calendar
        group would not have let more be built tonight - the limit is the
        build order, not sign-off.
      - #136 DONE: every runner of an owed re-check claims it first; a claimed
        one is skipped and stays owed. Failing test first. Written up in
        plans/post-build-review.md #136.
      - #135 DONE: a group whose every dataset is left out reads 'Not
        counted' with a line saying why, never green - both implementations
        and the shared status table. Two tests had pinned the false green as
        intended; they were turned into the failing tests. JS 576 tests and
        the e2e module (216, 6 minutes) green. Recorded on REQ-PIPE-106.
      - REQ-PIPE-112 BUILT (criterion 13 deferred to REQ-PIPE-111, as agreed):
        the timezone is effective-dated versions; every reader asks as at
        a date or an instant; a time daylight saving makes no instant or two
        is refused in the gate; the dashboard carries every version; the
        settings changelogs are structured. PROVEN by a full rebuild (9m51s,
        47 staged tables as before) and the arrival golden: no verdict or
        instant moved. ONE PROVISIONAL FOR YOU: the first version starts
        1970-01-01, so no date the system reads falls before every version.
        ONE CORRECTION: the implementation commit's message said 582 JS
        tests; the run said 581 - an added-up number, not a run. Recorded
        in the requirement's evidence.
      - REQ-PIPE-110 BUILT: contract/calendar.yaml holds the calendars, which
        calendar each collection and dataset is on, and each dataset's
        participation as dated versions; slaProperties is gone from both
        contracts and pipeline/cadence.py with it; delivery_months and
        owes_from are refused by name. One loader, one immutable value,
        passed to schedule, slots, the overlap gate and the builders. PINNED
        FIRST, and PROVEN by the night's one rebuild for it (587s, 47 staged
        tables) - the pin and the arrival golden unchanged. Full check: 4019
        passed, 2 failures of this change's own, both fixed. ONE DEFECT CAUGHT
        IN MY OWN REVIEW, fixed test-first: the dashboard's schedule-ended
        notice would have told you to edit data-asset.yaml. NOT YET PER
        PERIOD: expected time and grace still come from each dataset's newest
        participation version - every dataset has one, so nothing moves -
        and each period's own version is REQ-PIPE-113, next. Thread C stays
        until 113 is built, then goes whole.
      - A SLIP OF MINE ON 110, said plainly: I made the configFile fix after
        110's full run and re-ran only the fast gate and the targeted tests,
        so 9bc389e went out with two e2e tests still asserting the old file
        name - its commit message's "4019 passed" was true of the tree before
        that fix, not of the tree committed. Caught by the next full run and
        fixed in the 113 commit. The rule I broke is CLAUDE.md's "the last
        edit must come BEFORE the last gate run".
      - REQ-PIPE-113 BUILT: every slot takes its expected time, days before,
        grace and claim-window override from the participation version in
        force on its own period's date, through one slot-instants function
        that filing, the overlap gate and the daylight-saving gate all call;
        a new `days_before` (whole days) expresses "due the evening before";
        every horizon reaches past the largest one; one bisecting "in force
        on" helper now serves participation, calendar and timezone versions.
        No rebuild - the pin proves nothing moved for today's one-version
        agreement. ONE PROVISIONAL: a calendar period before a dataset's
        first participation version takes that first version's inputs, so
        the slot before it still has something to close against.
        ONE QUESTION FOR YOU (wording of a built requirement, so yours):
        REQ-PIPE-052 criterion 4 still says a slot's grace is "taken from its
        own dataset's contract". 113 required amending criterion 3 only.
        Proposed: "THE SYSTEM SHALL give each slot its own grace allowance,
        taken from its dataset's participation version in force on that
        period's date." Not applied until you say.
      - REQ-PIPE-110 CRITIC came back with real findings (saved in the
        session's reviews/2026-10-11-critic-110.md): a dataset listed twice in
        calendar.yaml passes and the last one wins; criterion 7 is checked
        against the newest participation version only; a dataset missing
        from calendar.yaml whose collection names a calendar passes the
        participation checks; three mistakes raise tracebacks instead of
        gate errors; and weaker messages. All defects against signed
        criteria, so fixed without needing you: ten failing tests first,
        then the fixes - written up as plans/post-build-review.md #137. Two
        left for REQ-DASH-182 (unsigned): label shapes no calendar here has.
      - A TIMING TEST WENT RED ONCE, NOT MINE: tests/test_dbt_worker.py's
        `test_later_runs_reuse_the_parse` asserts a later dbt run is faster
        than the first, and under the full parallel suite one later run took
        7.7s against a 7.5s first. It passed twice alone (11/11 each). A
        wall-clock assertion on a loaded 4-core machine; I have not changed
        it. Worth deciding whether it should compare something the parse
        reuse actually controls (a counter, a manifest mtime) instead.
      - REQ-PIPE-113 CRITIC: four real defects, all fixed test-first
        (plans/post-build-review.md #138) - the claim reach used the current
        rather than the widest claim window, a sub-day window fell off the
        reach at midnight, a period before the first version mixed its
        inputs, and the daylight-saving gate missed non-owed periods. Latent
        today (one version each, Perth has no daylight saving), real the day
        either changes. One left for REQ-DASH-182: the delivery-time label
        ignores days_before.
      - REQ-PIPE-111 BUILT (three halves deferred, below): once an item of
        the agreement could govern a filing - a date, a calendar or
        participation version, a not_expected entry, a timezone version - it
        changes only by a declared correction appended to its owner's
        `corrections:` list, naming change reference, date, author, approver,
        reason and each item's old and new value, and matching what the file
        actually did. The refusal is a paste-ready correction block naming
        who may approve. Next year's dates appended late need no ceremony
        unless they would move a filed supply; a synthetic asset may add
        past-dated versions. REQ-PIPE-050's "any changelog line clears it"
        guard is gone. Inside the pre-commit hook the gate compares the staged
        file with HEAD. And REQ-PIPE-122's settings guard dates by the committer, not
        the backdatable author (post-build-review #139; 122 c7 amended as 111
        decision 28 said).
        THREE PROVISIONALS FOR YOU: (1) who may approve - a real person in
        people.yaml with the MANAGER role (the criterion says only "allowed
        to approve"); (2) the item syntax a correction names, e.g.
        `calendar quarterly version 2023-01-01 date 2024-Q1`; (3) an
        uncommitted change (the hook) is dated "now".
        DEFERRED, recorded as unmet: the CODEOWNERS half of the approver
        check (REQ-GHUB-174 creates the file - none exists), naming the
        impact preview command (REQ-PIPE-169), and collection defaults
        (REQ-PIPE-181). REQ-PIPE-112's criterion 13 is now half met - the
        freeze is built; re-judge, preview and backstop wait on 168/169/173.
        THREAD C IS NOT DELETED: 110-113 are built, but REQ-PIPE-179/180/181
        and REQ-DASH-182 came out of the same thread and are unbuilt, so by
        CLAUDE.md's rule 4 it goes whole only after them.
