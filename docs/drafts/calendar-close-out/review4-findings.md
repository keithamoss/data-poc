# Round 4 reviews (2026-10-14): REQ-GEN-207, REQ-DASH-208, REQ-DASH-209, REQ-PIPE-210, REQ-PIPE-211, REQ-DASH-180's marker

Three advisory reviews, run in parallel with the scoper's fold of Keith's
15 follow-up answers (F1-F15), each reading the requirements as they will be
with those answers applied. Recorded here by the main session from the
agents' reports; nothing below is signed or folded yet.

## delivery-architect (1 blocker, 5 high, 7 medium, 3 low)

**B1 BLOCKER - REQ-PIPE-211 would not re-run the contested readers.**
`knock_on.readers()` re-runs a reader only where `_read_as(run, table) !=
_now_holds(table, period)`. A contested table is never resolved, so the run
records no `tables_read` for it (`_read_as` is None); after "reject both" the
period holds nothing (`_now_holds` is None). None equals None, so the reader
is only re-gated and stays red. This is the root cause of "red for good",
beyond the missing trigger. Proposed: a 211 criterion - a reader whose latest
result for a check reading the table is a not-evaluated record naming that
table (REQ-PIPE-115) is re-run whatever the period now holds; and an
amendment to REQ-PIPE-121 NFR 4 to say so. Test first, on the real Child
Protection fixture.

