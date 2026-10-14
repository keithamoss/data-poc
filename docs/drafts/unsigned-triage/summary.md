# Unsigned triage: the seven re-scoped (delivery-scoper, 2026-10-14)

Keith's decisions of 2026-10-14 (from the triage in `README.md` beside this file) applied. The full revised
requirements are in `requirements-draft.yaml` beside this file. **Every entry is a proposal: nothing is
signed, and none is described here as ready to build.** Each keeps its id; two new entries are split out:
**REQ-DASH-221** is REQ-DASH-175's re-check half (question 175-A), and **REQ-QAC-223** is REQ-QAC-176's
changelog-gate half (question 176-B). Confirm both numbers are still free before applying: the
road-testing-feedback draft already uses 219, 220 and 222, and the unjudged-cross-table draft uses 210 to 217.

**Keith's answers of 2026-10-14 afternoon are folded in** (all eight took the recommended option; see the
last section). Each is now a decision citing "Keith, 2026-10-14, <question id>", its open question is
gone, and its PROVISIONAL marks are removed.

**The three advisory reviews are folded in too** (delivery-architect, delivery-cli-ux, and the dashboard
UX review's findings on 166/175/221), with Keith's answers to their questions, all option A. See
**Reviews folded** near the end for what changed per requirement, **T12** for one new amendment to a
signed requirement, and **Ready for sign-off** for the build order and the few points still to confirm.

**Validation.** `uv run mothman dashboard validate-requirements --draft
docs/drafts/unsigned-triage/requirements-draft.yaml` reports 54 errors, all of the expected kind: a
dependency on a requirement that is in the register but not in the draft. There are no others. The drafts
were also merged into a copy of `requirements.yaml` (seven same-id entries replaced, REQ-DASH-221 and
REQ-QAC-223 appended), and that copy validates with **OK - 205 requirements, zero errors** (re-run after
the answers were folded in). **Re-run after the reviews were folded, 2026-10-14:** this draft alone still
reports 54 errors, every one "dependencies entry ... does not match any real requirement id in this
file"; both drafts merged into one copy of the register (the seven same-id unsigned entries replaced;
219, 220, 221, 222 and 223 appended) validate **OK - 208 requirements, zero errors**.

**Criterion numbers are kept wherever they could be.** Other records cite these criteria by number:
post-build-review #136 cites 164 c19 and 177 c16, REQ-PIPE-163's open question cites 164 c17, REQ-PIPE-177
c2 cites 176 c12, and the hold cites 176 c18. So no criterion of 164, 166, 176, 177 or 178 moves. 176's
seven criteria that moved to REQ-QAC-223 stay in place as `retired_criteria` (REQ-DOCS-143's mechanism,
`replaced_by: [REQ-QAC-223]`), so nothing after them renumbers. New ones are appended, and edits are made in place. 165 is
renumbered because it is a re-scope. 175 is renumbered because it is split; the mapping is a decision on
both halves.

## One correction to the triage, found in code