**H1 - amendment #27 is needed: REQ-PIPE-121 criterion 1 must change.**
`decision_log.apply_decision` owes a re-evaluation only when the period's
holding changes; "reject both" changes none. Criterion 1's last clause and
criterion 9 forbid the fix. Use the existing single predicate
`dataset_blockers._settles_a_contest` ("the one place a contest's end is
counted"), which also covers the rule superseding the pair (F5). Proposed
new 121 c1: "WHEN a table arrives in or leaves a period schema - promoted by
a rule or a person, re-filed in or out, superseded, demoted or rejected - or
a contest over a table in that period ends, by a person's settlement whatever
its outcome or by the rule superseding the pair (REQ-PIPE-194 criterion 9),
THE SYSTEM SHALL re-evaluate, within that period only, every cross-table
check that declares it reads the moved or formerly contested table, whether
it belongs to a supply WAITING in that period or one PROMOTED there, and
SHALL NOT re-evaluate any check that reads neither." Criterion 9 likewise
gains "or whose contest it ended". 211 c1 then reads "WHEN a contest ends
(REQ-PIPE-194 criterion 9)...". Check first whether REQ-PIPE-079 c6 already
re-evaluates when the later file arrives.

**H2 - REQ-GEN-207's byte-identity is coupled to more than the run plan.**
(a) `generate_cp_runs.py` indexes from the oldest quarter in seven places:
the seed, slot ids, run index, delivery names, ambers' placement,
`generated_periods()[-len(RUN_PLAN):]` and `inheritance_placements`.
Criterion 4 should require the added quarters to draw seeds, slot ids,
ambers and names separately, from a disjoint seed range, generated after the
existing fifteen, proved by a byte comparison of every existing delivery and
receipt. (b) Identical bytes do not mean identical results: drift references
reach back to the most recent earlier promoted period, so 2023-Q1 gains a
reference for the first time, and TS-77a stands on 2023-Q1. Add a criterion
comparing every existing Child Protection status and every quoted-text test
before and after, reporting any difference to Keith. (c) TS-79b's register
text ("the history's first supply ... nothing earlier") becomes untrue -
question A. (d) The added dates must go in a NEW, earlier quarterly calendar
version (as the daily calendar grew), never inserted into the 2023-01-01
version, or the agreement freeze refuses them; participation versions the
same. (e) The widened collision rule must pass today's plan unchanged
(TS-76 stands on 2024-Q4, TS-77a on 2023-Q1), or refuse naming both.

**H3 - REQ-DASH-209's data path.** `qa.slot_holds` is sufficient (amendment
#3 to REQ-GEN-045 is not needed - drop it), but `_manifest` agrees with it
only at the present date. And REQ-DASH-198's standing-in pill already
derives "Inherited/Substituted from" per dataset, period and day
(`pipeline/promotion_timeline.py`, `slot_timeline.for_dataset`, the page's
`promotionStateOn`). Proposed c2: take every row from the per-dataset
timelines the build already embeds, looked up by the date on show with the
same lookup as REQ-DASH-198, never a second derivation, never a period
schema, catalogue, `_manifest` or supply row. "At build time" becomes "the
build embeds the answers; the page looks them up". Add `stands_on` to the
timeline entries, and each supply's receipt, promoted status and
acknowledgements once per supply. TS-55's chip names the composition view as
its subject (REQ-DASH-208 c2's list gains it).

**H4 - REQ-PIPE-211 c1 restates the selection rule** (REQ-PIPE-193 c23
forbids a second rule): use `reevaluation.reading_checks()`. **c4 cannot be
met**: a chosen file is promoted later, by its own re-check's gate, which owes
its own re-evaluation - so the readers can run twice; reword and state the
cost.

**H5 - build order:** 207, 202, 211, 203, 204, 210, 182, 163, 179, 180, 208,
209, 205, 206 (the F8 scenario in 206).

**Medium:** M1 the still-failing shout contradicts 210 (question C). M2
REQ-PIPE-210's shared function belongs in `qa_tools/common`, pure over
recorded results and an instant, with each cause's sentence produced once in
Python; a reader with two causes is listed under the first by REQ-PIPE-115's
precedence; F6 as a criterion. M3 F8's scenario belongs to REQ-GEN-206
(question B). M4 TS-62: a pending correction does change later days - every
arrival from its date on is filed under the corrected agreement, confirmed
or not - so add a 205 criterion refusing a TS-62 version that takes effect on
or before any other Birth Registrations scenario's dates; `confirm_due` must
confirm only corrections listed in `corrections:`, or TS-62 gets confirmed;
the window must pass REQ-PIPE-134's overlap gate (question D). M5 the
terminal re-check criterion (claimed through `recheck.run`; the closing
panel says how many readers and which still fail). M6 REQ-DASH-208: chips as
`<a href>` with both parameters; the composition view in c2. M7 REQ-DASH-209
shows display names, never an email.

**Low:** the scenario parameter is matched against known ids before any use;
REQ-GEN-207 adds roughly 10-12 quarters, Child Protection's replay about
270s -> 450-480s, a bootstrap about 8.5-9 minutes; 211 needs 202's widened
pattern for its fixtures.

## delivery-cli-ux (REQ-PIPE-210, REQ-PIPE-211)

1. HIGH - the readers' re-check today runs AFTER the "Settled" panel, in
   silence, and over the whole collection's owed backlog. Run only this
   settlement's re-evaluations, before the closing panel, with the same
   progress display ("re-checking <dataset> (received <day>) against
   <period> - reader K of R"), no raw "knock-on:" lines.
2. HIGH - one closing "Settled" panel listing every reader re-evaluated,
   its status now and what the gate did; where its checks still could not
   run, the reason (REQ-PIPE-115), what runs them, and that nothing needs
   deciding; green only where every run completed green or amber.
3. HIGH - the still-failing shout ("A person decides", bold red in `mothman
   supply decisions`) contradicts 210 - same as architect M1.
4. HIGH - 210 must cover `mothman supply queue` and the after-a-run offer
   (`offer_after_run`), which would otherwise invite a decision on such a
   reader.
5. MED - the queue's header count on every route counts only items needing
   a decision and says "N more held red by one of these"; it agrees with the
   collection card; rule whether the ticket policy opens a ticket for such a
   reader (recommend not).
6. MED - beneath a cause, ONE dim "Holds red: ..." line naming every reader;
   in the picker one "Look at one of the N it holds red" entry (question C2).
7. MED - "Go to <cause>" lands exactly where the queue opens that item, then
   returns to a re-read queue.
8. MED - Ctrl-C during the readers' re-run gives a traceback today; end
   without one, say the settlement stands and what is owed, print `mothman
   pipeline process`; exit code question A2.
9. MED - accept `--wait` on choose-file rather than refusing it depending on
   data.
10. LOW-MED - the settlement's warning notes the readers to be re-checked and
    roughly how long (question B2).
11. LOW - F5's case (a later file ends the pair) reports the readers in that
    run's own closing output.
12. LOW - the cause sentence comes from one place for page and terminal.

## delivery-dashboard-ux (REQ-DASH-209, REQ-DASH-208, REQ-DASH-180 c27)

1. HIGH - REQ-DASH-208 c7/c9: a link that leads nowhere must say so in one
   line (the `.stale-link-notice` / `forgetStaleSegment` pattern), not land
   silently at the top.
2. HIGH - changing the date by hand after a jump leaves `scenario=` in the
   URL and the jump in the page's state; drop both on any date change.
3. HIGH - the accent mark needs a label ("<id> · in place on <date>") and the
   arrival notice's left rule, not the 2px accent outline (that is this
   page's focus ring); drop "until the reader next scrolls" (the jump's own
   scroll would remove it).
4. HIGH - REQ-DASH-209 "Nothing held" lumps red absences with quiet ones;
   group as Not supplied (red or waiting) first, then Substituted,
   Inherited, Promoted, then Not owed last, with a counting line (question
   D2).
5. MED-HIGH - the supply history has no "period row": put the link in each
   period's label and on gap/owed-nothing rows, never inside a delivery row.
6. MED - route `#/agency/<a>/collection/<c>/period/<p>?in-place-on=<D>`,
   with the h2/rail wording, not-found paths, and "<period> had not opened
   by <date>".
7. MED - chip as a real link: plain click intercepted, modified click left
   to the browser; Back/Forward restores the date without re-scrolling;
   focus without scrolling; parameter read case-insensitively.
8. MED - reuse "Decided by <name>" / "Applied automatically by the
   schedule"; head the column "Status when promoted"; give the table a
   caption.
9. MED - c27 with F9: shown from the authoring date to effective_to; a
   version with no dated changelog entry is refused by validation (question
   D3); a retroactive turn-off never foreshadows; a collection-level
   turn-off shows once on the card.
10. LOW - previous/next-period links on the view (question D4).

## Questions these raise for Keith

From the architect:
- **A.** TS-79b's text once earlier quarters exist: reword to "the oldest of
  the original fifteen quarters" (recommended), or add a new edge scenario.
- **B.** Who plants the "reject both" scenario: REQ-GEN-206, built last
  (recommended), or REQ-GEN-203 (needs 211 and 204 first).
- **C.** After "reject both", should still-red readers raise the "a person
  decides" shout? No, where every red is another table's - amends REQ-PIPE-121
  c12 (recommended; the CLI reviewer agrees); or yes, as today.
- **D.** TS-62's new claim window: wider, e.g. 6h (recommended - the default
  view stays quiet), or narrower (holds show, but recent ordinary arrivals may
  be held).

From the CLI UX reviewer:
- **A2.** Exit code when a settlement is recorded but a run or the readers'
  re-check is left owed: REQ-PIPE-163's distinct code (recommended; amends
  built REQ-PIPE-193), or 0 as today.
- **B2.** The readers' re-check in the settlement's warning: an un-keyed
  note (recommended; scripts unaffected), or a keyed line needing
  `--acknowledge`.
- **C2.** Readers held red, in the queue picker: one "Look at one of the N"
  entry per cause (recommended), or each reader as its own indented entry.

From the dashboard UX reviewer:
- **D1.** At 30 datasets, collapse routine rule-promoted-on-green rows into
  one "N promoted automatically on green" (recommended), or show every row.
- **D2.** Split "Nothing held" into Not supplied (top) and Not owed (bottom)
  (recommended), or one group as drafted.
- **D3.** A turn-off version with no dated changelog entry: validation
  refuses it (recommended), fall back to the claim-opening window, or no
  foreshadow.
- **D4.** Previous/next-period links on the composition view: not for now
  (recommended), or yes.