**REQ-PIPE-177 criterion 24 (the processing pass's deadline) is NOT met.** The triage counted it as met.
`processing_pass.run_pass` checks its deadline only before it takes a new *arrival* (processing_pass.py,
`out_of_time()` at the arrival loop). The pass's owed work is a single call to
`recheck.run_all_owed(kinds=(REEVALUATE, RECHECK))`, which takes no deadline and runs up to 1000 items. So
a Lambda pass with hundreds of owed bulk re-checks would run past its budget. The work is small, but it is
real, so c24 stays a criterion and a decision records why. The other two "already met" items do hold, and
are recorded as decisions, not new work:

- 164 c19 and 177 c16: `recheck.run`'s advisory-lock claim, tested by
  `tests/test_recheck.py::TestTwoRunnersNeverRunOneOwedItem`.

## Per requirement

### REQ-PIPE-164: re-check one supply (currency pass; 21 -> 24 criteria)

Checked against everything signed since it was drafted. What changed, and why:

- **c2**: the supply's tables are found through REQ-PIPE-193 c13's one resolver, which already lists
  `recheck`. The reason is that a settled pair leaves two supplies on one arrival key.
- **c10**: a held supply's refusal gives the hold's own responses for its label (REQ-PIPE-179 c18), as
  REQ-PIPE-163 c38 does for promote. "Naming place" was wrong for a schedule-ended hold.
- **c11, plus a new c22**: no re-check on a file of an open contested pair. REQ-PIPE-194 c4 offers only
  the settlement there, and the settlement checks each file anyway (REQ-PIPE-193 c21).
- **c13**: a promoted supply re-checked red names *acknowledge* as well as demote, because Keith's
  2026-10-10 decision made acknowledge the way to record that it stays.
- **c21**: cites REQ-PIPE-179 c23 (it counts whether or not the dataset is turned off), and pins the
  acknowledge amendment to REQ-PIPE-122 c14.
- **New c23**: refused while the agreement backstop refuses the dataset, consistent with
  REQ-PIPE-163 c35. Confirmed by Keith (164/177-A).
- **New c24**: a re-check records no new *arrival* verdict (REQ-PIPE-168). This requirement's "verdict" is
  the QA status, and the two meanings must not blur in the build.
- **New NFRs**: re-check is a new decision-log action, so every reader of the log has to be listed. The
  schema change is additive only, whichever way #89 goes.
- **Unchanged after checking**: REQ-PIPE-170 (corrections) and REQ-PIPE-161 (excuses). A re-check moves
  no filing, so neither is affected.
- **Amendments**: they now build on top of REQ-PIPE-163's approved ones (T1, T5, T6, T7 below). One
  thing worth knowing: REQ-PIPE-163 c24 *says* its 076 c7 amendment names re-check, but the wording you
  approved does not. 164 is where re-check gets added.

### REQ-GHUB-165: un-supersede and a parity test (re-scoped; 6 -> 6 criteria, rewritten)

- **c1** (kept): un-supersede is offered wherever `filing_decisions.apply` would accept it, meaning a
  superseded version exists and nothing else waits. It is read from recorded supersessions, the way
  `excuse_offers` reads punctuality.
- **c2 to c6**: the parity test. It covers every slot state, plus a held supply of each label (that is
  how REQ-PIPE-163 c10/c17's held listing gets tested), crossed with every operation. It fails where the
  flag route would append an entry the door does not offer. It takes its operations from
  `filing_decisions.OPERATIONS`, so re-check, the withdrawals and the bulk re-check join it without
  amending 165. A no-op does not count as accepted. A state with no example fails the test rather than
  passing on fewer states. A separate test checks that every `TERMINAL_ONLY` operation is refused on
  GitHub.
- **Recorded as decisions**:
  - Old c2 is already met: `filing_tui` lists `superseded_in` once un-supersede is chosen.
  - Old c3 is moot: an open pair offers only choose-file (REQ-PIPE-194 c4).
  - Old c4 is now REQ-PIPE-163 c10/c17.
  - Keep and the correction confirmation belong to REQ-PIPE-170, not to the slot door.
  - The test runs in one direction only, because what is offered is not the same as what is permitted.

### REQ-PIPE-166: withdraw a mark or an acknowledgement (currency pass; 8 -> 13 criteria)

- **c1**: both routes. Who may withdraw follows REQ-PIPE-161 c8's terms: the person who recorded it, or
  anyone on the allowlist. 166 said it mirrored 161 but never stated this.
- **c6**: where each withdrawal is offered.
  - withdraw-not-supplied is per period, beside substitute, on a not-supplied (accepted) slot.
  - withdraw-acknowledgement is on a promoted supply with a standing acknowledgement, read from the
    log as excuses are.
- **c7**: now also amends REQ-GHUB-082 c31 and c32, which list the per-period decisions.
- **New c9**: withdrawing an acknowledgement of a *re-checked* verdict (REQ-PIPE-164) puts the supply
  back under "Promoted, then re-checked".
- **New c10**: the prompt says the reason is published on the dashboard.
- **New c11**: the withdrawal is honoured in every reader. These were enumerated in code:
  - `qa_store`'s acknowledgement view
  - `pipeline/acknowledgements.py`
  - `pipeline/closed_slots.py`
  - `slot_state`
  - `filing_queue`
  - `not_supplied`
- **New c12 and c13**: the page half (confirmed by Keith, 166-A and 166-B). Without it the page goes on publishing a withdrawn
  acknowledgement as standing, because the template reads acknowledge entries directly.
- **No amendment to REQ-PIPE-076 c7 is needed**, and a decision says why: acknowledge already counts as
  a person's decision, and a mark names no supply.

### REQ-DASH-175 -> REQ-DASH-175 (placement) + REQ-DASH-221 (re-check): scoper pass

**Split, confirmed by Keith** (question 175-A). 175 keeps the placement half and its id, so REQ-PIPE-163's dependency
and amendment 2 still point at the right place. It can be built alongside REQ-PIPE-163. 221 takes the
re-check half and is built after REQ-PIPE-164 and REQ-PIPE-177.

- **Amendment 2** (the one you approved with REQ-PIPE-163) is carried word for word. It was criterion 12;
  after the split it is **criterion 7 of REQ-DASH-175**. It still says "re-checked"; that half is built
  and tested in 221's c7.
- **New in 175**:
  - **c3**: a resolved hold's row stays in the section that listed it while it was held.
  - **c9**: the rule's re-file from no period does not get the "Placed in" tag. This covers the
    schedule-ended drain, turned-off holds and `correction_apply._place`, all of which record actor_kind
    rule.
  - **c10**: a held contested pair placed whole (REQ-PIPE-163 c37) says so on the pair's row.
- **New in 221**:
  - **c7**: "re-checked" is added to `DECISION_DONE`.
  - **c9**: the amber re-checked tag sits where the red-promoted badge sits, before the turn-off marker
    (REQ-DASH-180 c13).
  - **c12**: counts whether or not the dataset is turned off (REQ-DASH-180 c6).
  - **c14**: amends **REQ-DASH-126** c1, c2 and c6. The old 175 c14 (the red-promoted badge "naming the
    re-check as the cause") contradicted signed REQ-DASH-126 as written. 126 defines red promoted from
    refreshed cross-table results and names only an arrival or a promotion as the cause.

### REQ-QAC-176 -> REQ-QAC-176 (stored fingerprint, HELD) + REQ-QAC-223 (changelog gate, signable now)

**Split by Keith, 2026-10-14 (176-B, option A).** The split line, by 176's criterion number:

| 176 criterion | What it says | Now |
|---|---|---|
| 1, 2 | record a fingerprint on every result; computed by the one writer, frozen defaults left out | 176 (c2 now says it extends REQ-QAC-223's widened writer) |
| 3 | expression or test type in the hash | **223 c1** |
| 4 | generic-test macro, singular SQL and the macros it names | **223 c2** |
| 5 | Evidently column, method, thresholds as CHECK_LIFECYCLE literals | **223 c3** |
| 6 | one reader given a path and a git ref | **223 c4** |
| 7 to 16 | normalising, frozen defaults, scheme versions, the column, both writers stamping, the per-process map, the golden test, the frozen-default test | 176 |
| 17 | the changelog gate uses the widened hash | **223 c5** (reworded as an EARS event) |
| 18 | the pre-fingerprint database (HELD BEHIND #89, both texts) | 176, unchanged |
| 19 | amend REQ-QAC-006 c2 (T8) | **223 c6** |
| 20, 21, 22 | RFC 8785, 'v1:' + full 64-hex digest (Keith, 176-A), per-dataset file checks | 176 |
| 23 | one report per source file | **223 c7** |
| - | test: the gate fails on an unexplained edit to macros/matches_regex.sql, naming the file once and its checks | **223 c8, new** |
| - | test: one check's expression, singular SQL or Evidently threshold changed without an entry fails naming that check alone; with an entry it passes | **223 c9, new** |

In 176 the moved criteria stay in place as `retired_criteria` with `replaced_by: [REQ-QAC-223]`, so 12 and
18 keep their numbers. 223 is written as "definition hash" rather than "fingerprint", because it stores
nothing. It needs no database change, so it is not held. 176 now depends on 223, and no longer on
REQ-QAC-006, whose amendment moved to 223.

**Two things in 223 that are new, and worth a look at sign-off:**
- **The build commit trips the gate once for each Evidently check (about five).** 223 c3 adds column,
  method and thresholds to each CHECK_LIFECYCLE entry, and the diff base's entries have none of them. The
  draft has the build add a changelog entry to each check ("definition now recorded with the check;
  behaviour unchanged"). That follows your 2026-10-10 rejection of a one-off gate exemption. Say if you
  would rather handle it another way.
- **One writer, two uses.** When 176 lands, it extends 223's writer with the frozen defaults, RFC 8785 and
  the 'v1:' 64-hex form, and the gate compares that writer's output on both sides. A second, gate-only hash
  is rejected.

What follows is the 176 scoper-pass account from before the split, unchanged:

- **No criterion changed** except c18. It is now marked **HELD BEHIND plans/running-thoughts.md #89** and
  carries both texts: the 2026-10-10 refuse-and-rebuild wording, and a migration-era alternative under
  #89 rule 1 ("an empty value means not recorded at the time; never computed from a later definition").
- **Code checked and still true**: no fingerprint column, a 16-hex `_config_hash`, Evidently constants
  still read as module constants, and no rfc8785 dependency.
- **Recorded as decisions**:
  - This is #89's raw-evidence gap "a check's definition isn't pinned to each result".
  - Its `v1:` prefix already follows #89's proposed rule 4.
- **Open question, part of the hold (still open)**: under migrations, what REQ-PIPE-177's bulk re-check does with
  an *empty* fingerprint. Both earlier rejections were made under "regenerate, never migrate".
- **New NFRs**: rfc8785 is a new dependency, guarded by the golden test; storage of about 67 bytes per
  result; config only, no personal data.

### REQ-PIPE-177: bulk re-check (scoper pass; 26 -> 28 criteria)

- **c21**: its REQ-GHUB-082 c3 amendment now builds on REQ-PIPE-163's (T2 below) and adds the bulk
  re-check to `TERMINAL_ONLY`.
- **New c27**: leaves out files of an open contested pair and says how many in the panel. Their
  settlement checks them under today's definitions anyway.
- **New c28** (confirmed by Keith, 164/177-A): skips datasets the agreement backstop refuses and names them in the panel.
  The queue nudge keeps them, so nothing is lost.
- **c24 is not met**; see the correction above. Keith left post-build-review #179 (owed work has no Lambda
  budget; processing_pass.py:520 calls `recheck.run_all_owed` with no deadline) to this requirement:
  c24 carries the fix, recorded as a decision.
- **Decisions**:
  - **REJECTED running only the fixed check** (now possible under REQ-PIPE-188 to 191). A supply's most
    recent run is its current run (REQ-PIPE-140 c5), so a one-check run would leave every other check
    unjudged. Say if you want this reopened: it is the biggest speed lever, about a minute per supply
    against seconds.
  - Turned-off datasets need nothing new.
- **New NFRs**:
  - The decision's new check column is additive.
  - Cost: about seven hours of tool time for a fix that touches 400 supplies, which is why the hand-off
    and the deadline matter.

### REQ-PIPE-178: trial (scoper pass; 17 criteria, one edited)

- **c3**: tables are found through REQ-PIPE-193 c13's one resolver.
- **Decisions**:
  - The trial runs every check, not only the fixed one, because it shows a verdict and the gate's
    prediction.
  - It is not a filing decision, so REQ-GHUB-082 needs no amendment.
  - Open pairs and refused datasets carry over from 177 automatically.
- **New NFRs**: cost (uncapped by your choice), and nothing left on disk.
- **No questions.**

## Questions for Keith (relay-ready; recommended option first)

**All eight were answered 2026-10-14, each with option A. See the last section.** They are kept here as
the record of what was asked.

### Set 1: sign-off forks on 164, 165, 175, 177

1. **(164/177-A) The agreement backstop refuses a dataset. What happens to a re-check of its supplies?**
   - **A (recommended): refuse a single re-check, and skip that dataset in a bulk re-check, naming it in
     the panel.** This matches REQ-PIPE-163 c35, which refuses a placement in the same situation. Nothing
     is lost: the fingerprint still differs, so the queue's nudge keeps offering it.
   - B: record it and let it wait, still owed, until the change is restored or declared. `recheck.run`
     already does this for other owed runs. The cost is that a decision sits on the record with nothing
     having run.
2. **(164-B) Can a REJECTED or superseded supply be re-checked?**
   - **A (recommended): no, keep refusing it (today's c10).** The scope stays small. A rejected supply's
     table sits in the rejected schema, which REQ-PIPE-140's run does not read today.
   - B: yes. It stays rejected or superseded, with its new verdict on the record. This means a supply you
     rejected because *our* check was wrong would no longer keep that wrong verdict on the record. It
     needs run support for the rejected and superseded schemas.
3. **(165-A) How does the parity test ask "would the flags accept this"?**
   - **A (recommended): drive the real `filing_decisions.apply` against a database with one slot per
     state, inside a transaction that is rolled back.** This uses the real refusals, adds no product
     code, and follows CLAUDE.md's test rule 1. It probably runs in the deployment half of CI.
   - B: pull a pure `permitted(state, operation)` out of apply, and have both the door and the test use
     it. Drift becomes impossible by construction, but it is a refactor of apply, and the test then
     compares a function with itself.
4. **(175-A) Split REQ-DASH-175?**
   - **A (recommended, and drafted): two requirements.** 175 is placement, built with REQ-PIPE-163.
     **REQ-DASH-221** is re-check, built after 164 and 177. Each is small and signable on its own, and
     neither reads as half-built for weeks.
   - B: one requirement, with the criteria ordered and the re-check half left unmet until 164 and 177
     land.

### Set 2: 166, and the parts of 176 not held

1. **(166-A) Does the dashboard half of a withdrawal live in REQ-PIPE-166?**
   - **A (recommended, and drafted): fold it in.** That is two criteria (c12 and c13), and without them a
     withdrawn acknowledgement keeps showing as standing.
   - B: a separate DASH requirement, the way REQ-PIPE-161 and REQ-DASH-162 were split.
2. **(166-B) On a date before the withdrawal, does the page still show the acknowledgement or mark?**
   - **A (recommended): yes, up to the withdrawal's instant.** This is how an acknowledgement is already
     shown (from its own instant). The supply history shows both entries.
   - B: no, on every date, as REQ-DASH-162 c5 does for an excuse. The mistake is erased from the past
     view too.
3. **(176-A) Fingerprint length.**
   - **A (recommended): the full 64 hex digits.** Both the architect and the scoper recommend it. It costs
     about 48 bytes more per result row, and there is no truncation to defend later.
   - B: 16 hex digits, like `check_lifecycle._config_hash` today. The chance of a collision is negligible
     either way.
4. **(176-B) Split 176 so that its changelog-gate half can be signed now?**
   - **A (recommended): split it.** Criteria 3 to 6, 17, 19 and 23 widen what the changelog gate sees:
     expressions, singular SQL, macros and Evidently settings. They need no stored column. Today
     `macros/matches_regex.sql` backs 11 checks, and editing it trips no gate. That half could be built
     now, while the stored fingerprint waits on #89.
   - B: keep it whole, and held.

**Still held, not asked now:** 176 c18 itself, and what an empty fingerprint means for 177. Both come back
with #89.

## Non-functional angles: which were judged, and how

- **Performance and cost.** Judged per requirement:
  - 177: about a minute per supply, which is why the hand-off and the deadline matter.
  - 178: a trial costs what a real run costs.
  - 176: the fingerprint map is built once per process.
  - 165: the test's cost in CI.
  - Proposed in the NFRs; no question needed.
- **Scalability at 30 datasets.**
  - 221: a bulk run adds one drawer line and nothing on unchanged rows.
  - 175: one tag per placed row.
  - 176: storage per row.
  - 177: the nudge already aggregates.
- **Reliability.** The owed, claimed and processing-pass machinery already exists. One real gap was
  found: the deadline (177 c24).
- **Security.** Ruled out beyond what exists: the same allowlist and actor rules, and the bulk re-check
  and trial stay off GitHub.
- **Privacy.**
  - 178 reads supply rows only on the orchestrator path (existing NFR).
  - 176 reads configuration only.
  - Worth knowing, but not new to these requirements: every reason a person types is published on the
    public dashboard. On a real asset, a free-text reason could carry personal detail. That applies to
    every filing decision, so it is not raised as a question here.
- **Compatibility.** Ruled out: no new vendor assets, and rfc8785 is pure Python and installs through
  `uv`.
- **Maintainability.**
  - New decision-log actions (164, 166) and a new column (177, 176) mean schema changes. They are
    additive, so they fit either regime #89 settles on.
  - rfc8785 is a new dependency.
  - 176 adds a frozen-defaults table to look after.
- **Observability and audit.**
  - A withdrawal names the entry it withdraws.
  - A bulk re-check records the check and its changelog entry.
  - Nothing is ever deleted.
- **Compliance and retention.** Ruled out: everything is append-only, and nothing is deleted.

## Amendments to SIGNED requirements (exact wording; OLD copied from the live requirements.yaml)

`<date built>` is the date the amendment lands, written the way the register already dates its
amendments. Where REQ-PIPE-163's already-approved amendment touches the same criterion, NEW shows the
combined result, and the note says how to apply this batch's clauses alone. REQ-DASH-175 c12 (amendment 2)
is not repeated here: it is approved, and it is carried word for word as REQ-DASH-175 c7.

**T1. REQ-GHUB-082 criterion 1** (signed 2026-09-28, built). Carried by REQ-PIPE-164 c12 (re-check), REQ-PIPE-166 c7 (both withdrawals); the last sentence is REQ-PIPE-163's already-approved amendment 11, shown so the result is whole.

- Old: "THE SYSTEM SHALL accept promote, reject, demote, re-file, substitute, de-substitute, inherit, un-inherit, mark as not supplied, acknowledge, supersede, un-supersede, excuse lateness and withdraw excuse as structured filing decisions raised on the GitHub ticket for the SLOT they concern - one dataset in one period, per REQ-PIPE-083 - so that the period a decision applies to comes from the ticket's own identity rather than from anything stated in the body. Every criterion below that says "a filing decision" SHALL mean any one of those fourteen. AMENDED 2026-10-05 by REQ-PIPE-132 criterion 13 (mark as not supplied), REQ-PIPE-122 criterion 22 (acknowledge) and REQ-PIPE-120 criterion 9 (supersede, un-supersede), and 2026-10-11 by REQ-PIPE-161 criterion 13 (excuse lateness, withdraw excuse). Keep, and the confirmation of a calendar correction's moves, are filing decisions too, offered on the terminal route only (criterion 3) - AMENDED 2026-10-11 by REQ-PIPE-170 criterion 11. Settling a contested pair (choose-file) is a filing decision too, offered on the terminal route only (criterion 3) - AMENDED 2026-10-13 by REQ-PIPE-193 criterion 29."
- New: "THE SYSTEM SHALL accept promote, reject, demote, re-file, substitute, de-substitute, inherit, un-inherit, mark as not supplied, acknowledge, supersede, un-supersede, excuse lateness, withdraw excuse, re-check, withdraw acknowledgement and withdraw not-supplied as structured filing decisions raised on the GitHub ticket for the SLOT they concern - one dataset in one period, per REQ-PIPE-083 - so that the period a decision applies to comes from the ticket's own identity rather than from anything stated in the body. Every criterion below that says "a filing decision" SHALL mean any one of those seventeen. AMENDED 2026-10-05 by REQ-PIPE-132 criterion 13 (mark as not supplied), REQ-PIPE-122 criterion 22 (acknowledge) and REQ-PIPE-120 criterion 9 (supersede, un-supersede), 2026-10-11 by REQ-PIPE-161 criterion 13 (excuse lateness, withdraw excuse), <date built> by REQ-PIPE-164 criterion 12 (re-check) and <date built> by REQ-PIPE-166 criterion 7 (withdraw acknowledgement, withdraw not-supplied). Keep, and the confirmation of a calendar correction's moves, are filing decisions too, offered on the terminal route only (criterion 3) - AMENDED 2026-10-11 by REQ-PIPE-170 criterion 11. Settling a contested pair (choose-file) is a filing decision too, offered on the terminal route only (criterion 3) - AMENDED 2026-10-13 by REQ-PIPE-193 criterion 29. Placing a held supply (place) is a filing decision too, offered on the terminal route only (criterion 3) - AMENDED <date built> by REQ-PIPE-163 criterion 13."
- Why: re-check and the two withdrawals are filing decisions on both routes, like withdraw excuse; the count moves 14 -> 17.
- Built behaviour: BUILT CODE CHANGES: filing_decisions.OPERATIONS gains three operations; the GitHub intake recognises them by name.
- Note: Each requirement adds only its own clause. If REQ-PIPE-164 or 166 is built before REQ-PIPE-163, leave 163's last sentence out; if only one of 164/166 is built, add only its names, its AMENDED clause, and count 15 or 16.

**T2. REQ-GHUB-082 criterion 3** (signed 2026-09-28, built). Carried by REQ-PIPE-177 c21; the place clause is REQ-PIPE-163's already-approved amendment 12.

- Old: "THE SYSTEM SHALL write an identical decision-log entry whichever route raised the decision, and SHALL NOT give either route an operation the other lacks, except the confirmation of a calendar correction's moves and the keeps it records, which is offered on the terminal route only (REQ-PIPE-170 criterion 10), and settling a contested pair (choose-file), which is offered on the terminal route only (REQ-PIPE-193 criteria 1 and 16). AMENDED 2026-10-11 by REQ-PIPE-170 criterion 11, and 2026-10-13 by REQ-PIPE-193 criterion 29."
- New: "THE SYSTEM SHALL write an identical decision-log entry whichever route raised the decision, and SHALL NOT give either route an operation the other lacks, except the confirmation of a calendar correction's moves and the keeps it records, which is offered on the terminal route only (REQ-PIPE-170 criterion 10), settling a contested pair (choose-file), which is offered on the terminal route only (REQ-PIPE-193 criteria 1 and 16), placing a held supply (place), which is offered on the terminal route only (REQ-PIPE-163 criteria 14 and 36), and a bulk re-check of one check, which is offered on the terminal route only (REQ-PIPE-177 criterion 21). AMENDED 2026-10-11 by REQ-PIPE-170 criterion 11, 2026-10-13 by REQ-PIPE-193 criterion 29, <date built> by REQ-PIPE-163 criterion 14, and <date built> by REQ-PIPE-177 criterion 21."
- Why: a bulk re-check names a check, not a slot, so it has no ticket to be raised on; it is a fourth terminal-only exception.
- Built behaviour: BUILT CODE CHANGES: filing_decisions.TERMINAL_ONLY gains it (REQ-PIPE-177 c21).
- Note: REQ-PIPE-177 depends on REQ-PIPE-164, which depends on REQ-PIPE-163, so 163's clause will always have landed first.

**T3. REQ-GHUB-082 criterion 31** (signed 2026-09-28, built). Carried by REQ-PIPE-166 c7.

- Old: "THE SYSTEM SHALL reach substitute, de-substitute, inherit, un-inherit and mark as not supplied per period and dataset rather than from the supply queue, because none of them answers "what do I do with this arriving supply" - each is a decision about how a period is filled, or accepted as unfilled, when a supply for it never arrives. AMENDED 2026-10-05 by REQ-PIPE-132 criterion 13."
- New: "THE SYSTEM SHALL reach substitute, de-substitute, inherit, un-inherit, mark as not supplied and withdraw not-supplied per period and dataset rather than from the supply queue, because none of them answers "what do I do with this arriving supply" - each is a decision about how a period is filled, or accepted as unfilled, when a supply for it never arrives. AMENDED 2026-10-05 by REQ-PIPE-132 criterion 13, and <date built> by REQ-PIPE-166 criterion 7."
- Why: withdrawing a mark is about how a period is accepted as unfilled, so it is reached where the mark is.
- Built behaviour: BUILT CODE CHANGES: filing_decisions.PERIOD_SCOPED gains it.

**T4. REQ-GHUB-082 criterion 32** (signed 2026-09-28, built). Carried by REQ-PIPE-166 c7.

- Old: "THE SYSTEM SHALL record substitute, de-substitute, inherit, un-inherit and mark as not supplied in the decision log on the same terms as every other filing decision - actor, reason, allowlist, refusal, GitHub parity - so that the un-inherit an operator performs to unblock a refused demotion is as accountable as the demotion itself. AMENDED 2026-10-05 by REQ-PIPE-132 criterion 13."
- New: "THE SYSTEM SHALL record substitute, de-substitute, inherit, un-inherit, mark as not supplied and withdraw not-supplied in the decision log on the same terms as every other filing decision - actor, reason, allowlist, refusal, GitHub parity - so that the un-inherit an operator performs to unblock a refused demotion is as accountable as the demotion itself. AMENDED 2026-10-05 by REQ-PIPE-132 criterion 13, and <date built> by REQ-PIPE-166 criterion 7."
- Why: the per-period list here must match criterion 31's.
- Built behaviour: NO CODE CHANGE beyond T3; text catch-up.

**T5. REQ-PIPE-074 criterion 1** (signed 2026-09-26, built). Carried by REQ-PIPE-164 c12, REQ-PIPE-166 c7; the place wording is REQ-PIPE-163's already-approved amendment 18.

- Old: "THE SYSTEM SHALL record every filing decision - promote, reject, demote, re-file, mark as not supplied, acknowledge, supersede, un-supersede, excuse lateness, withdraw excuse, keep and choose-file - as an entry in one append-only log, and SHALL NOT keep a second record of any of them anywhere else. AMENDED 2026-10-05 by REQ-PIPE-132 criterion 13, REQ-PIPE-122 criterion 22 and REQ-PIPE-120 criterion 9, and 2026-10-11 by REQ-PIPE-161 criterion 13 and REQ-PIPE-170 criterion 11 (keep; confirming a calendar correction records each re-file, hold and keep it makes as its own entry here), and 2026-10-13 by REQ-PIPE-193 criterion 29 (choose-file - one entry for a settlement, with each file's rejection, supersession or re-file its own entry naming it as the cause)."
- New: "THE SYSTEM SHALL record every filing decision - promote, reject, demote, re-file, mark as not supplied, acknowledge, supersede, un-supersede, excuse lateness, withdraw excuse, keep, choose-file, place, re-check, withdraw acknowledgement and withdraw not-supplied - as an entry in one append-only log, and SHALL NOT keep a second record of any of them anywhere else. AMENDED 2026-10-05 by REQ-PIPE-132 criterion 13, REQ-PIPE-122 criterion 22 and REQ-PIPE-120 criterion 9, and 2026-10-11 by REQ-PIPE-161 criterion 13 and REQ-PIPE-170 criterion 11 (keep; confirming a calendar correction records each re-file, hold and keep it makes as its own entry here), and 2026-10-13 by REQ-PIPE-193 criterion 29 (choose-file - one entry for a settlement, with each file's rejection, supersession or re-file its own entry naming it as the cause). And <date built> by REQ-PIPE-163 criterion 13 (place - recorded as a person's re-file from no period, REQ-PIPE-163 criterion 2, so it adds no decision-log action of its own). And <date built> by REQ-PIPE-164 criterion 12 (re-check - one entry for each supply re-checked, a bulk re-check (REQ-PIPE-177) writing one for each supply it covers), and <date built> by REQ-PIPE-166 criterion 7 (withdraw acknowledgement, withdraw not-supplied - each naming the entry it withdraws)."
- Why: the one log's list of filing decisions is meant to be complete.
- Built behaviour: BUILT CODE CHANGES: three new decision-log actions (decision_log.ACTIONS, qa_store's decision_action_known constraint).
- Note: Built before REQ-PIPE-163: start from the OLD text and leave out ', place' and 163's 'And <date built> by REQ-PIPE-163...' sentence.

**T6. REQ-PIPE-076 criterion 7** (signed 2026-09-26, built). Carried by REQ-PIPE-164 c20; the placement clause is REQ-PIPE-163's already-approved amendment 20.

- Old: "WHERE any decision has been recorded against a supply by a person, THE SYSTEM SHALL NOT promote that supply automatically thereafter - EXCEPT un-supersede, re-file and an excuse of lateness or its withdrawal, the person-decisions after which the gate may still promote automatically, and the supersede un-supersede undoes (REQ-PIPE-120 criterion 4, REQ-PIPE-141 criterion 8, REQ-PIPE-161 criterion 19). AMENDED 2026-10-05 by REQ-PIPE-120 criterion 9 and REQ-PIPE-141 criterion 19, and 2026-10-11 by REQ-PIPE-161 criterion 19."
- New: "WHERE any decision has been recorded against a supply by a person, THE SYSTEM SHALL NOT promote that supply automatically thereafter - EXCEPT un-supersede, re-file (a person's placement of a held supply included, being recorded as a re-file - REQ-PIPE-163 criteria 2 and 24), re-check, single or bulk, and an excuse of lateness or its withdrawal, the person-decisions after which the gate may still promote automatically, and the supersede un-supersede undoes (REQ-PIPE-120 criterion 4, REQ-PIPE-141 criterion 8, REQ-PIPE-161 criterion 19, REQ-PIPE-164 criterion 20). AMENDED 2026-10-05 by REQ-PIPE-120 criterion 9 and REQ-PIPE-141 criterion 19, 2026-10-11 by REQ-PIPE-161 criterion 19, <date built> by REQ-PIPE-163 criterion 24, and <date built> by REQ-PIPE-164 criterion 20."
- Why: Keith, 2026-10-10: a re-checked waiting supply that comes back green may promote itself; without this every re-checked supply needs a person.
- Built behaviour: BUILT CODE CHANGES: the re-check action joins rejection.NOT_A_DECISION_ABOUT_ITS_DATA.
- Note: REQ-PIPE-163 criterion 24 says its amendment names re-check, but the wording Keith approved does not - this is where re-check is added.

**T7. REQ-PIPE-122 criterion 14** (signed 2026-10-04, built). Carried by REQ-PIPE-164 c21.

- Old: "IF a person acknowledges a supply that owes no acknowledgement - not promoted, not amber, promoted under promote, or already acknowledged - THEN THE SYSTEM SHALL refuse it and say why."
- New: "IF a person acknowledges a supply that owes no acknowledgement - not promoted, not amber, promoted under promote, or already acknowledged - THEN THE SYSTEM SHALL refuse it and say why; a promoted supply whose re-check came back worse than the verdict it was promoted on (REQ-PIPE-164) owes an acknowledgement of that new verdict, whatever the amber setting, until a person acknowledges it or demotes it. AMENDED <date built> by REQ-PIPE-164 criterion 21."
- Why: Keith, 2026-10-10: 'it stays' is recorded with acknowledge, reused rather than a new 'keep'.
- Built behaviour: BUILT CODE CHANGES: acknowledgement's refusal and qa_store's acknowledgement view learn the re-checked case.

**T8. REQ-QAC-006 criterion 2** (signed 2026-09-20, built). Carried by **REQ-QAC-223 c6**. It moved there from REQ-QAC-176 c19 with the split (176-B), so it is **no longer held**.

- Old: "A definition change with no accompanying changelog entry fails CI."
- New: "A definition change with no accompanying changelog entry fails CI - a definition change being a change to a check's configuration, its expression or test type, a singular test's SQL, a project macro its test type or its SQL uses (REQ-QAC-223 criterion 2), or an Evidently check's column, method or thresholds. AMENDED <date built> by REQ-QAC-223 criterion 6."
- Why: today the gate misses expression, singular-SQL, macro and Evidently changes (176's decisions).
- Built behaviour: BUILT CODE CHANGES: validate_check_lifecycle uses the widened definition hash.
- Note: Wording unchanged in substance from the 2026-10-10 draft; the only change is that it cites REQ-QAC-223 in place of REQ-QAC-176 criteria 4 and 19.

**T9. REQ-DASH-126 criterion 1** (signed 2026-10-04, built). Carried by REQ-DASH-221 c14.

- Old: "WHERE a promoted supply's status, recomputed with its most recent cross-table results, is red, THE SYSTEM SHALL show it as RED PROMOTED on its dataset page and its agency card, distinctly from a red supply awaiting a decision and from a promoted supply that is not red. AMENDED 2026-10-13 (REQ-DASH-197 criteria 13 and 17): the promoted supply this label and the agency card's count read is the verdict line's in-place supply, which is now the one most recently promoted as at the date on show."
- New: "WHERE a promoted supply's status, recomputed with its most recent cross-table results - or taken from its most recent re-check where that is newer (REQ-PIPE-164, REQ-PIPE-177) - is red, THE SYSTEM SHALL show it as RED PROMOTED on its dataset page and its agency card, distinctly from a red supply awaiting a decision and from a promoted supply that is not red. AMENDED 2026-10-13 (REQ-DASH-197 criteria 13 and 17): the promoted supply this label and the agency card's count read is the verdict line's in-place supply, which is now the one most recently promoted as at the date on show. AMENDED <date built> by REQ-DASH-221 criterion 14: a promoted supply a re-check turned red is red promoted too."
- Why: a promoted supply our fixed check now judges red must read very clearly (Keith's condition, 2026-10-10), and the existing badge is that treatment.
- Built behaviour: BUILT CODE CHANGES (the template's red-promoted condition) unless it already reads the newest run - check at build.

**T10. REQ-DASH-126 criterion 2** (signed 2026-10-04, built). Carried by REQ-DASH-221 c14.

- Old: "THE SYSTEM SHALL name, beside a red promoted supply, the arrival or promotion that caused the re-evaluation that turned it red."
- New: "THE SYSTEM SHALL name, beside a red promoted supply, the arrival or promotion that caused the re-evaluation that turned it red, or the re-check that did (REQ-PIPE-164, REQ-PIPE-177), worded as REQ-DASH-221 criteria 1 and 2 word it. AMENDED <date built> by REQ-DASH-221 criterion 14."
- Why: the cause must name our check, never leave a supplier looking responsible.
- Built behaviour: BUILT CODE CHANGES.

**T11. REQ-DASH-126 criterion 6** (signed 2026-10-04, built). Carried by REQ-DASH-221 c14.

- Old: "WHEN the dashboard is viewed as at an instant before a promoted supply turned red, THE SYSTEM SHALL show the supply as it was at that instant, with a note that it turned red on a named date after a named arrival or promotion, and SHALL NOT show the earlier view as red."
- New: "WHEN the dashboard is viewed as at an instant before a promoted supply turned red, THE SYSTEM SHALL show the supply as it was at that instant, with a note that it turned red on a named date after a named arrival or promotion - or, where a re-check turned it, REQ-DASH-221 criterion 5's re-checked-later note in place of that note - and SHALL NOT show the earlier view as red. AMENDED <date built> by REQ-DASH-221 criterion 14."
- Why: REQ-DASH-175's 2026-10-10 as-of decision: the re-check note replaces the turned-red-later tag.
- Built behaviour: BUILT CODE CHANGES.

## Register bookkeeping (not amendments)

- REQ-PIPE-163's decisions cite "REQ-DASH-175 criterion 12" for amendment 2. After the split, that text is
  REQ-DASH-175 c7. 163 is signed, so this is noted here rather than edited.
- Applying `requirements-draft.yaml` adds REQ-DASH-221 and REQ-QAC-223. Confirm both numbers are still
  free first.
- REQ-QAC-176 now carries a `retired_criteria:` block (criteria 3, 4, 5, 6, 17, 19, 23, by Keith,
  2026-10-14, replaced by REQ-QAC-223). Keep it when applying. It is what holds 176's numbering steady.
- No other amendment T1 to T11 moves. T8 is the only one 176 carried.

## Plans file draft (for a human to apply; not written)

`plans/running-thoughts.md` #92, appended to step 3:

> **Unsigned triage re-scoped, 2026-10-14 (delivery-scoper):** the seven are drafted in
> docs/drafts/unsigned-triage/ (requirements-draft.yaml, summary.md). REQ-DASH-175 is split, its
> re-check half becoming REQ-DASH-221. One triage finding was
> wrong: REQ-PIPE-177 criterion 24 (the pass's deadline for owed work) is not met; Keith left
> post-build-review #179 to it. Keith answered all eight questions the same afternoon (all option A).
> REQ-QAC-176 was split: its changelog-gate half is REQ-QAC-223, signable now, and the stored fingerprint
> stays held behind #89. The architect, CLI UX and dashboard UX reviews were folded in the same afternoon
> (Keith answered their questions, all option A; one new amendment, T12, to REQ-PIPE-163 c35); the
> closePanel() defect they found is post-build-review #180. REQ-PIPE-177, REQ-PIPE-178 and REQ-DASH-221
> are effectively held with REQ-QAC-176 behind #89. Next is the sign-off walk.

## Keith's answers (2026-10-14 afternoon, via AskUserQuestion)

- 164/177-A (backstop refuses the dataset): **A** - a single re-check is
  refused naming the backstop; a bulk one skips the dataset, names it in the
  panel and keeps it in the nudge (as REQ-PIPE-163 c35).
- 164-B (re-check a rejected or superseded supply): **A** - keep refusing.
- 165-A (parity test): **A** - drive the real `filing_decisions.apply` for
  one slot per state inside a rolled-back transaction.
- 175-A: **A** - split: 175 placement (built with REQ-PIPE-163), REQ-DASH-221
  re-check wording (after 164 and 177).
- 166-A: **A** - the dashboard half folded into 166.
- 166-B: **A** - on a past date the page shows the annotation up to its
  withdrawal, not after.
- 176-A: **A** - full 64-hex SHA-256.
- 176-B: **A** - split the changelog-gate half off to sign now; the
  fingerprint-on-every-result half stays held behind #89.
- post-build-review #179 (owed work has no Lambda budget): **leave it to
  REQ-PIPE-177** - its criterion 24 carries it.
- Next: architect + CLI UX + dashboard UX reviews before the sign-off walk.

## Folded in (delivery-scoper, 2026-10-14 afternoon)

Each answer above is now a decision on the requirement it concerns, citing "Keith, 2026-10-14, <question
id>". The open question (where there was one) is removed, and so is the PROVISIONAL mark. The criteria
already said what Keith chose, so no criterion text changed for any of them:

- **164/177-A**: REQ-PIPE-164 c23, REQ-PIPE-177 c28.
- **164-B**: REQ-PIPE-164 c10 (unchanged).
- **165-A**: REQ-GHUB-165 NFR 3.
- **175-A**: REQ-DASH-175 and REQ-DASH-221.
- **166-A** and **166-B**: REQ-PIPE-166 c12 and c13.
- **176-A**: REQ-QAC-176 c21. Decision 'THE FULL 64-HEX SHA-256 IS STORED' is now marked confirmed.
- **176-B**: the split above.
- **#179**: a decision on REQ-PIPE-177 says c24 carries the fix.

**Still open, deliberately:**
- REQ-QAC-176 c18, and its empty-fingerprint question (mirrored on REQ-PIPE-177). Both are held behind #89.
- ~~REQ-DASH-175's low-stakes question~~ - settled after the reviews (main session, low stakes): a placed
  turned-off hold stays in the quiet section. See **Reviews folded**.
- REQ-QAC-223's handling of the Evidently checks in the build commit. It is drafted as a decision, flagged
  above, and is one of the confirmations in **Ready for sign-off**.

## Reviews folded (2026-10-14 afternoon)

Sources: `review-architect.md` and `review-cli-ux.md` beside this file, and
`../road-testing-feedback/review-dashboard-ux.md` for 166, 175 and 221. Every finding is in a criterion,
an NFR or a decision; each of Keith's answers is a decision citing "Keith, 2026-10-14, review-<name>
Q<n>" with the rejected option. **No criterion was renumbered**: changes are in place, new criteria are
appended, and each requirement carries a "REVIEWS FOLDED, 2026-10-14" decision listing them.

The closePanel() defect both reviews found is NOT specified here: the main session is fixing it now, for
all five side panels and test-first, as post-build-review #180 (Keith, review-architect Q1 and
review-dashboard-ux Q4, option A). It is folded into REQ-DASH-222 in the other draft.

**REQ-PIPE-164** (24 -> 27 criteria)
- In place:
  - c5: says nothing runs until the processing pass or that command does (cli-ux L4).
  - c10: a rejected supply's refusal names promote, and a superseded one's names un-supersede, each
    with its flag form (cli-ux L2).
  - c15: "the verdict it was promoted on" is the promote decision's `promoted_status` (architect).
  - c23: the backstop refusal gives REQ-PIPE-173's own finding and its paste-ready fix
    (`agreement_freeze.Finding.fix`), and says the re-check can be raised again once declared (cli-ux H3).
- New:
  - c25: a test that a promoted supply's re-check appends no gate decision. This is the architect's HIGH:
    `recheck._run_claimed` calls `promotion.after_runs` on every re-check today.
  - c26: the door's label, "Re-check: run its checks again where it is (about a minute; recorded and
    published)", listed after the decisions that settle the supply (cli-ux L1).
  - c27: carries amendment **T12** to signed REQ-PIPE-163 c35 (cli-ux H3).
- NFRs: the gate is skipped in the executor; `_readers_rechecked` reused for c2; an action constant of
  its own, distinct from `recheck.RECHECK`; `promoted_status` as the source for c15.
- c19's linked test is named for the build (architect LOW).

**REQ-GHUB-165** (6 -> 7 criteria)
- c1: un-supersede is read through a connection-taking `supersede_offers(conn, state)` beside
  `excuse_offers`, and the offer carries a count (architect; cli-ux L5).
- New c7: the parity test seeds its own examples, committed, in the test's own database
  (`MOTHMAN_TEST_DSN`). Keith chose this: **review-architect Q3, option A**.
- The 165-A decision is marked partly superseded. Driving the real `apply` stands. The rolled-back
  transaction goes, because the flag route opens a second connection (`filing_decisions.py` around
  line 477) that cannot see uncommitted seed rows.
- NFR 4: the test now runs in the **fast** half of CI, not `needs_deployment`.
- Decision: built after REQ-PIPE-163.

**REQ-PIPE-166** (13 -> 18 criteria)
- In place:
  - c2: the withdrawn entry is named by id, through `caused_by_decision`, never by position (architect).
  - c11 and the reader NFR: they now name `acknowledgement.acknowledged_by`, `pipeline/slot_timeline.py`,
    both dashboard-data builders and `DECISION_DONE` (architect).
  - c12: wording is "no longer acknowledged" / "no longer marked not supplied", following REQ-DASH-198's
    precedent (dashboard-ux M6).
  - c13: a mark's withdrawal is shown where c15 says.
- New:
  - c14: the confirmation names the entry withdrawn, its public consequence, and that it can be
    recorded again (cli-ux M4).
  - c15: a withdrawn mark shows in the cycle-table cell and in the accepted-gaps list, in
    `excuseNote()`'s shape (dashboard-ux M4).
  - c16: the awaiting tag returns with the withdrawn line beneath, and the reason is visible text
    (dashboard-ux M5).
  - c17: a second acknowledgement after a withdrawal is the one standing. `acknowledged_by` currently
    takes the EARLIEST (`LIMIT 1`) (architect).
  - c18: a test ties `DECISION_DONE` to `decision_log.ACTIONS` (architect LOW).
- NFR: generalise `excuse.history`/`pipeline/excuses.py` rather than add two near-copies.

**REQ-DASH-175** (no criterion changed)
- Its open question is closed as a decision marked **main session, low stakes**: a placed turned-off hold
  stays in the quiet "Received while turned off" section. This is what c3 and signed REQ-DASH-180 c14
  already say together, so it changes nothing Keith signed.
- The architect found it sound and buildable with REQ-PIPE-163.

**REQ-DASH-221** (no criterion changed)
- **Effectively held**, now said in its source and in a decision: it depends on REQ-PIPE-177 (and 178),
  which depend on REQ-QAC-176, held behind #89.
- The dashboard-ux review made no finding on it.

**REQ-QAC-176**: a "reviewed, no structural issues, stays held" decision. No criterion changed.

**REQ-QAC-223** (no criterion changed), three NFRs:
- c4's one reader is `validate_check_lifecycle._old_file_content`, extended to `ref=None`.
- It is not merged with `sources_fingerprint()` (REQ-PIPE-192's digest).
- The shared `WARN_THRESHOLD`/`FAIL_THRESHOLD` in `evidently_common.py` move into each check, with a
  comment saying why.

**REQ-PIPE-177** (28 -> 33 criteria). Now marked effectively held in its source.
- In place:
  - c13: offered **above the collection choice**, beside calendar corrections, as "Supplies checked
    before a check changed (N)". Keith: **review-cli-ux Q1, option A** (H1).
  - c14: progress lines in the shape `[k/N] re-checking <dataset> <period> (received <day>)...`, with
    elapsed and remaining time, and changed verdicts marked (M1).
  - c18: the approximate duration is shown as information only (**Q2 A**), with "Hand it to the
    processing pass" offered first (**Q4 A**). It also says nothing runs until the pass does (L4), and
    the flag panel says closing the terminal leaves the rest owed (M1).
  - c19: each collection's queue shows its own count plus "(M more in other collections)" (H1).
  - c20: `supply queue` prints one paste-ready line per check (H2; see the confirmation below).
  - c22: the reason is published against each of the N supplies (L3).
  - c23: nothing runs until the pass does (L4).
  - c28: the backstop's finding and fix are shown in the panel (H3).
- New:
  - c29: one owed line per bulk re-check, "k of N re-checks for <check> still owed (raised <date>)" (H4).
  - c30: exit codes 0 / 1 / REQ-PIPE-163 c28's code (**Q3 A**, M2).
  - c31: with no terminal and no `--yes`, the panel is shown and the command refuses with the flag hint
    (M3).
  - c32: `--list` (M5).
  - c33: the panel counts rejected and superseded supplies the run does not cover (L2).
- NFRs: an `ids=` filter on `run_all_owed`, which also carries c24's deadline; `_say_owed` grouping.

**REQ-PIPE-178** (17 -> 18 criteria): new c18, a trial ends by printing the real run's command and its
count, and in the TUI returns to the real run's confirmation (cli-ux M6). Its source now says it is
effectively held.

**Not adopted as written, and why** (each recorded in the requirement's decisions):
- cli-ux L4's condition "where no pass is scheduled" is written unconditionally. Nothing in the system
  knows whether a pass is scheduled, and the sentence is true either way.
- The architect's "drop panel=/req= in navUrl" applies to the Requirements panel only (REQ-DASH-222 c14).
  Other panels are left to #180.

## Amendment added by the reviews (exact wording; OLD copied from the live requirements.yaml)

**T12. REQ-PIPE-163 criterion 35** (signed 2026-10-14, **not built**). Carried by REQ-PIPE-164 c27. This is
cli-ux H3: the refusal gives no next step, the same gap 164 c23 and 177 c28 now close.

- Old: "IF the agreement backstop refuses the dataset (REQ-PIPE-173), THEN THE SYSTEM SHALL refuse the placement, saying that the dataset's judged past changed without a declared correction, and SHALL NOT record anything."
- New: "IF the agreement backstop refuses the dataset (REQ-PIPE-173), THEN THE SYSTEM SHALL refuse the placement, saying that the dataset's judged past changed without a declared correction, giving REQ-PIPE-173's own finding for that dataset with its paste-ready fix, each on a line of its own, and saying that the placement can be made again once the correction is declared, and SHALL NOT record anything. AMENDED <date built> by REQ-PIPE-164 criterion 27."
- Why: a refusal with no next step strands the person, and REQ-PIPE-173 already computes the fix.
- Built behaviour: NO CODE YET. 163 is unbuilt, so there is no built behaviour to change.
- Note: 163 is signed but not built, so Keith has two ways to apply this.
  - **(a) Recommended:** approve the wording now and apply it to 163 before 163 is built, writing
    "AMENDED 2026-10-14 by REQ-PIPE-164 criterion 27 (approved before build)". 163 then ships with the
    next step, and 164 c27 is met on day one.
  - (b) Let 164 carry it, as the other T amendments do. 163 would then ship without the next step until
    164 lands.

**The final amendment list for this batch is T1 to T12.** T1 to T11 are unchanged by the reviews. T12 is
new. REQ-DASH-175 c7 (amendment 2) is carried as before.

## Ready for sign-off

**Recommended build order** is the architect's, adjusted for Keith's answers:

1. **Post-build-review #180**, the closePanel() fix for all five side panels. The main session is
   doing it now.
2. **REQ-QAC-223** (changelog gate; no database change) and **REQ-DASH-222** (requirement addresses,
   relying on #180) - both buildable now, independent of each other.
3. **REQ-DOCS-219, then REQ-DASH-220** (the Feedback tab; other draft).
4. **REQ-PIPE-163 with REQ-DASH-175**, then **REQ-PIPE-179**'s remainder as the architect ordered.
5. **REQ-PIPE-164, then REQ-PIPE-166.** 166 c9 is vacuous until 164 exists.
6. **REQ-GHUB-165**. It needs 163 built, because held supplies are among its states. It no longer needs
   a bootstrap.
7. **Held behind plans/running-thoughts.md #89:** REQ-QAC-176, REQ-PIPE-177, REQ-PIPE-178 and
   REQ-DASH-221.

**Signable now** (each has had a scoper pass and the reviews; no open question changes what is built):

- REQ-PIPE-164
- REQ-GHUB-165
- REQ-PIPE-166
- REQ-DASH-175
- REQ-QAC-223

**Signable but not buildable until #89 settles:**

- REQ-PIPE-177
- REQ-PIPE-178
- REQ-DASH-221

**Still held, not for sign-off:** REQ-QAC-176. Criterion 18 and its empty-fingerprint question come back
with #89.

**Three points to confirm at sign-off**, recommended option first:

1. **T12: how REQ-PIPE-163 c35 gets the next step.**
   - **A (recommended):** approve the wording now and apply it to 163 before 163 is built.
   - B: let REQ-PIPE-164 c27 carry it later.
2. **REQ-PIPE-177 c20: `mothman supply queue` prints one line per changed check beneath the count**
   (cli-ux H2).
   - **A (recommended):** yes, each line a paste-ready `--check` value.
   - B: keep the single aggregate line.
   - Why this is asked rather than assumed: your 2026-10-10 decision rejected one line per check, for
     the terminal's queue. A is drafted as applying only to the command's printed output, and the TUI
     keeps your aggregate line and chooser.
3. **REQ-QAC-223: the build commit adds one changelog entry per Evidently check**, about five,
   "definition now recorded with the check; behaviour unchanged".
   - **A (recommended):** yes, following your 2026-10-10 rejection of one-off gate exemptions.
   - B: some other handling, to be said.

**Also settled by the main session as low stakes, for Keith to overrule if he wants:**

- REQ-DASH-175: a placed turned-off hold stays in the quiet section.

## Keith's answers to the fold's last questions (2026-10-14 afternoon)

- T12: **A** - approved now; applied to REQ-PIPE-163 criterion 35 in the
  register before 163 is built (164 c27 then records it as already applied).
- 177 c20: **A** - the printed `mothman supply queue` lists one line per
  changed check, ready to paste as --check; the terminal menu keeps the
  aggregate line and chooser (Keith, 2026-10-10).
- 223: **A** - the build commit adds one changelog entry per Evidently check
  ("definition now recorded with the check; behaviour unchanged"); no
  exemption.
