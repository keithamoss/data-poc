# Calendar close-out batch: for sign-off

Keith - this is the batch with your close-out answers, your 15 follow-up answers and your round 4 answers (all 2026-10-14) folded in, with the round 4 reviews (`review4-findings.md`) folded into REQ-DASH-208, REQ-DASH-209, REQ-GEN-205 and REQ-GEN-206. Since then, REQ-DASH-182's own UX review (`review-182-ux.md`) with your four answers to it, your answers G1 to G3, your answers H1 to H4, and REQ-PIPE-179's own scoper pass (`req-179-own-pass.md`) with your four answers to it, are folded too. TS-63 is now its own requirement, **REQ-GEN-218**. **None of it is signed, and requirements.yaml has not changed.** The full text is in `requirements-draft.yaml` next to this file, with the three overnight reviews (`review-*.md`). Merged with the live register (the draft's versions replacing the register's) it passes `mothman dashboard validate-requirements` (207 requirements, zero errors; re-run 2026-10-14 after the H1 to H4 fold and REQ-PIPE-179's own pass, with REQ-GEN-218 added).

Every answer that took the recommendation now uses the wording already drafted for it, and each is recorded in its requirement's `decisions:` as "Keith, 2026-10-14, close-out QN", "Keith, 2026-10-14, follow-up FN" or "Keith, 2026-10-14, round 4 RN"; each round 4 finding folded is recorded as "round 4 <reviewer> <finding>". **Answers are not sign-off**, so each requirement below still needs your yes.

**New wording you have not seen yet** (each marked "NEW WORDING - for Keith's approval" in the YAML):
- Q11: TS-53 with a person's promote (REQ-GEN-206 criterion 5), and the REQ-GEN-137 criterion 2 amendment.
- Q16: the whole of REQ-DASH-209, the period-composition view.
- Q24: REQ-DASH-208 criteria 5, 8 and 9, the scenario jump carried in the URL.
- Q26: REQ-DASH-180 criterion 27, the "Turning off after <date>" marker.
- Q17 also needed new words: REQ-DASH-204 criterion 15 gives each cause its own line and next step. You chose the option, not the wording.
- Q19 and Q21: the two new pipeline requirements, REQ-PIPE-210 and REQ-PIPE-211.

**New wording from the 15 follow-ups.** Only REQ-DASH-180's carries the YAML marker; the rest are listed here:
- F3 and F15: REQ-DASH-209 criteria 3 and 10 (the person's name), and new criterion 11 (page size).
- F5 and F7: REQ-PIPE-211 criteria 1, 2 and 4 to 7, new criteria 8 and 9, and amendment 27's NEW text.
- F6: REQ-PIPE-210 criterion 7.
- F8: REQ-GEN-206 criteria 16 to 18 (TS-81).
- F9: REQ-DASH-180 criterion 27 reworded, and new criterion 28.
- F10: REQ-DASH-208 criterion 10.
- F11: REQ-GEN-205 criteria 24 and 25.

**New wording from REQ-DASH-182's review and G1, for your approval** (none of it is marked in the YAML; it is listed here in full):
- REQ-DASH-182 criteria 2, 3 and 14: the em dash as the separator - "Not owed — outside its agreed months (Feb, Aug)", "Not expected — <reason>", "Turned off — <reason>", "Not owed yet — owes supplies from <date>". The words are yours, and since H1 so is the dash; REQ-DASH-180 criterion 16's "Turned off — nothing due" follows suit.
- REQ-DASH-182 criterion 8: the frequency words "Yearly", "Twice a year", "Quarterly", "Monthly", otherwise "<N> times a year", and "various days" where the days differ.
- REQ-DASH-182 criterion 9: the row's muted "Inherited from <period>", and the standing-in panel's heading: the kind label alone on the present, "On <date>: <kind label>" on a past date, the reason in .promo-why (your H3).
- REQ-DASH-182 criterion 3: the "Not owed yet" notice's body keeps only "Pick a later date, or reset to the default, using the 📅 In place on control above." (your H2).
- REQ-DASH-182 criterion 11: the SLA tile in the row's form, "Twice a year (Feb, Aug, day 1), by 09:00" (your Q1 example; months now comma-separated where today's tile uses a slash), the reason on a muted second line.
- REQ-DASH-182 criterion 13: a run reads "<kind label>, <first> to <last> (<n> periods)" ("days" for a daily dataset), and "(<n> periods so far)" while it is open.
- REQ-DASH-209 criterion 14: "Previous period: <period name>" and "Next period: <period name>"; "Previous day: <date>" and "Next day: <date>" for a daily collection.

**New wording from REQ-PIPE-179's own pass, for your approval:**
- REQ-PIPE-179 criteria 20, 36, 37, 38, 40 and 41, as listed in `req-179-own-pass.md` ("New wording that needs your approval"). Your Q2 approved the substance of 36 and 37; the words are still for your yes.
- REQ-PIPE-179 criterion 34 (your Q3): one row per dataset, reading "<dataset> - <n> received while turned off, earliest <date>", as REQ-DASH-180's quiet line reads; N in "Received while turned off (N)" counts supplies.
- REQ-GEN-218: the whole requirement, though criteria 1 to 5 carry criterion 39's words; criterion 7 and amendments 45 to 47 are new.

## Scoper passes, honestly

- **Round 4 reviews (architect, CLI UX, dashboard UX), 2026-10-14:** REQ-DASH-208, REQ-DASH-209, REQ-PIPE-210 and REQ-PIPE-211 (and REQ-GEN-207, now signed). The findings for 208 and 209, and those touching 205 and 206, are folded. The findings for 210 and 211 are not: those two wait on running-thoughts #95.
- **REQ-PIPE-179:** the joint 2026-10-13 pass with REQ-PIPE-163 and REQ-DASH-182, then its own delivery-scoper pass, 2026-10-14 (`req-179-own-pass.md`), with your four answers folded.
- **REQ-DASH-182:** the joint 2026-10-13 pass, then its own dashboard UX review, 2026-10-14 (`review-182-ux.md`), with your answers to it and H1 to H3 folded.
- **REQ-GEN-218 (new):** drafted by delivery-scoper on 2026-10-14 from REQ-PIPE-179 criterion 39. Not reviewed as a requirement of its own; its content was reviewed in round 3 as criterion 39 (architect A4, A5 and E21).
- **Neither that pass nor one of its own:** REQ-DASH-180.
- The rest had a scoper pass and the round 3 reviews.

## Build order

The round 4 architect's order (H5), which REQ-GEN-203's sign-off already follows:

1. REQ-GEN-207 (signed)
2. REQ-PIPE-202 (signed)
3. REQ-PIPE-211
4. REQ-GEN-203 (signed)
5. REQ-DASH-204
6. REQ-PIPE-210
7. REQ-DASH-182
8. REQ-PIPE-163
9. REQ-PIPE-179
10. REQ-DASH-180
11. REQ-DASH-208
12. REQ-DASH-209
13. REQ-GEN-205
14. REQ-GEN-218 (new, TS-63)
15. REQ-GEN-206

REQ-DASH-208 and REQ-DASH-209 must come before the first REQ-GEN-205 or 206 bootstrap, because TS-55's chip opens 209's view. REQ-GEN-206 also comes after REQ-PIPE-211 because of TS-81 (F8): planted there, TS-81 is observed with the fix in place. Running-thoughts #95 has to be signed before REQ-DASH-204, 210 and 211 are built, and so before 206's TS-81 Expect can be written.

REQ-GEN-218 (TS-63) must come after REQ-DASH-180, because its register entry quotes 180's quiet line and marker; that was your Q1 on REQ-PIPE-179's own pass. Placing it after REQ-GEN-205 rather than straight after 180 is provisional: it follows the recommended answer to the new question on TS-63's scenario links (below), because the link that shows the marker needs REQ-GEN-205 criterion 12. If you choose option B there, it moves up to straight after REQ-DASH-180. Either way REQ-GEN-207's dry run has already sized room for TS-63, and each of 205 and 218 checks its claims against the other's where it is already planted.

## The requirements, in build order

**REQ-GEN-207 (must): grow the Child Protection history earlier, once.**
- **Story:** add quarters before 2023, sized by a dry run of the collision check, so each new scenario has a quarter of its own and no planted scenario moves.
- **What changed:** you chose option A (Q1). It is its own requirement, built first, and today's quarters stay byte-identical.
- The dry run now counts what your other answers added: Child Protection lead-in quarters (Q3), TS-50's era and lead-ins (Q12), and every period the confirmed correction claims.
- TS-62 is left out of the dry run because it is on Birth Registrations (Q7).
- **Follow-ups:** the dry run now counts TS-81, the Child Protection pair with both files rejected (F8). TS-53 is on Birth Registrations (F12), so it is not counted. TS-62's effective date is checked by REQ-GEN-205 on every generation, not by this dry run (F11).
- The build-order decision now places the three new requirements.
- **Open:** nothing.

**REQ-PIPE-202 (should): widen cp_clients' file pattern.**
- **Story:** two Client Register files in one delivery are recognised as a contested pair.
- **What changed:** criterion 13 is new (Q22). The Synthetic-mode picker lists a two-file arrival marked "two files for one table", and refuses when it is picked, naming both files.
- **Open:** nothing.

**REQ-GEN-203 (should): TS-42 and TS-80.**
- **Story:** one contested Client Register pair that a later file supersedes, and one that a scripted person settles, both on the real page.
- **What changed:**
  - Criterion 4 (Q3): the Child Protection generator gains green targeting with lead-in quarters, as REQ-GEN-185 did for Birth Registrations.
  - Criterion 5 (Q1): both scenarios and their lead-ins go in grown quarters.
  - The old criteria 4 to 11 are now 6 to 13.
- **Open, but not a question to you before:** TS-80's outcome (the stray test file rejected, the real extract kept) is still the scoper's proposal. Say if you want it otherwise.

**REQ-DASH-204 (must, Q20): a reader turned red by another table says so at the top of its page.**
- **Story:** a data team leader is sent to the one decision or arrival that clears the red.
- **What changed:**
  - **All causes (Q17):** the line now covers every cause rooted in another table: two files for one table, could not be loaded, held with no period, overdue, and waiting on a decision. It never covers not-yet-due.
  - **Wording (new):** criterion 15 gives each cause its own wording and next step, for example "Red because <dataset>'s supply for <period> is overdue".
  - **The reader's own item (Q19, page half):** criterion 16 makes it say that nothing needs deciding on this supply, and what re-checks it.
  - **Collection level (Q18):**
    - criterion 17: the causing dataset's notice ends "Affects <reader links>";
    - criterion 18: a quiet note under each reader's row, and one line per cause on the collection card.
  - **After settlement (Q21):** criterion 7 names REQ-PIPE-211's re-check as what runs the checks again.
- **Open, a build-time check:** whether every cause already has a notice on the causing dataset's page to end with "Affects". The contested banner does; the others are to be confirmed, and any cause with no notice comes back to you rather than getting a new banner.

**REQ-PIPE-210 (NEW, should, unreviewed): the terminal queue says the same as the page.**
- **Story:** a reader whose red is wholly another table's says nothing needs deciding on it, and is listed beneath that table's own item in the queue. One function decides this for both the page and the terminal.
- A reader with a failing check of its own is never told this.
- Its own decisions stay available.
- **Follow-up F6:** criterion 7. A reader listed beneath its cause is not counted, in the queue or in `mothman supply queue`, so the count is the number of things to decide. A reader with a failing check of its own is still counted.
- **MoSCoW (F14):** should.
- **Open:** the two questions F6 raised (set B) now wait on running-thoughts #95.

**REQ-PIPE-211 (NEW, must, unreviewed): ending a contest re-checks its readers, whatever the outcome.**
- **Story:** after "reject both" (and any other settlement), the readers' contested results are re-evaluated through the one knock-on handler. Otherwise they stay red for good.
- **Follow-ups:**
  - F5: a pair ended by a later file that is not promoted re-checks the readers too (criteria 1, 2, 4, 5, 7 and 9). This makes amendment 27 (REQ-PIPE-121 criterion 1) needed rather than contingent, and changes its NEW text.
  - F7: in the terminal, the readers' re-check runs while you wait. It runs after the settlement's own runs and before the outcome panel, and the warning panel names it beforehand (criterion 8).
  - F8: the "reject both" scenario, TS-81, is planted by REQ-GEN-206, not here. The reasons are under REQ-GEN-206 below.
  - F14: must.
- It amends REQ-PIPE-193 criterion 23 (amendment 43, unchanged by F5) and REQ-PIPE-121 criterion 1 (amendment 27, revised).
- **Open:** an architect check only. Do REQ-PIPE-121 criteria 9 and 15, worded for a decision and a promotion, need amending for a contest ended by an arrival?

**REQ-DASH-182 (must): owed-nothing rows and the delivery time in force.**
- **Re-folded 2026-10-14** after its own UX review (`review-182-ux.md`) and your four answers. Now 15 criteria.
- **Finding 1 did not reproduce as stated.** In a real browser, cp-case-workers on 2025-06-15 and 2026-06-15 shows no "No data". The false "No data" that did reproduce (an early-arriving supply, post-build-review #178) is fixed and recorded on REQ-DASH-054. So the reviewer's staleness criterion is not added. Instead, criterion 15 is a regression guard: a period the dataset owes nothing in, by participation or not_expected, never reads as stale or "No data". It has a real-browser test that passes today, plus a tests-js test for not_expected. REQ-DASH-180 criterion 5 keeps only the turned-off case (your Q2).
- **Q1 (criterion 11):** the SLA tile names the dataset's own months and frequency, with the reason on a muted line. The draft now says "SLA tile" everywhere, as the page does, and so does REQ-DASH-180 criterion 16.
- **Q3 (criterion 3):** "Not owed yet — owes supplies from <date>" replaces the "Nothing had been supplied by this date" heading, and the SLA tile reads the same.
- **Q4 (criterion 14):** the labels are unchanged on every page, including REQ-DASH-209's "Not owed" group.
- **The reviewer's proposals, folded as criteria:**
  - what a quiet row looks like (12);
  - how runs are worded and counted (13);
  - the standing-in panel's heading (9);
  - one function for kind, label and reason (14);
  - both days-before forms tested (7);
  - the frequency words (8);
  - the scope of criterion 1 (1);
  - two NFRs: words, never colour alone; a cold-loaded past-date link.
- **REQ-DASH-054 added as a dependency.** Criterion 7 rewords built behaviour (today's tile reads "due N days before each date, by 22:00"). The terminal's `mothman schedule show` is flagged for delivery-cli-ux, not folded.
- **Your H1 to H3 (2026-10-14), folded:**
  - H1: the em dash in every label (criteria 2, 3 and 14), and REQ-DASH-180 criterion 16's "Turned off — nothing due" with it.
  - H2: the "Not owed yet" notice keeps only its way-back sentence and drops "There is no QA run within the accepted freshness window" (criterion 3).
  - H3: the standing-in heading reads "On <date>: <kind label>" on a past date, the kind label alone on the present, and the reason in .promo-why (criterion 9). The substituted heading is unchanged.
  - Each is a decision citing "Keith, 2026-10-14, H<N>"; the three open questions are removed.
- **Open:** nothing.

**REQ-PIPE-163 (must): placing a held supply.**
- **What changed:**
  - Q25: criteria 35 and 36 are kept.
  - Q23: criterion 16's period chooser now also picks a settlement's re-file target, and criterion 42 amends REQ-PIPE-193 criterion 19 (amendment 42 below).
  - Q27: the REQ-DASH-175 amendment, "Placed in <period>", is presented with this requirement (amendment 2 below; REQ-DASH-175 is unsigned).
- **Open, a note rather than a question:** criterion 26 names re-check, which does nothing until REQ-PIPE-164 is built.

**REQ-PIPE-179 (must): turning a dataset off.**
- **Its own scoper pass (2026-10-14, `req-179-own-pass.md`)** replaced the draft. Criteria 1 to 41, numbers 1 to 39 unchanged. In short: criterion 40 now refuses a turn-off with no `turns_off: true` changelog entry (R8), criterion 41 dates a turn-off and carries it to the build for REQ-DASH-180, criteria 24 and 32 are trimmed, criteria 20, 36 and 37 name the amendments they carry, and criterion 38 is reworded against the built backstop.
- **Your four answers to that pass, folded:**
  - Q1: TS-63 is split out into **REQ-GEN-218**. Criterion 39 is now a pointer that keeps its number ("THE SYSTEM SHALL NOT plant TS-63 ... planted by REQ-GEN-218"), because signed REQ-PIPE-163, 170 and 181 cite criteria by number. REQ-DASH-180, REQ-GEN-207 and REQ-GEN-044 leave the dependencies (they were there for criterion 39 alone), so 179 and 180 no longer depend on each other.
  - Q2: keep is refused on a parked move too (criteria 36 and 37, amendment 40).
  - Q3: the terminal's "Received while turned off" group lists one row per dataset with its count and earliest receipt, opening to its supplies (criterion 34, and the SCALE NFR).
  - Q4: turned-off holds stay quiet and kept; retention is plans/running-thoughts.md #77's question, which already says so (added 2026-10-14). PRIVACY NFR updated.
  - Each is a decision citing "Keith, 2026-10-14, own pass Q<N>"; the four open questions are removed.
- **Still in open_questions, none for you:** provisional choices (which correction or entry is "the newest"; a `turns_off` entry with no effective_to; N counting supplies and the row wording in criterion 34), and two build checks for the architect (criterion 19's re-filer before a correction is confirmed; criterion 38's `_sources` key).

**REQ-DASH-180 (must): the turned-off dataset on the page.**
- **What changed (Q26, new wording):** criterion 27 adds the "Turning off after <effective_to>" marker. The dataset stays counted in its rollups while it shows. The marker gives way to criterion 4's or 25's wording once either applies.
- **Follow-up F9 (new wording):** criterion 27 now starts the marker on the date the turn-off was authored (its changelog entry's date) and runs it until effective_to. New criterion 28: a turn-off authored after its effective_to shows no marker at all.
- **Your H1:** criterion 16's SLA tile now reads "Turned off — nothing due" (em dash). Criterion 25's "Turning off after <effective_to> - nothing more owed" still has a hyphen; H1 did not name it, so it is left for 180's own sign-off.
- **Open:** the two questions F9 raised (set A: which changelog entry dates a turn-off, and what dates a turn-off declared as a correction) were answered by R8; that fold belongs to REQ-DASH-180's own sign-off.

**REQ-DASH-208 (should): a scenario link lands on what it is about.**
- **What changed (Q24, new wording):**
  - The jump now survives a reload. The scenario id rides in a lowercase `scenario` query parameter, and loading that URL repeats the jump.
  - It is dropped when you navigate away, and cleared if it names nothing on the page (criteria 5, 8 and 9).
  - The REQ-GEN-199 amendment now asserts the text is in view again after a cold reload, and criterion 37 is amended too (amendments 9 and 10 below).
- **Follow-up F10:** criterion 10 makes each chip a real `<a href>` link carrying the as-of date and the scenario parameter. A plain click still jumps without a reload. No signed criterion calls the chip a button, so nothing is amended.
- **Round 4 (dashboard UX 1, 2, 3 and 7; architect M6, L1 and H3):**
  - A link that leads nowhere says so in one line, in the page's existing stale-link notice, rather than landing silently at the top (criteria 7 and 9).
  - Changing the date by any means drops `scenario=` from the URL and clears the jump bar and the mark (criterion 8).
  - The mark is the arrival notice's accent left rule with a label, "<id> · in place on <date>". It is not the 2px accent outline, because that is the page's focus ring. "Until the reader next scrolls" is gone, because the jump's own scroll would remove the mark (criterion 4).
  - The chip behaves as a real link. A plain click is intercepted and every other click is left to the browser (criterion 10). Focus moves to the subject without a second scroll (criterion 1). Back and Forward restore the date without scrolling again (new criterion 12).
  - The parameter name is read case-insensitively, and its value is matched against the panel's own ids before it is used anywhere (new criterion 11).
  - REQ-DASH-209's table is in the list of subjects (criterion 2). It joins when 209 is built, and 209 is not made a dependency, because 209 already depends on this one.
  - New wording, for your approval: criteria 4, 7, 11 and 12.
- **Open:** nothing.

**REQ-DASH-209 (NEW, should; Q16; round 4 reviewed): the period-composition view.**
- **Story:** one view per period of a collection, with one row per dataset saying Promoted, Inherited from <period>, Substituted from <period>, Not supplied or Not owed. Each row shows receipt, when it was decided, who decided, reason, and the status it was promoted on.
- **Follow-ups F1 to F4, F14 and F15:** as before (own address, every collection, the person's name, every dataset listed, should, page size measured).
- **Round 4, your answers:**
  - R6: every row is shown open, and nothing collapses (criterion 4). The cost is thirty rows at thirty datasets.
  - R7: "Nothing held" is split. "Not supplied" (owed: red or waiting) goes at the top and "Not owed" (turned off, not expected, outside agreed months) at the bottom. Each is counted in the opening line, for example "30 datasets: 1 not supplied, 1 substituted, 2 inherited, 25 promoted, 1 not owed" (criteria 1 and 4).
- **Round 4, the reviews:**
  - **Where the rows come from (architect H3):** the per-dataset timelines the build already embeds, looked up with the same lookup as REQ-DASH-198's standing-in pill (`promotionStateOn`). There is no second derivation, and nothing reads a period schema, `_manifest` or a supply row (criterion 2). "Built at build time" becomes "the build embeds the answers and the page looks them up". The timeline entries gain `stands_on`, and each supply's receipt, status when promoted and acknowledgements are embedded once per supply (criterion 9).
  - **The test (H3):** `_manifest` agrees with the slot holds only at the present date. So the test compares the two both ways at the build's date, and holds an earlier date against the decision log's as-at readers (criterion 10).
  - **Amendment 3 to REQ-GEN-045 is dropped (H3).** TS-55's coordinate keeps naming the substituted dataset, and the view is its link's target (criterion 7).
  - **Display names, never an email (M7):** criterion 3.
  - **Route (UX 6):** `#/agency/<a>/collection/<c>/period/<p>?in-place-on=<D>`. Also an h2, a rail, a caption and focus on arrival (new criterion 12), the existing not-found page (new criterion 13), and "<period> had not opened by <date>" (criterion 8).
  - **Link placement (UX 5):** the link goes in each period's label in supply history and on gap and owed-nothing rows, never inside a delivery row. This is how F1's "each period row" is read, because supply history has no period row.
  - **Wording (UX 8; your G2):** criterion 3 says exactly "Decided by <name>" or "Applied automatically by the schedule", the page's own sentences, under a column headed "Status when promoted". "The rule" is not shown.
  - New wording, for your approval: the h2, sub-line and rail in criterion 12.
- **Your G1 (new criterion 14):** previous and next-period links beside the h2. Each is a real `<a href>` to the adjacent period's route and keeps the date on show. The link wording is new (listed above).
- **Your H4:** a link is left out, not disabled, where there is no earlier period or where the next period had not opened by the date on show (criterion 14 as written). Recorded as a decision citing "Keith, 2026-10-14, H4".
- REQ-DASH-182 is added as a dependency, because the "Not owed" group takes its labels from REQ-DASH-182's one function.
- **Open:** nothing.

**REQ-GEN-205 (must): TS-57 to TS-62.**
- **What changed:**
  - Q2: you approve the fictional corrections.
  - Q5: the scripted confirmation lives in a top-level `corrections:` list (criterion 4).
  - Q6: exactly two corrections (criterion 20).
  - Q7: TS-62 is on Birth Registrations, and every correction is dated late (criteria 11 and 21).
  - Q8: one grown quarter's date per shape (criterion 22).
  - Q9: TS-61 stays parked to the end (criterion 23).
  - Q28: criterion 19 is gone. It is built (post-build-review #177, `correction_replay.history_end` and `confirm_due(history_end=)`), and a decision records that. The old criterion 20 (resume) is now 19.
- **Follow-up F11 (new wording):** TS-62's correction adds a new Birth Registrations daily version near the end of the history. It has a different claim window and stays pending (criteria 9 and 24).
- **Round 4, your answer R1:**
  - TS-62's version takes effect after 2026-09-08, TS-47's following day, which keeps it clear of TS-47's four-hour window (criterion 25).
  - For a version-level correction, criterion 10 claims only the days its impact preview says it would change, plus one either side.
  - Before the rebuild, the impact preview must show that TS-43 to TS-46 do not move, including TS-46's last day, 2026-09-22 (new criterion 26).
  - The new claim window is about six hours against today's four, so the default view stays quiet (criterion 24). It must pass REQ-PIPE-134's overlap gate (new criterion 27).
- **Round 4, architect M4:**
  - A pending correction still files every later arrival under the new version when it arrives. So the narrowed claim counts arrivals received on or after the effective date, not only supplies the correction would move.
  - M4's blanket refusal ("refuse a version taking effect on or before any other Birth Registrations scenario's dates") is not taken as worded. TS-44 to TS-46 lie after 2026-09-08, so it would refuse what R1 chose. The narrowed claim refuses only where a filing actually changes.
  - **M4's other point is WITHDRAWN by your G3 (option B).** A replay confirms everything due, as today, unless the script says pending. Criteria 4, 5 and 6 are back to their wording before the round 4 fold:
    - a confirmation with no keeps is refused again;
    - a correction with no entry is confirmed.
    Criterion 28 (REQ-PIPE-181's confirm entry) is removed, and amendment 44 is dropped. Two things are new:
    - criterion 6 names every route that confirms;
    - criterion 16's test covers both the bootstrap and the resumed bootstrap.
    This is because TS-62 stays pending only while each route reads its entry. The accepted cost: a forgotten "pending" entry would confirm silently.
- **Open:** nothing for you. Build-time checks: whether a correction declared for an added synthetic version is staged as a correction, and whether REQ-PIPE-169's impact preview reports arrivals filed under the new version, not only moves.
- **Not put to you:** cp-case-workers as TS-61's blocker is still the main session's provisional choice.
- **Since REQ-GEN-218:** REQ-GEN-205 is signed (2026-10-14), so its criterion 10's "REQ-PIPE-179's TS-63 correction" is re-pointed by amendment 47 rather than edited here; the draft's copy is left exactly as signed.

**REQ-GEN-218 (NEW, must, provisional; your Q1 on REQ-PIPE-179's own pass): TS-63, a dataset turned off for two quarters.**
- **Story:** the synthetic history shows a dataset turned off for a while and turned back on, through the same declared-correction gate a real turn-off goes through: the marker before it, a supply for a quarter it still owed filed there, a supply received inside the gap held quietly, and the gap's owed-nothing rows.
- **What it carries from REQ-PIPE-179 criterion 39:** cp-carers split off the shared `*cp_participation` alias (criterion 1); the turn-off declared as a correction dated before the gap, approved by your real identity, with a fictional reason and a `turns_off: true` changelog entry (criterion 2); its quarters in REQ-GEN-207's grown history, refused on collision (criterion 3); two injected supplies, one filed to the last owed quarter and one held as turned off (criterion 4); the register entry rewritten to the real calendar, quoting 180's quiet line and marker (criterion 5).
- **New:** a unit test for TS-63, which REQ-PIPE-170 criterion 23 asks of TS-57 to TS-64 (criterion 6); the three citations re-pointed (criterion 7, amendments 45 to 47). It clears no unmet entry: REQ-PIPE-170's lists TS-63 only as moved.
- **Decisions carried, each with its source:** your Q1 split; 2026-10-13 set 2 Q8 (TS-63 with the turn-off work); declared as a correction; grow earlier; close-out Q4 (dated before the gap) and Q2 (your identity); architect A4 and E21; R8 (the marker dates from the correction).
- **Provisional, not put to you:** cp-carers as the dataset (carried); must.
- **Open:** one question for you, on its scenario links (below).

**REQ-GEN-206 (should): the rest of REQ-GEN-136 and 137, plus #175.**
- **What changed:**
  - Q10 (criterion 8): TS-48 is recorded as demonstrated by TS-75; TS-49 and TS-51 are not planted, with your reason. This amends REQ-GEN-136 criteria 5 and 9.
  - Q11, new wording (criterion 5): TS-53 is reject, then un-supersede, then a scripted person's promote, amending REQ-GEN-137 criterion 2.
  - Q12 (criterion 6): TS-50 is planted in full.
  - Q13: TS-54 rides TS-76.
  - Q14 (criterion 11): TS-47 gets a green following day.
  - Q15 (criterion 15): REQ-GEN-199 criterion 9 is reworded.
  - Q16 (criterion 4): TS-55's chip opens REQ-DASH-209.
- **Follow-ups:**
  - F8 (new wording): TS-81 is a Child Protection pair whose two files a scripted person rejects, planted in one grown quarter (criteria 16 to 18). It belongs here rather than on REQ-PIPE-211 for three reasons:
    - planting a scenario is generator work;
    - this requirement is built last, after REQ-PIPE-211, so TS-81's Expect is written against the fix rather than the defect;
    - on REQ-PIPE-211 it would make a must requirement wait for grown quarters and a full bootstrap.
    REQ-GEN-203 was also considered and rejected, because it is built before REQ-PIPE-211.
  - TS-81's shape is the scoper's provisional reading of "another grown quarter": no green targeting, no lead-ins, and the settlement the day after arrival. Say if you want it otherwise.
  - F12: TS-53 is on Birth Registrations (criterion 5).
  - F13: REQ-GEN-136 criterion 4 keeps its wording. Its unmet entry is cleared, with evidence naming TS-75, as a register change when this is built rather than as an amendment (criterion 8).
- **Round 4:**
  - TS-81 stays here. The architect agrees (M3 and question B), and this requirement is built last.
  - R2 (the still-failing shout after "reject both") is not folded here. It is running-thoughts #95's question now, and TS-81 shows whatever #95 decides.
  - TS-81's links now say that each reader's page carries REQ-DASH-204's line in its criterion 15 wording (criterion 18). The readers' status, and that wording, follow #95's outcome. Neither is stated as red. #95's draft proposes replacing criterion 15's per-cause wording with one line, "No promoted <dataset> for <period>", so the quoted text depends on #95 too.
  - REQ-DASH-204 is added as a dependency.
  - R3 (TS-79b's reword) belongs to REQ-GEN-207, which is signed.
- **Open:** the build-time check on #175's 8 September supply. TS-81's Expect also waits on #95, which is not a question to you now.

## Proposed amendments to signed requirements (complete)

**47 amendments numbered, 45 standing, to 26 requirements**, every one with exact wording: the 9 drafted on the morning of 2026-10-14, plus 38 drafted since. Amendments 45 to 47 are new with REQ-GEN-218: they re-point REQ-PIPE-170 criterion 23 (and its unmet entry), REQ-GEN-207 criterion 2 and REQ-GEN-205 criterion 10 (signed since) from REQ-PIPE-179 to REQ-GEN-218. Two are now DROPPED: amendment 3 (round 4 architect H3) and amendment 44, REQ-PIPE-170 criterion 31 (your G3, option B). One target, REQ-DASH-175, is unsigned. Each is also recorded on the requirement that carries it, as a "PROPOSED AMENDMENT WORDING" decision. Every OLD text is copied from the live requirements.yaml. `<date built>` is the one placeholder: it is the date the amendment lands, written the way the register already dates its amendments.

Four kinds of entry need you more than the rest:

- **Not promised by the draft.** Found by reading the targets: REQ-PIPE-141 criterion 12 (amendment 33) and REQ-PIPE-170 criterion 26 (amendment 39). Without them, each contradicts REQ-PIPE-179. Since REQ-PIPE-179's own pass, criteria 20 and 37 name them. REQ-PIPE-170 criterion 28 (amendment 40) stretches REQ-PIPE-179 criterion 36 to the second place keep is offered; you chose that extension (own pass Q2), and criterion 36 now says it.

- **Contingent, and settled.** REQ-GEN-045 criterion 1 (amendment 3) was a "check at build" item for the architect. Round 4 (H3) found it is not needed, so it is DROPPED. REQ-PIPE-121 criterion 1 (amendment 27) was contingent too. Since your follow-up F5 it is needed, and its NEW text changed.

- **Changed by the 15 follow-ups:** only amendment 27 (F5). F8 and F11 needed no amendment: TS-81 is a new scenario that no signed criterion promises, and criterion 25 keeps REQ-GEN-199's quotes where they are. Amendment 43 is unchanged: a later file superseding a pair is not a settlement, so amendment 27 carries that case.

- **Removes a guarantee on purpose.** Each is marked below and follows an answer you already gave.

- **No change needed.** Seven promises turned out to need nothing once the target was read. They are listed at the end.

### REQ-DASH-155 (signed 2026-10-06, built): The exhausted-schedule notice says how many supplies are waiting and since when

**1. REQ-DASH-155 criterion 1**. Carried by REQ-DASH-180 criterion 22.

- Old: "WHERE the dashboard shows the exhausted-schedule notice, THE SYSTEM SHALL state how many supplies are held because a schedule ended and the receipt date of the earliest of them."
- New: "WHERE the dashboard shows the exhausted-schedule notice, THE SYSTEM SHALL state how many supplies are held because a schedule ended - each hold's label worked out from the configuration in force on the in-place-on date (REQ-PIPE-179 criterion 18), so that a supply held as turned off is not counted - and the receipt date of the earliest of them. AMENDED <date built> by REQ-DASH-180 criterion 22."
- Why: the backlog counts only holds that adding dates would file.
- Built behaviour: BUILT CODE CHANGES (the notice's backlog count reads the recorded flag today); NOT STATED ELSEWHERE IN REQ-DASH-180, so its build needs a test of its own.

### REQ-DASH-175 (UNSIGNED, not_started): The dashboard says when a supply was placed by hand, or re-checked after we fixed a check

**2. REQ-DASH-175 criterion 12** (drafted this morning). Carried by REQ-PIPE-163 presented with it (decision, close-out Q27).

- Old: "THE SYSTEM SHALL describe a placement and a re-check in words wherever a past decision is described - 'placed in <period>', 're-checked' - and SHALL NOT show the raw operation name."
- New: "THE SYSTEM SHALL describe a placement and a re-check in words wherever a past decision is described - 'placed in <period>', 're-checked' - recognising a placement as a person's re-file whose from-period is empty (REQ-PIPE-163 criterion 2), and SHALL NOT show the raw operation name or describe a placement as a re-file."
- Why: Keith, close-out Q27: a placement is a re-file underneath, so the page must recognise it.
- Built behaviour: UNSIGNED and not_started - no built behaviour; it is a redraft rather than an amendment.

### REQ-GEN-045 (signed 2026-09-22, built): A generated scenario map says where each scenario can be seen

**3. REQ-GEN-045 criterion 1**. Carried by REQ-DASH-209 criterion 7.

- Old: "THE SYSTEM SHALL generate a map naming, for each injected scenario, the dataset, the supplies it produced, the period and the in-place-on date at which that scenario can be seen.
"
- New: "THE SYSTEM SHALL generate a map naming, for each injected scenario, the dataset - or, for a scenario about a whole period of a collection (REQ-DASH-209 criterion 7), the collection - the supplies it produced, the period and the in-place-on date at which that scenario can be seen.
 AMENDED <date built> by REQ-DASH-209 criterion 7."
- Why: criterion 1 requires every coordinate to name a dataset; a coordinate naming only a collection and a period would break it.
- Built behaviour: BUILT CODE CHANGES if needed (the scenario map's coordinate); built and tested by REQ-DASH-209 criterion 7.
- **Note:** DROPPED (round 4 architect H3, 2026-10-14). TS-55's coordinate keeps naming the substituted dataset, with the composition view as its target (REQ-DASH-209 criterion 7), so no change is needed. It is kept here, struck, so the numbering holds.

### REQ-GEN-136 (signed 2026-10-04, built): Every arrival-driven shape of the option A and period-closing batch is planted in the synthetic history

**4. REQ-GEN-136 criterion 5** (drafted this morning). Carried by REQ-GEN-206 criterion 8.

- Old: "THE SYSTEM SHALL plant a correction whose re-check after its partner's promotion still fails, producing the decision log's large shout (REQ-PIPE-121)."
- New: "THE SYSTEM SHALL register, and SHALL NOT plant, TS-49 - a correction whose re-check after its partner's promotion still fails, producing the decision log's large shout (REQ-PIPE-121) - which Keith left unplanted (2026-10-11, confirmed 2026-10-14) because it needs named red cross-table targets and referential closure across six tables."
- Why: Keith, close-out Q10.
- Built behaviour: NO BUILT BEHAVIOUR CHANGES: criterion 5 is unmet.
- **Note:** REMOVES A GUARANTEE, deliberately: TS-49 will not be planted (Keith, Q10).

**5. REQ-GEN-136 criterion 9** (drafted this morning). Carried by REQ-GEN-206 criterion 8.

- Old: "THE SYSTEM SHALL plant a promoted supply whose cross-table result goes red when a sibling arrives later (REQ-DASH-126)."
- New: "THE SYSTEM SHALL register, and SHALL NOT plant, TS-51 - a promoted supply whose cross-table result goes red when a sibling arrives later (REQ-DASH-126) - which Keith left unplanted (2026-10-11, confirmed 2026-10-14) because it needs named red cross-table targets and referential closure across six tables."
- Why: Keith, close-out Q10.
- Built behaviour: NO BUILT BEHAVIOUR CHANGES: criterion 9 is unmet.
- **Note:** REMOVES A GUARANTEE, deliberately: TS-51 will not be planted (Keith, Q10).

### REQ-GEN-137 (signed 2026-10-04, built): The batch's person decisions, and the _manifest's three kinds of table, are planted in the synthetic history

**6. REQ-GEN-137 criterion 2** (drafted this morning). Carried by REQ-GEN-206 criterion 14.

- Old: "THE SYSTEM SHALL plant Keith's worked un-supersede case: a good file superseded by a bad later one; a person rejects the bad one and un-supersedes the good one, which is re-checked and promoted by the gate (REQ-PIPE-120)."
- New: "THE SYSTEM SHALL plant Keith's worked un-supersede case: a good file superseded by a bad later one; a person rejects the bad one and un-supersedes the good one, which is re-checked (REQ-PIPE-120), left waiting by the gate, and then promoted by a person."
- Why: Keith, close-out Q11 (option B): as built, the gate does not promote the un-superseded file without a further decision.
- Built behaviour: NO BUILT BEHAVIOUR CHANGES: criterion 2 is in REQ-GEN-137's unmet list; REQ-GEN-206 criterion 5 plants it.

### REQ-GEN-196 (signed 2026-10-13, built): Birth Registrations' generated history has a contested pair for every way a settlement can go, each settled by a scripted person - a duplicate send, a next day's file sent early, a later file chosen, a stray test file (one that loads and one that does not), both files rejected, and one file re-filed while the other is rejected

**7. REQ-GEN-196 a new decision**. Carried by REQ-PIPE-202 criterion 12.

- Old: "(none - decision 1 stays as history; this appends a decision. Decision 1 reads: "BIRTH REGISTRATIONS, NOT CHILD PROTECTION (2026-10-13, carried from REQ-PIPE-193): Child Protection's arrival patterns are exact filenames and cannot admit two files for one table (TS-34 and TS-42 record why), while birth_registrations_[^/]+\.csv admits two today. No pattern is widened; TS-42 stays not injectable.")"
- New: "SUPERSEDED IN PART BY REQ-PIPE-202 (Keith, 2026-10-13; recorded <date built> by REQ-PIPE-202 criterion 12): decision 1's "No pattern is widened; TS-42 stays not injectable" no longer holds - cp-clients' arrival pattern is `cp_clients(_[^/]+)?\.csv`, so TS-42 is planted by REQ-GEN-203. Every other Child Protection pattern stays exact, so TS-34 stays not injectable, and this requirement's own pairs stay on Birth Registrations."
- Why: a reader of REQ-GEN-196 must not take "no pattern is widened" as current.
- Built behaviour: TEXT ONLY - a decision, no criterion and no code.

### REQ-GEN-199 (signed 2026-10-13, built): The generated history has a scenario for each way the as-at panel and qualifier can read - awaiting then rejected, a substitution later removed, one later replaced, a supply promoted out of order, and cp-case-workers' inheritance named - each linked from the test-scenarios panel

**8. REQ-GEN-199 criterion 9** (drafted this morning). Carried by REQ-GEN-206 criterion 15.

- Old: "THE SYSTEM SHALL record in TS-76's register entry, as part of what TS-76 shows, the state cp-clients and cp-carers are left in for TS-76's quarter once the substitution is removed - promoted and red, permanently, as the delivery-architect found (H1) - and what cp-clients' and cp-carers' pages read before the substitution, while it stands and after it ends."
- New: "THE SYSTEM SHALL record in TS-76's register entry, as part of what TS-76 shows, the state cp-clients and cp-carers are left in for TS-76's quarter once the substitution is removed - cp-clients promoted amber and cp-carers green, as the first bootstrapped build showed (post-build-review #174), the cross-table checks reading cp_placements being filed under cp-placements and run for neither in a quarter with no placements supply - and what cp-clients' and cp-carers' pages read before the substitution, while it stands and after it ends."
- Why: Keith, close-out Q15: record what was observed, not what the architect predicted.
- Built behaviour: TEXT ONLY: a register entry's wording.

**9. REQ-GEN-199 criterion 36** (drafted this morning). Carried by REQ-DASH-208 criterion 6.

- Old: "THE SYSTEM SHALL have a needs_deployment real-browser test that, at a 1280x800 viewport, clicks each of this requirement's chips in the test-scenarios panel and asserts that the element holding the text its register Expect quotes is inside the initial viewport without scrolling, then cold-reloads that URL and asserts the same text with zero console errors."
- New: "THE SYSTEM SHALL have a needs_deployment real-browser test that, at a 1280x800 viewport, clicks each of this requirement's chips in the test-scenarios panel and asserts that the element holding the text its register Expect quotes is inside the viewport once the scenario jump (REQ-DASH-208) has brought it there, then cold-reloads that URL and asserts the same text inside the viewport again, with zero console errors."
- Why: Keith, close-out Q24: the jump is carried in the URL, so a reload lands on the subject too.
- Built behaviour: BUILT TEST CHANGES (the strict expected failures naming post-build-review #174 come out as each text comes into view); REQ-DASH-208 criterion 6.
- **Note:** RELAXES "without scrolling" to "once the jump has brought it there" - Keith chose a page fix that scrolls (Q24); the cold-reload assertion is STRENGTHENED to the viewport.

**10. REQ-GEN-199 criterion 37** (drafted this morning). Carried by REQ-DASH-208 criterion 6.

- Old: "IF the Expect's element is outside the initial 1280x800 viewport, THEN that SHALL be recorded as a finding against the page, and SHALL NOT be resolved by loosening the assertion or the Expect."
- New: "IF the Expect's element is outside the 1280x800 viewport once the scenario jump (REQ-DASH-208) has run, THEN that SHALL be recorded as a finding against the page, and SHALL NOT be resolved by loosening the assertion or the Expect."
- Why: follows criterion 36.
- Built behaviour: TEXT ONLY beyond criterion 36's test change.

### REQ-GEN-205 (signed 2026-10-14, not_started): TS-57 to TS-62

**47. REQ-GEN-205 criterion 10**. Carried by REQ-GEN-218 criterion 7.

- Old: "THE SYSTEM SHALL count as claimed by each correction, once however many scenarios ride it, every period whose slot a declared change alters together with the period before and the period after it - except that for a version-level change (TS-62's), only the days whose filing it would change, as its impact preview (REQ-PIPE-169) computes them, for supplies received before its effective date and for every arrival received on or after it, together with the day before and the day after each; SHALL check that claim against every injection, every post-generation placement (TS-52, TS-79a, TS-79b) and REQ-PIPE-179's TS-63 correction; and IF it meets a period another claims, THEN generation SHALL refuse naming both, and SHALL NOT shift either or relax the rule."
- New: "THE SYSTEM SHALL count as claimed by each correction, once however many scenarios ride it, every period whose slot a declared change alters together with the period before and the period after it - except that for a version-level change (TS-62's), only the days whose filing it would change, as its impact preview (REQ-PIPE-169) computes them, for supplies received before its effective date and for every arrival received on or after it, together with the day before and the day after each; SHALL check that claim against every injection, every post-generation placement (TS-52, TS-79a, TS-79b) and TS-63's correction (REQ-GEN-218) where it is already planted; and IF it meets a period another claims, THEN generation SHALL refuse naming both, and SHALL NOT shift either or relax the rule. AMENDED <date applied> by REQ-GEN-218 criterion 7."
- Why: as amendment 45. "Where it is already planted" because REQ-GEN-205 may be built before REQ-GEN-218; REQ-GEN-218 criterion 3 makes the check the other way.
- Built behaviour: TEXT ONLY. REQ-GEN-205 is not built. Applied with amendment 45, together with a decision appended to REQ-GEN-205: "TS-63 RE-POINTED (Keith, 2026-10-14, REQ-PIPE-179 own pass Q1): TS-63 is planted by REQ-GEN-218, built after REQ-DASH-180; criterion 10 checks against its correction where it is already planted. Recorded <date applied> by REQ-GEN-218 criterion 7." Its 2026-10-13 decision "TS-63 IS NOT HERE" stays as history.

### REQ-GEN-207 (signed 2026-10-14, not_started): grow the Child Protection history earlier, once

**46. REQ-GEN-207 criterion 2**. Carried by REQ-GEN-218 criterion 7.

- Old: "THE SYSTEM SHALL size the growth by a dry run of the generator's collision refusal over every Child Protection scenario this batch plans, with every period each claims - TS-42 and TS-80 with the lead-in quarters their green targets need (REQ-GEN-203), the confirmed correction carrying TS-57 to TS-61 with every period it claims (REQ-GEN-205; TS-62, like TS-53, is on Birth Registrations), TS-63 and its correction (REQ-PIPE-179), and TS-50 with its lead-ins and green-replacement era, TS-55 and TS-81, the pair with both files rejected (REQ-GEN-206) - adding the fewest whole years that leave the dry run with no refusal, and SHALL record the count and the dry run's output in this requirement's evidence."
- New: "THE SYSTEM SHALL size the growth by a dry run of the generator's collision refusal over every Child Protection scenario this batch plans, with every period each claims - TS-42 and TS-80 with the lead-in quarters their green targets need (REQ-GEN-203), the confirmed correction carrying TS-57 to TS-61 with every period it claims (REQ-GEN-205; TS-62, like TS-53, is on Birth Registrations), TS-63 and its correction (REQ-GEN-218), and TS-50 with its lead-ins and green-replacement era, TS-55 and TS-81, the pair with both files rejected (REQ-GEN-206) - adding the fewest whole years that leave the dry run with no refusal, and SHALL record the count and the dry run's output in this requirement's evidence. AMENDED <date applied> by REQ-GEN-218 criterion 7."
- Why: as amendment 45.
- Built behaviour: TEXT ONLY. REQ-GEN-207 is not built, and its dry run counts TS-63 and its correction exactly as before. Applied with amendment 45.

### REQ-GHUB-082 (signed 2026-09-28, built): An operator records a filing decision from GitHub or from the terminal, and both write the same entry

**11. REQ-GHUB-082 criterion 1**. Carried by REQ-PIPE-163 criterion 13.

- Old: "THE SYSTEM SHALL accept promote, reject, demote, re-file, substitute, de-substitute, inherit, un-inherit, mark as not supplied, acknowledge, supersede, un-supersede, excuse lateness and withdraw excuse as structured filing decisions raised on the GitHub ticket for the SLOT they concern - one dataset in one period, per REQ-PIPE-083 - so that the period a decision applies to comes from the ticket's own identity rather than from anything stated in the body. Every criterion below that says "a filing decision" SHALL mean any one of those fourteen. AMENDED 2026-10-05 by REQ-PIPE-132 criterion 13 (mark as not supplied), REQ-PIPE-122 criterion 22 (acknowledge) and REQ-PIPE-120 criterion 9 (supersede, un-supersede), and 2026-10-11 by REQ-PIPE-161 criterion 13 (excuse lateness, withdraw excuse). Keep, and the confirmation of a calendar correction's moves, are filing decisions too, offered on the terminal route only (criterion 3) - AMENDED 2026-10-11 by REQ-PIPE-170 criterion 11. Settling a contested pair (choose-file) is a filing decision too, offered on the terminal route only (criterion 3) - AMENDED 2026-10-13 by REQ-PIPE-193 criterion 29."
- New: "THE SYSTEM SHALL accept promote, reject, demote, re-file, substitute, de-substitute, inherit, un-inherit, mark as not supplied, acknowledge, supersede, un-supersede, excuse lateness and withdraw excuse as structured filing decisions raised on the GitHub ticket for the SLOT they concern - one dataset in one period, per REQ-PIPE-083 - so that the period a decision applies to comes from the ticket's own identity rather than from anything stated in the body. Every criterion below that says "a filing decision" SHALL mean any one of those fourteen. AMENDED 2026-10-05 by REQ-PIPE-132 criterion 13 (mark as not supplied), REQ-PIPE-122 criterion 22 (acknowledge) and REQ-PIPE-120 criterion 9 (supersede, un-supersede), and 2026-10-11 by REQ-PIPE-161 criterion 13 (excuse lateness, withdraw excuse). Keep, and the confirmation of a calendar correction's moves, are filing decisions too, offered on the terminal route only (criterion 3) - AMENDED 2026-10-11 by REQ-PIPE-170 criterion 11. Settling a contested pair (choose-file) is a filing decision too, offered on the terminal route only (criterion 3) - AMENDED 2026-10-13 by REQ-PIPE-193 criterion 29. Placing a held supply (place) is a filing decision too, offered on the terminal route only (criterion 3) - AMENDED <date built> by REQ-PIPE-163 criterion 13."
- Why: place is a new filing decision, terminal only, and the list is meant to be complete.
- Built behaviour: BUILT CODE CHANGES (filing_decisions.OPERATIONS gains place); built and tested by REQ-PIPE-163 criteria 1, 13 and 36.

**12. REQ-GHUB-082 criterion 3**. Carried by REQ-PIPE-163 criterion 14.

- Old: "THE SYSTEM SHALL write an identical decision-log entry whichever route raised the decision, and SHALL NOT give either route an operation the other lacks, except the confirmation of a calendar correction's moves and the keeps it records, which is offered on the terminal route only (REQ-PIPE-170 criterion 10), and settling a contested pair (choose-file), which is offered on the terminal route only (REQ-PIPE-193 criteria 1 and 16). AMENDED 2026-10-11 by REQ-PIPE-170 criterion 11, and 2026-10-13 by REQ-PIPE-193 criterion 29.
"
- New: "THE SYSTEM SHALL write an identical decision-log entry whichever route raised the decision, and SHALL NOT give either route an operation the other lacks, except the confirmation of a calendar correction's moves and the keeps it records, which is offered on the terminal route only (REQ-PIPE-170 criterion 10), settling a contested pair (choose-file), which is offered on the terminal route only (REQ-PIPE-193 criteria 1 and 16), and placing a held supply (place), which is offered on the terminal route only (REQ-PIPE-163 criteria 14 and 36). AMENDED 2026-10-11 by REQ-PIPE-170 criterion 11, 2026-10-13 by REQ-PIPE-193 criterion 29, and <date built> by REQ-PIPE-163 criterion 14.
"
- Why: place is offered on the terminal route only, so it is a third exception to "neither route lacks an operation".
- Built behaviour: BUILT CODE CHANGES (the GitHub route replies and records nothing for place); built and tested by REQ-PIPE-163 criterion 36.

### REQ-PIPE-053 (signed 2026-09-22, built): A schedule that runs out is loud, and only for its own dataset

**13. REQ-PIPE-053 criterion 10**. Carried by REQ-PIPE-179 criterion 32.

- Old: "WHERE a calendar is an authored date list, THE SYSTEM SHALL warn when fewer than a configured number of future slots remain for a dataset naming it."
- New: "WHERE a calendar is an authored date list, THE SYSTEM SHALL warn when fewer than a configured number of future slots remain for a dataset naming it - counting, for a dataset in a temporary turned-off gap, only the periods it owes once turned back on - and SHALL NOT warn for a dataset turned off for good (REQ-PIPE-179 criterion 25). AMENDED <date built> by REQ-PIPE-179 criterion 32."
- Why: Keith's T6: a supplier turned off for good must not keep the runway warning firing.
- Built behaviour: BUILT CODE CHANGES (runway.calendar_runway); built and tested by REQ-PIPE-179 criterion 25.

**14. REQ-PIPE-053 criterion 15**. Carried by REQ-PIPE-179 criterion 32.

- Old: "WHEN a calendar is low on runway, THE SYSTEM SHALL warn once for that calendar, naming it, its last authored period and how many datasets name it, and SHALL NOT enumerate those datasets."
- New: "WHEN a calendar is low on runway, THE SYSTEM SHALL warn once for that calendar, naming it, its last authored period and how many datasets name it, not counting a dataset turned off for good (REQ-PIPE-179 criterion 25), and SHALL NOT enumerate those datasets. AMENDED <date built> by REQ-PIPE-179 criterion 32."
- Why: the per-calendar count must agree with criterion 10.
- Built behaviour: BUILT CODE CHANGES (the warning's count); built and tested by REQ-PIPE-179 criterion 25.

**15. REQ-PIPE-053 criterion 19**. Carried by REQ-DASH-180 criterion 22.

- Old: "THE SYSTEM SHALL evaluate the exhausted-schedule condition against the in-place-on date currently selected, and SHALL NOT report a schedule as exhausted while viewing a date its calendar covers."
- New: "THE SYSTEM SHALL evaluate the exhausted-schedule condition against the in-place-on date currently selected, and SHALL NOT report a schedule as exhausted while viewing a date its calendar covers, nor report a dataset as exhausted on a date it is turned off (REQ-PIPE-179). AMENDED <date built> by REQ-DASH-180 criterion 22."
- Why: a turned-off dataset owes nothing, so a run-out schedule is not its problem; criteria 16 to 18 render and count the condition this criterion evaluates, so they need no change of their own.
- Built behaviour: BUILT CODE CHANGES (the template's exhausted condition and dataset_status.py); built and tested by REQ-DASH-180 criterion 17.

### REQ-PIPE-064 (signed 2026-09-24, built): When nothing is confidently claimable, hold it for a human

**16. REQ-PIPE-064 criterion 5**. Carried by REQ-PIPE-179 criterion 24.

- Old: "THE SYSTEM SHALL report a held supply as an event needing action, distinguished from an informational one."
- New: "THE SYSTEM SHALL report a held supply as an event needing action, distinguished from an informational one - except a supply held as turned off (REQ-PIPE-179 criterion 24), which SHALL be reported as a quiet count and not as needing action. AMENDED <date built> by REQ-PIPE-179 criterion 24."
- Why: Keith's T3: a supplier still sending files after being asked to stop must not raise a needs-action item each time.
- Built behaviour: BUILT CODE CHANGES (every held supply counts as needing action today); built and tested by REQ-PIPE-179 criteria 24 and 34.
- **Note:** REMOVES A GUARANTEE, deliberately: a turned-off hold is no longer reported as needing action (Keith, T3, 2026-10-10).

**17. REQ-PIPE-064 criterion 8**. Carried by REQ-PIPE-179 criterion 32.

- Old: "THE SYSTEM SHALL count and report outstanding holds together, and SHALL NOT present one element per held supply."
- New: "THE SYSTEM SHALL count and report outstanding holds together, by label - turned off, schedule ended or the plain assignment-rule hold, each worked out from the configuration in force when the count is made (REQ-PIPE-179 criterion 18) - and SHALL NOT present one element per held supply. AMENDED <date built> by REQ-PIPE-179 criterion 32."
- Why: Keith's T4: a hold's label is worked out from current configuration everywhere, counts included.
- Built behaviour: BUILT CODE CHANGES (supply_holds.Tally reads the recorded flag today); built and tested by REQ-PIPE-179 criteria 18 and 26.

### REQ-PIPE-074 (signed 2026-09-26, built): Every filing decision is recorded once, in one append-only log that refuses an anonymous entry

**18. REQ-PIPE-074 criterion 1**. Carried by REQ-PIPE-163 criterion 13.

- Old: "THE SYSTEM SHALL record every filing decision - promote, reject, demote, re-file, mark as not supplied, acknowledge, supersede, un-supersede, excuse lateness, withdraw excuse, keep and choose-file - as an entry in one append-only log, and SHALL NOT keep a second record of any of them anywhere else. AMENDED 2026-10-05 by REQ-PIPE-132 criterion 13, REQ-PIPE-122 criterion 22 and REQ-PIPE-120 criterion 9, and 2026-10-11 by REQ-PIPE-161 criterion 13 and REQ-PIPE-170 criterion 11 (keep; confirming a calendar correction records each re-file, hold and keep it makes as its own entry here), and 2026-10-13 by REQ-PIPE-193 criterion 29 (choose-file - one entry for a settlement, with each file's rejection, supersession or re-file its own entry naming it as the cause)."
- New: "THE SYSTEM SHALL record every filing decision - promote, reject, demote, re-file, mark as not supplied, acknowledge, supersede, un-supersede, excuse lateness, withdraw excuse, keep, choose-file and place - as an entry in one append-only log, and SHALL NOT keep a second record of any of them anywhere else. AMENDED 2026-10-05 by REQ-PIPE-132 criterion 13, REQ-PIPE-122 criterion 22 and REQ-PIPE-120 criterion 9, and 2026-10-11 by REQ-PIPE-161 criterion 13 and REQ-PIPE-170 criterion 11 (keep; confirming a calendar correction records each re-file, hold and keep it makes as its own entry here), and 2026-10-13 by REQ-PIPE-193 criterion 29 (choose-file - one entry for a settlement, with each file's rejection, supersession or re-file its own entry naming it as the cause). And <date built> by REQ-PIPE-163 criterion 13 (place - recorded as a person's re-file from no period, REQ-PIPE-163 criterion 2, so it adds no decision-log action of its own)."
- Why: place is a filing decision and must be in the one log; the note says it is recorded as a re-file so nobody looks for a PLACE action.
- Built behaviour: BUILT CODE CHANGES only through REQ-PIPE-163 criterion 2 (no new action); tested there.

**19. REQ-PIPE-074 criterion 9**. Carried by REQ-PIPE-163 criterion 39.

- Old: "THE SYSTEM SHALL record a re-file as ONE entry carrying a from-slot, a to-slot and one reason, and SHALL NOT express it as a demotion followed by a promotion.
"
- New: "THE SYSTEM SHALL record a re-file as ONE entry carrying a from-slot, a to-slot and one reason, and SHALL NOT express it as a demotion followed by a promotion; WHERE a re-file places a held supply - by the rule (REQ-PIPE-154 criterion 7, REQ-PIPE-179 criterion 19) or by a person placing a supply with an open assignment-rule hold (REQ-PIPE-163 criterion 2) - it SHALL carry no from-slot, and IF a person's re-file names no from-slot for any other supply, THEN THE SYSTEM SHALL refuse it, naming place; and WHERE a confirmed correction holds a supply (REQ-PIPE-170 criterion 8), its re-file SHALL carry no to-slot. AMENDED <date built> by REQ-PIPE-163 criterion 39; the rule's and the correction's one-slot forms were built 2026-10-06 and 2026-10-11 and are stated here for the first time."
- Why: this is the criterion that states the decision log's re-file rule (qa_tools/common/decision_log.py), which REQ-PIPE-163 criterion 39 relaxes for a person's placement; it already omitted two one-slot forms the code accepts.
- Built behaviour: BUILT CODE CHANGES for the person's placement only (decision_log.py's REFILE check); built and tested by REQ-PIPE-163 criterion 39. The rule and correction halves are TEXT CATCH-UP of built behaviour.
- **Note:** Widens what the text says is accepted, but no guarantee is lost: the code already accepted the two one-slot forms, and a person's re-file with no from-slot stays refused except for placing.

### REQ-PIPE-076 (signed 2026-09-26, built): Rejection and un-decide are a person's decisions, and automation defers to a person permanently

**20. REQ-PIPE-076 criterion 7**. Carried by REQ-PIPE-163 criterion 24.

- Old: "WHERE any decision has been recorded against a supply by a person, THE SYSTEM SHALL NOT promote that supply automatically thereafter - EXCEPT un-supersede, re-file and an excuse of lateness or its withdrawal, the person-decisions after which the gate may still promote automatically, and the supersede un-supersede undoes (REQ-PIPE-120 criterion 4, REQ-PIPE-141 criterion 8, REQ-PIPE-161 criterion 19). AMENDED 2026-10-05 by REQ-PIPE-120 criterion 9 and REQ-PIPE-141 criterion 19, and 2026-10-11 by REQ-PIPE-161 criterion 19."
- New: "WHERE any decision has been recorded against a supply by a person, THE SYSTEM SHALL NOT promote that supply automatically thereafter - EXCEPT un-supersede, re-file (a person's placement of a held supply included, being recorded as a re-file - REQ-PIPE-163 criteria 2 and 24) and an excuse of lateness or its withdrawal, the person-decisions after which the gate may still promote automatically, and the supersede un-supersede undoes (REQ-PIPE-120 criterion 4, REQ-PIPE-141 criterion 8, REQ-PIPE-161 criterion 19). AMENDED 2026-10-05 by REQ-PIPE-120 criterion 9 and REQ-PIPE-141 criterion 19, 2026-10-11 by REQ-PIPE-161 criterion 19, and <date built> by REQ-PIPE-163 criterion 24."
- Why: a placement must not bar the gate, and it is recorded as a re-file, which this criterion already exempts.
- Built behaviour: PROBABLY NO CODE CHANGE: rejection.decided_by_a_person already leaves REFILE out (read 2026-10-14), so a placement recorded as a re-file is exempt; REQ-PIPE-163 criterion 24 still needs a test proving it.

### REQ-PIPE-098 (signed 2026-09-28, built): A dataset that does not participate in a period stands on its most recent supply, by a view created when the period is born

**21. REQ-PIPE-098 criterion 1**. Carried by REQ-PIPE-179 criterion 32.

- Old: "WHEN a period's schema is first created, THE SYSTEM SHALL INHERIT, for each dataset the schedule says does not participate in that period, that dataset's most recent promoted supply - creating in the new period's schema a view that resolves the dataset's logical name to it.
"
- New: "WHEN a period's schema is first created, THE SYSTEM SHALL INHERIT, for each dataset the schedule says does not participate in that period or is turned off in it (REQ-PIPE-179 criterion 22), that dataset's most recent promoted supply - creating in the new period's schema a view that resolves the dataset's logical name to it.
 AMENDED <date built> by REQ-PIPE-179 criterion 32."
- Why: Keith's Q-G: a turned-off period inherits the last promoted supply, so cross-table checks do not read the table as missing.
- Built behaviour: BUILT CODE CHANGES (inheritance._does_not_participate via the one helper); built and tested by REQ-PIPE-179 criterion 22.

### REQ-PIPE-111 (signed 2026-10-07, built): A delivery agreement's past changes only by a declared, approved correction

**22. REQ-PIPE-111 criterion 2**. Carried by REQ-PIPE-179 criterion 30.

- Old: "THE SYSTEM SHALL treat each dated calendar entry, each dated entry of a dataset's own authored dates, calendar version, participation version (including a collection's default participation), not_expected entry and timezone version as FROZEN from the first instant it can govern a filing - for a dated entry, the earliest claim-opening instant that EVERY dataset on its calendar would have for that period, participating or not, since that instant also closes each one's previous period; for a not_expected entry, that dataset's claim-opening instant for the period; for a version, the earlier of the start of its effective-from date and the earliest claim-opening instant of any period it governs."
- New: "THE SYSTEM SHALL treat each dated calendar entry, each dated entry of a dataset's own authored dates, calendar version, participation version (including a collection's default participation), not_expected entry and timezone version as FROZEN from the first instant it can govern a filing - for a dated entry, the earliest claim-opening instant that EVERY dataset on its calendar would have for that period, participating or not - a dataset turned off in that period (REQ-PIPE-179) counted only where it is the first period of its gap, whose claim-opening instant closes the last owed slot before it (REQ-PIPE-179 criterion 14) - since that instant also closes each one's previous period; for a not_expected entry, that dataset's claim-opening instant for the period; for a version, the earlier of the start of its effective-from date and the earliest claim-opening instant of any period it governs; except that a participation version's effective_to and turned_off_reason are not frozen with their version but on their own, as REQ-PIPE-179 criteria 11 and 12 state. AMENDED <date built> by REQ-PIPE-179 criterion 30."
- Why: effective_to has its own freeze point (Keith, Q-K), and only the first period of a gap closes a slot, so only it can freeze a dated entry for a turned-off dataset.
- Built behaviour: BUILT CODE CHANGES (agreement_freeze); built and tested by REQ-PIPE-179 criteria 11 and 12.

**23. REQ-PIPE-111 criterion 4**. Carried by REQ-PIPE-179 criterion 30.

- Old: "THE SYSTEM SHALL carry declared corrections in a `corrections:` list on each OWNING ITEM, beside its versions - a calendar's on that calendar; a dataset's (its participation, due time, participates, not_expected and own authored dates) on that dataset's entry; a collection's participation_defaults on that collection's entry (amended by REQ-PIPE-181); the zone's on the timezone - each correction stating change_reference, date, author, approver, reason, and a list of changes each naming the item, its old value and its new value; and SHALL refuse a correction missing any of them."
- New: "THE SYSTEM SHALL carry declared corrections in a `corrections:` list on each OWNING ITEM, beside its versions - a calendar's on that calendar; a dataset's (its participation, due time, participates, not_expected, own authored dates, effective_to and turned_off_reason) on that dataset's entry; a collection's participation_defaults, their effective_to and turned_off_reason included, on that collection's entry (amended by REQ-PIPE-181); the zone's on the timezone - each correction stating change_reference, date, author, approver, reason, and a list of changes each naming the item, its old value and its new value; and SHALL refuse a correction missing any of them. AMENDED <date built> by REQ-PIPE-179 criterion 30."
- Why: a correction must be able to carry the two new frozen items.
- Built behaviour: BUILT CODE CHANGES (agreement_freeze's correction matching); built and tested by REQ-PIPE-179 criteria 11 and 12, and shown by TS-63's correction (REQ-GEN-218, split out of criterion 39).

**24. REQ-PIPE-111 criterion 15**. Carried by REQ-PIPE-179 criterion 30.

- Old: "WHEN a change is refused, THE SYSTEM SHALL report it as the existing configuration errors do (file, where, problem, fix), grouped by item, saying that nothing was committed, naming the item in exactly the syntax a correction uses, printing a ready-to-paste correction entry with the item, old and new values filled in and reason, approver and change_reference as placeholders, listing who may approve, naming the impact preview command (REQ-PIPE-169), and - for a not_expected entry - naming mark as not supplied (REQ-PIPE-132) as the after-the-fact route."
- New: "WHEN a change is refused, THE SYSTEM SHALL report it as the existing configuration errors do (file, where, problem, fix), grouped by item, saying that nothing was committed, naming the item in exactly the syntax a correction uses, printing a ready-to-paste correction entry with the item, old and new values filled in and reason, approver and change_reference as placeholders, listing who may approve, naming the impact preview command (REQ-PIPE-169), and - for a not_expected entry or an effective_to - naming mark as not supplied (REQ-PIPE-132) as the after-the-fact route. AMENDED <date built> by REQ-PIPE-179 criterion 30."
- Why: a missed period before a turn-off is recorded after the fact the same way as one before a not_expected entry.
- Built behaviour: BUILT CODE CHANGES (refusal text); NO OTHER CRITERION STATES IT, so REQ-PIPE-179's build needs its own test for this wording.

### REQ-PIPE-113 (signed 2026-10-07, built): A slot's due instant comes from the participation in force on its period's date, and a later change never moves an earlier slot

**25. REQ-PIPE-113 criterion 2**. Carried by REQ-PIPE-179 criterion 31.

- Old: "THE SYSTEM SHALL take a slot's expected time, days before, grace allowance and claim-window override each as the value REQ-PIPE-181 resolves for that period's own date, from the dataset or its collection, and its default claim window from the calendar version in force on that date (amended by REQ-PIPE-181)."
- New: "THE SYSTEM SHALL take a slot's expected time, days before, grace allowance and claim-window override each as the value REQ-PIPE-181 resolves for that period's own date, from the dataset or its collection - through the one participation resolution of REQ-PIPE-179 criterion 27, so that a collection inside its own turned-off gap supplies no value (REQ-PIPE-179 criterion 7) - and its default claim window from the calendar version in force on that date (amended by REQ-PIPE-181, and <date built> by REQ-PIPE-179 criterion 31)."
- Why: inside a collection's gap the collection supplies no values (Keith, T1), so a back-on dataset's slot takes only its own.
- Built behaviour: BUILT CODE CHANGES (slots via the one helper); built and tested by REQ-PIPE-179 criteria 7 and 27.

**26. REQ-PIPE-113 criterion 4**. Carried by REQ-PIPE-179 criterion 31.

- Old: "THE SYSTEM SHALL compute each slot's closing instant (REQ-PIPE-131) from the next calendar period's claim-opening instant as that next period's own inputs give it, so that a version change takes effect at its own boundary and nowhere before it."
- New: "THE SYSTEM SHALL compute each slot's closing instant (REQ-PIPE-131) from the next calendar period's claim-opening instant as that next period's own inputs give it, so that a version change takes effect at its own boundary and nowhere before it; WHERE the dataset is turned off in that next period, from the claim-opening instant it would have had, each value resolved as if every effective_to on or before its date were absent (REQ-PIPE-179 criterion 14). AMENDED <date built> by REQ-PIPE-179 criterion 31."
- Why: a period inside a gap has no slot, so without this the last owed slot before a gap would have no closing instant.
- Built behaviour: BUILT CODE CHANGES (slots.py closing instant); built and tested by REQ-PIPE-179 criterion 14.

### REQ-PIPE-121 (signed 2026-10-04, built): A table arriving in or leaving a period re-checks the waiting supplies in that period that read it, and re-applies the gate - through one mechanism

**27. REQ-PIPE-121 criterion 1**. Carried by REQ-PIPE-211 criterion 1.

- Old: "WHEN a table arrives in or leaves a period schema - promoted by a rule or a person, re-filed in or out, superseded, demoted or rejected - THE SYSTEM SHALL re-evaluate, within that period only, every cross-table check that declares it reads the moved table, whether it belongs to a supply WAITING in that period or one PROMOTED there, and SHALL NOT re-evaluate any check that does not read a moved table."
- New (REVISED 2026-10-14 for follow-up F5): "WHEN a table arrives in or leaves a period schema - promoted by a rule or a person, re-filed in or out, superseded, demoted or rejected - or the contest of a table in that period ends, by a person's settlement of the pair whatever its outcome or by a later arrival superseding the pair whether or not that arrival is promoted (REQ-PIPE-211), THE SYSTEM SHALL re-evaluate, within that period only, every cross-table check that declares it reads the moved table or the table whose contest ended, whether it belongs to a supply WAITING in that period or one PROMOTED there, and SHALL NOT re-evaluate any check that reads neither. AMENDED <date built> by REQ-PIPE-211 criterion 1."
- Why: a contested pair's files are staged, never in the period schema. A settlement that leaves nothing promoted, or a later file superseding the pair and left waiting, moves no table into or out of it. So as worded, criterion 1 does not trigger, and its last clause forbids re-evaluating a check that reads no moved table.
- Built behaviour: BUILT CODE CHANGES with REQ-PIPE-193 criterion 23 (knock_on gains a trigger); built and tested by REQ-PIPE-211.
- **Note:** NO LONGER CONTINGENT, since F5. REQ-PIPE-193 criterion 23 can carry a settlement's knock-on, but a later arrival's supersession is not a settlement, and this criterion is the list of the one handler's triggers. The text changed from the morning draft: "a contested pair ... is settled" became "the contest ... ends", naming both ways it ends, and "the moved or settled table" became "the moved table or the table whose contest ended". The architect may still place the supersession trigger elsewhere (REQ-PIPE-118).

### REQ-PIPE-131 (signed 2026-10-04, built): A period closes once its calendar's next period's claim window opens, so a file is only ever filed to the one open period

**28. REQ-PIPE-131 criterion 1**. Carried by REQ-PIPE-179 criterion 31.

- Old: "THE SYSTEM SHALL treat a dataset's slot as OPEN from its claim-opening instant until the claim-opening instant that dataset would have for the NEXT PERIOD OF ITS CALENDAR - whether or not the dataset participates in that next period - and as CLOSED from then on."
- New: "THE SYSTEM SHALL treat a dataset's slot as OPEN from its claim-opening instant until the claim-opening instant that dataset would have for the NEXT PERIOD OF ITS CALENDAR - whether or not the dataset participates in that next period or is turned off in it (REQ-PIPE-179) - and as CLOSED from then on. AMENDED <date built> by REQ-PIPE-179 criterion 31."
- Why: the same closing rule applies across a turned-off gap as across a period not participated in.
- Built behaviour: BUILT CODE CHANGES with criterion 2 below; built and tested by REQ-PIPE-179 criterion 14.

**29. REQ-PIPE-131 criterion 2**. Carried by REQ-PIPE-179 criterion 31.

- Old: "THE SYSTEM SHALL compute that next claim-opening instant from the next calendar period's date with each value as REQ-PIPE-181 resolves it on that next period's date (amended by REQ-PIPE-181)."
- New: "THE SYSTEM SHALL compute that next claim-opening instant from the next calendar period's date with each value as REQ-PIPE-181 resolves it on that next period's date (amended by REQ-PIPE-181) - or, WHERE the dataset is turned off in that next period, as if every effective_to on or before that date were absent (REQ-PIPE-179 criterion 14; AMENDED <date built> by REQ-PIPE-179 criterion 31)."
- Why: inside a gap nothing resolves (the collection supplies no values), so the closing instant is computed as if the turn-off were absent.
- Built behaviour: BUILT CODE CHANGES (slots.py); built and tested by REQ-PIPE-179 criterion 14.

### REQ-PIPE-134 (signed 2026-10-04, built): A dataset's periods never overlap - enforced in CI from configuration

**30. REQ-PIPE-134 criterion 1**. Carried by REQ-PIPE-179 criterion 31.

- Old: "THE SYSTEM SHALL require, for every dataset and every pair of consecutive periods of that dataset's calendar - whether or not the dataset participates in either - that the claim-opening instant the dataset would have for the later period is strictly after the late-after instant (due instant plus grace) the dataset would have for the earlier one."
- New: "THE SYSTEM SHALL require, for every dataset and every pair of consecutive periods of that dataset's calendar - whether or not the dataset participates in either - that the claim-opening instant the dataset would have for the later period is strictly after the late-after instant (due instant plus grace) the dataset would have for the earlier one; WHERE either period of a pair lies inside a turned-off gap (REQ-PIPE-179), THE SYSTEM SHALL instead check the last owed period before the gap against the closing instant REQ-PIPE-179 criterion 14 gives it and, WHERE the gap is temporary, require the first owed slot after it to open strictly after the last owed slot before it closes, and SHALL NOT check any pair both of whose periods lie inside the gap. AMENDED <date built> by REQ-PIPE-179 criterion 31."
- Why: inside a gap a period has no resolved values to check, and the overlap that matters is between the owed slots either side of it.
- Built behaviour: BUILT CODE CHANGES (period_overlap / validate_schedule); NO OTHER CRITERION STATES IT, so REQ-PIPE-179's build needs its own tests for all three clauses.

### REQ-PIPE-140 (signed 2026-10-04, built): A decision can run a supply's QA again, on demand, as a run of its own that never overwrites the first

**31. REQ-PIPE-140 new criterion 9**. Carried by REQ-PIPE-163 criterion 31.

- Old: "(none - criteria 1 to 8 are unchanged; this is a new criterion 9)"
- New: "THE SYSTEM SHALL have every runner of an owed run - the terminal's filing-decisions door, `mothman supply decide --wait` (REQ-PIPE-163 criterion 25) and the processing pass - claim the run before running it, SHALL release a claim when the process holding it ends, and SHALL have a runner that finds the run claimed skip it and leave it owed, saying that it is being run elsewhere (REQ-PIPE-163 criterion 30). ADDED <date built> by REQ-PIPE-163 criterion 31: the claim was built 2026-10-11 (post-build-review #136, recheck.run's advisory lock) and is stated here for the first time."
- Why: the claim is built and no criterion states it.
- Built behaviour: TEXT CATCH-UP for the door and the processing pass (built 2026-10-11); the decide --wait runner is new and is REQ-PIPE-163 criterion 25's to build.

### REQ-PIPE-141 (signed 2026-10-04, built): Re-filing a supply returns it to staging under a new filing for its new period, where it is checked and the normal gate decides

**32. REQ-PIPE-141 criterion 7**. Carried by REQ-PIPE-163 criterion 25.

- Old: "THE SYSTEM SHALL then run the re-filed supply's QA against the target period through REQ-PIPE-140, and SHALL apply the promotion gate to it exactly as for a first arrival, with the amber and replacement settings in force at that instant (REQ-PIPE-122, REQ-PIPE-123), not those in force when it first arrived or was first checked."
- New: "THE SYSTEM SHALL then run the re-filed supply's QA against the target period through REQ-PIPE-140, and SHALL apply the promotion gate to it exactly as for a first arrival, with the amber and replacement settings in force at that instant (REQ-PIPE-122, REQ-PIPE-123), not those in force when it first arrived or was first checked; WHERE the re-file is recorded through `mothman supply decide --wait`, that run SHALL happen in the foreground straight after the decision commits, ending with REQ-PIPE-163 criterion 26's shared outcome panel, and WHERE it is recorded through decide without --wait, the run SHALL be left owed (REQ-PIPE-140 criterion 7). AMENDED <date built> by REQ-PIPE-163 criterion 25."
- Why: decide --wait now covers re-file as well as place and re-check (Keith, round 3 Q1).
- Built behaviour: BUILT CODE CHANGES (decide gains --wait); built and tested by REQ-PIPE-163 criteria 25 to 30.

**33. REQ-PIPE-141 criterion 12**. Carried by REQ-PIPE-179 criterion 20.

- Old: "IF a person re-files a supply into a period where its dataset's slot is resolved by INHERITANCE, THEN THE SYSTEM SHALL refuse it, say that nothing was expected for that period, and name un-inherit as the step that must come first."
- New: "IF a person re-files a supply into a period where its dataset's slot is resolved by INHERITANCE, THEN THE SYSTEM SHALL refuse it, say that nothing was expected for that period, and name un-inherit as the step that must come first - except WHERE that period lies inside a turned-off gap (REQ-PIPE-179), when REQ-PIPE-179 criterion 20's refusal SHALL be given in its place. AMENDED <date built> by REQ-PIPE-179 criterion 20."
- Why: a gap period inherits (REQ-PIPE-179 criterion 22), so this criterion would advise un-inherit, which does not make a gap period owed - the same narrowing REQ-PIPE-163 criterion 8 makes for a placement.
- Built behaviour: BUILT CODE CHANGES (refiling.plan's refusal); built and tested by REQ-PIPE-179 criterion 20.
- **Note:** NOT PROMISED BY THE DRAFT - found by reading criterion 12 against REQ-PIPE-179 criteria 20 and 22.

### REQ-PIPE-154 (signed 2026-10-06, built): A supply arriving after its dataset's schedule has ended is held as schedule-ended, and says what to edit

**34. REQ-PIPE-154 criterion 1**. Carried by REQ-PIPE-179 criterion 32.

- Old: "IF a supply arrives after the last slot of its dataset's authored calendar has closed, THEN THE SYSTEM SHALL hold it for a person under REQ-PIPE-064 with a reason stating that the dataset's delivery schedule has ended and naming that dataset's own last authored period."
- New: "IF a supply arrives after the last slot of its dataset's authored calendar has closed, THEN THE SYSTEM SHALL hold it for a person under REQ-PIPE-064 with a reason stating that the dataset's delivery schedule has ended and naming that dataset's own last authored period - unless the dataset is turned off for the period whose slot would then be current, when the hold is labelled turned off instead (REQ-PIPE-179 criterion 17). AMENDED <date built> by REQ-PIPE-179 criterion 32."
- Why: turned off outranks schedule ended (Keith confirmed, 2026-10-13, set 2 Q7(a)): "add the next dates" would not make a turned-off dataset owe anything.
- Built behaviour: BUILT CODE CHANGES (assignment / supply_holds labelling); built and tested by REQ-PIPE-179 criterion 17.

**35. REQ-PIPE-154 criterion 2**. Carried by REQ-PIPE-179 criterion 32.

- Old: "THE SYSTEM SHALL record whether a hold was raised because the schedule ended as a structured field of the hold, and SHALL NOT require any reader to parse the hold's prose to tell."
- New: "THE SYSTEM SHALL record whether a hold was raised because the schedule ended as a structured field of the hold, kept as history, and SHALL NOT require any reader to parse the hold's prose to tell; every reader that labels, re-files or counts a hold SHALL take its label from the configuration in force when it reads (REQ-PIPE-179 criterion 18), not from that field. AMENDED <date built> by REQ-PIPE-179 criterion 32."
- Why: Keith's T4: the recorded flag is history; the label shown, re-filed on and counted is worked out from current configuration.
- Built behaviour: BUILT CODE CHANGES (readers of the recorded flag); built and tested by REQ-PIPE-179 criterion 18.

**36. REQ-PIPE-154 criterion 6**. Carried by REQ-PIPE-179 criterion 32.

- Old: "WHEN a processing pass holds one or more supplies because their dataset's schedule has ended, THE SYSTEM SHALL state in that pass's own summary how many datasets and how many supplies were held for that reason, separately from any other holds."
- New: "WHEN a processing pass holds one or more supplies because their dataset's schedule has ended, THE SYSTEM SHALL state in that pass's own summary how many datasets and how many supplies were held for that reason - the label worked out as REQ-PIPE-179 criterion 18 says - separately from any other holds, turned-off holds included (REQ-PIPE-179 criterion 26). AMENDED <date built> by REQ-PIPE-179 criterion 32."
- Why: the pass counts by the worked-out label, and turned-off holds are their own count.
- Built behaviour: BUILT CODE CHANGES (the pass summary); built and tested by REQ-PIPE-179 criteria 18 and 26.

**37. REQ-PIPE-154 criterion 7**. Carried by REQ-PIPE-179 criterion 32.

- Old: "WHEN dates are added to a dataset's calendar that cover the receipt instant of a supply held because its schedule ended, THE SYSTEM SHALL re-file that supply by the filing rule on the next processing pass, in receipt order with every other supply so held, and SHALL resolve its hold naming the filing that replaced it."
- New: "WHEN configuration later gives an outstanding assignment-rule hold's receipt instant an open owed slot - dates added to a dataset's calendar covering a supply held because its schedule ended, or any other change, whatever the hold's label (REQ-PIPE-179 criterion 19) - THE SYSTEM SHALL re-file that supply by the filing rule on the next processing pass, in receipt order with every other supply so held, and SHALL resolve its hold naming the filing that replaced it. AMENDED <date built> by REQ-PIPE-179 criterion 32."
- Why: Keith, round 3 Q8 and set 2 Q6: one re-filer for every hold configuration later covers, not a second one for turned-off holds.
- Built behaviour: BUILT CODE CHANGES (schedule_ended.refile_covered widens to every label, including the eight Case Workers holds); built and tested by REQ-PIPE-179 criterion 19.
- **Note:** WIDENS a built behaviour: plain assignment-rule holds, including holds a correction or a settlement raised, will start being filed by the rule when configuration covers them.

### REQ-PIPE-170 (signed 2026-10-07, built): After a correction, the data asset's manager confirms the proposed filing moves all at once, and may keep any supply where it is

**38. REQ-PIPE-170 criterion 5**. Carried by REQ-PIPE-179 criterion 36.

- Old: "THE SYSTEM SHALL let the asset manager exclude individual supplies and then confirm every remaining move, across every dataset and agency the correction touches, in one action."
- New: "THE SYSTEM SHALL let the asset manager exclude individual supplies and then confirm every remaining move, across every dataset and agency the correction touches, in one action; IF the corrected configuration makes a supply's current period one its dataset owes nothing in - by participation, not_expected or a turn-off - THEN THE SYSTEM SHALL NOT offer to exclude (keep) that supply, and SHALL propose moving it to the owed slot the filing rule gives it, or holding it, saying that the period no longer owes a supply. AMENDED <date built> by REQ-PIPE-179 criterion 36."
- Why: Keith, round 3 Q9: a supply kept in a period with no slot, which inherits and accepts no placement, would have three rules disagreeing about one period.
- Built behaviour: BUILT CODE CHANGES (correction_trial / confirm-correction); REQ-PIPE-179 criterion 36 is the only statement, so its build needs a test of its own.
- **Note:** REMOVES A GUARANTEE, deliberately: the asset manager can no longer keep such a supply where it is (Keith, round 3 Q9).

**39. REQ-PIPE-170 criterion 26**. Carried by REQ-PIPE-179 criterion 37.

- Old: "WHEN a processing pass finds a parked move whose blocker has cleared, THE SYSTEM SHALL carry it out to the period confirmed, as the rule naming who confirmed it, before any arrival in that pass, and SHALL NOT do so for a dataset the agreement backstop refuses (REQ-PIPE-173)."
- New: "WHEN a processing pass finds a parked move whose blocker has cleared, THE SYSTEM SHALL carry it out to the period confirmed, as the rule naming who confirmed it, before any arrival in that pass, and SHALL NOT do so for a dataset the agreement backstop refuses (REQ-PIPE-173), nor WHERE the confirmed period now lies inside a turned-off gap, when the move stays parked and says so (REQ-PIPE-179 criterion 37). AMENDED <date built> by REQ-PIPE-179 criterion 37."
- Why: criterion 26 says a cleared parked move SHALL be carried out; REQ-PIPE-179 criterion 37 says one into a turned-off gap stays parked - the two contradict unless 26 is amended.
- Built behaviour: BUILT CODE CHANGES (the processing pass's parked-move step); built and tested by REQ-PIPE-179 criteria 20 and 37.
- **Note:** NOT PROMISED BY THE DRAFT - found by reading criterion 26 against REQ-PIPE-179 criterion 37.

**40. REQ-PIPE-170 criterion 28**. Carried by REQ-PIPE-179 criterion 36.

- Old: "WHILE a move is parked, THE SYSTEM SHALL let the data asset's manager keep the supply where it is instead, with a reason, recorded as a keep against that correction, through mothman supply confirm-correction --keep on the confirmed reference and from the filing menu."
- New: "WHILE a move is parked, THE SYSTEM SHALL let the data asset's manager keep the supply where it is instead, with a reason, recorded as a keep against that correction, through mothman supply confirm-correction --keep on the confirmed reference and from the filing menu - except WHERE the supply's current period is one its dataset now owes nothing in, when keep SHALL NOT be offered (criterion 5). AMENDED <date built> by REQ-PIPE-179 criterion 36."
- Why: the scoper's reading: keep on a parked move is the same act as keep at confirmation, so the same exception applies.
- Built behaviour: BUILT CODE CHANGES (confirm-correction --keep on a parked move); stated in REQ-PIPE-179 criterion 36 since its own pass, and listed in its NFR 11, so it gets a test of its own.
- **Note:** an extension of criterion 36 to the second place keep is offered. It was the scoper's proposal; you chose it (Keith, 2026-10-14, REQ-PIPE-179 own pass Q2, option A).

**44. REQ-PIPE-170 criterion 31: DROPPED** (Keith, 2026-10-14, G3, option B). It existed only to carry the "confirm only what the script says" option. Under G3 a replay confirms everything due unless the script says pending. Criterion 31 already says that ("confirm every pending correction dated up to now"), so REQ-PIPE-170 stays as signed. Recorded on REQ-GEN-205 as "AMENDMENT 44 DROPPED".

**45. REQ-PIPE-170 criterion 23, and its unmet entry**. Carried by REQ-GEN-218 criterion 7.

- Old criterion: "THE SYSTEM SHALL generate the calendar-correction scenarios TS-57 to TS-62 (TS-63 by REQ-PIPE-179 criterion 39, Keith, 2026-10-13) in the test scenario register (plans/supply-model.md) into the synthetic history once this requirement is built - a correction made part way through that history, merged, and confirmed with at least one supply kept, one moved, one held, one blocked and one re-judged with no move, plus one left awaiting confirmation - so that each shape can be seen in the real dashboard and terminal, and SHALL give TS-57 to TS-64 each a unit test."
- New criterion: "THE SYSTEM SHALL generate the calendar-correction scenarios TS-57 to TS-62 (TS-63 by REQ-GEN-218, Keith, 2026-10-13 and 2026-10-14) in the test scenario register (plans/supply-model.md) into the synthetic history once this requirement is built - a correction made part way through that history, merged, and confirmed with at least one supply kept, one moved, one held, one blocked and one re-judged with no move, plus one left awaiting confirmation - so that each shape can be seen in the real dashboard and terminal, and SHALL give TS-57 to TS-64 each a unit test. AMENDED <date applied> by REQ-GEN-218 criterion 7: TS-63 moved to REQ-PIPE-179 criterion 39 (Keith, 2026-10-13) and was split out of it into REQ-GEN-218 (Keith, 2026-10-14)."
- Old unmet entry (its `criterion` field; `why`, `owner` and `blocked_by` unchanged): "Criterion 23, first half - TS-57 to TS-62 GENERATED INTO THE SYNTHETIC HISTORY. Each has a unit test (TestScenarioRegister; TS-64 in tests/test_correction_trial.py), TS-63 moved to REQ-PIPE-179 criterion 39 (Keith, 2026-10-13)."
- New: "Criterion 23, first half - TS-57 to TS-62 GENERATED INTO THE SYNTHETIC HISTORY. Each has a unit test (TestScenarioRegister; TS-64 in tests/test_correction_trial.py), TS-63 moved to REQ-PIPE-179 criterion 39 (Keith, 2026-10-13) and from there to REQ-GEN-218 (Keith, 2026-10-14)."
- Why: Keith, 2026-10-14, REQ-PIPE-179 own pass Q1: TS-63 is planted by REQ-GEN-218, and REQ-PIPE-179 criterion 39 is now a pointer.
- Built behaviour: TEXT ONLY. Applied in the change that adds REQ-GEN-218 to requirements.yaml (so the signed register never names a criterion that no longer plants TS-63); `<date applied>` is that change's date, not a build date.

### REQ-PIPE-173 (signed 2026-10-07, built): The pipeline refuses a dataset whose judged past changed without a declared correction

**41. REQ-PIPE-173 criterion 12**. Carried by REQ-PIPE-179 criterion 38.

- Old: "THE SYSTEM SHALL treat a judged period that a not_expected entry now declares owed nothing as changed, so it refuses the dataset unless a declared correction of that entry accounts for it (added 2026-10-11, Keith's answer (i))."
- New: "THE SYSTEM SHALL treat a judged period that a not_expected entry, or an effective_to added or moved (REQ-PIPE-179), now declares owed nothing as changed, so it refuses the dataset unless a declared correction of that entry or that effective_to accounts for it (added 2026-10-11, Keith's answer (i); AMENDED <date built> by REQ-PIPE-179 criterion 38)."
- Why: a turn-off removes a judged slot exactly as a not_expected entry does, and the backstop must see either.
- Built behaviour: POSSIBLY BUILT CODE CHANGE: whether agreement_drift already flags a vanished slot is REQ-PIPE-179's open question; test first either way.

### REQ-PIPE-193 (signed 2026-10-13, built): A person settles a contested pair in the terminal - saying, for EACH of its two files, whether it is this period's supply, is re-filed to another period, is rejected, or is kept but superseded - and each file that becomes a supply is filed, checked and gated on its own receipt

**42. REQ-PIPE-193 criterion 19** (drafted this morning). Carried by REQ-PIPE-163 criterion 42.

- Old: "IF a re-file target is refused, THEN THE SYSTEM SHALL say why and ask for the period again, before the reason is asked and keeping both files' answers; the target prompt SHALL offer the next period as its default."
- New: "WHEN a file's outcome is a re-file, THE SYSTEM SHALL ask for its target period through REQ-PIPE-163 criterion 16's period chooser, with the next period as its first choice, and SHALL NOT ask for a typed period; IF a re-file target is refused, THEN THE SYSTEM SHALL say why and offer the chooser again, before the reason is asked and keeping both files' answers."
- Why: Keith, close-out Q23: periods are never typed in the terminal.
- Built behaviour: BUILT CODE CHANGES (settle_tui's typed prompt becomes the chooser); built and tested by REQ-PIPE-163 criterion 16.

**43. REQ-PIPE-193 criterion 23** (drafted this morning). Carried by REQ-PIPE-211 criterion 6.

- Old: "WHEN a settlement moves a file into or out of a period, and WHEN a settled supply is promoted, THE SYSTEM SHALL owe the knock-on through REQ-PIPE-121's one handler (knock_on), which selects the checks by reevaluation.reading_checks() and the datasets by reevaluation.counts_toward(), and SHALL NOT add a settlement-specific path or restate either rule."
- New: "WHEN a pair is settled, whatever its outcome (REQ-PIPE-211), WHEN a settlement moves a file into or out of a period, and WHEN a settled supply is promoted, THE SYSTEM SHALL owe the knock-on through REQ-PIPE-121's one handler (knock_on), which selects the checks by reevaluation.reading_checks() and the datasets by reevaluation.counts_toward(), and SHALL NOT add a settlement-specific path or restate either rule."
- Why: Keith, close-out Q21: after "reject both" the readers would otherwise stay red for good.
- Built behaviour: BUILT CODE CHANGES (settlement.apply owes a knock-on it does not today); built and tested by REQ-PIPE-211 criteria 1 to 8.
- **Note:** unchanged by follow-up F5: a later file superseding the pair is not a settlement, and amendment 27 carries that case.

### No change needed

- **REQ-PIPE-083 criterion 21** (named by REQ-PIPE-179 criterion 24): its needs-action ticket policy is per SLOT, and a held supply has no slot and so no ticket (REQ-PIPE-083's own decision, "A HELD SUPPLY HAS NO SLOT AND SO HAS NO TICKET") - so a turned-off hold never raises one. Criterion 24's "and REQ-PIPE-083 criterion 21" can be dropped.
- **REQ-PIPE-053 criterion 4** (named by REQ-PIPE-179 criterion 32): it says only that such a supply is held, and already gives its labelling to REQ-PIPE-154, whose criterion 1 is amended. A turned-off supply is still held. Criterion 32's "criteria 4, 10 and 15" can read "criteria 10 and 15".
- **REQ-PIPE-053 criteria 16, 17 and 18** (named by REQ-DASH-180 criterion 22): they render, keep out of the rollup and count the exhausted condition, which criterion 19 evaluates; amending 19 alone carries all three.
- **REQ-DASH-155 criterion 3** (named by REQ-DASH-180 criterion 22): it is worded on the same test as criterion 1 ("no supply is held because a schedule ended"), so amending 1's count carries it. One corner is left for the architect: a temporary gap running past the calendar's last date could leave turned-off holds received after the schedule ended, making "nothing has arrived since the schedule ended" untrue.
- **REQ-PIPE-154 criterion 7** (named by REQ-PIPE-163 (folded decision, 2026-10-10)): REQ-PIPE-163's own decision records that amendment as SUPERSEDED by round 3 Q7: schedule-ended holds are never placed or rejected, which REQ-PIPE-163 criterion 22 states. Only REQ-PIPE-179's amendment to criterion 7 remains.
- **REQ-PIPE-170 its unmet entry for criterion 23** (named by REQ-PIPE-179's old criterion 40): the live register already read "TS-57 to TS-62 ... TS-63 moved to REQ-PIPE-179 criterion 39 (Keith, 2026-10-13)" in both criterion 23 and its unmet entry, so that criterion was dropped. SUPERSEDED 2026-10-14 by the TS-63 split: both now need re-pointing at REQ-GEN-218, which is amendment 45.
- **REQ-PIPE-163 criterion 17** (named by REQ-PIPE-179 (round 3 decision)): REQ-PIPE-179's decision "163 NO LONGER AMENDED HERE" records that 163 is written turn-off-aware (Keith, set 1 Q1). REQ-PIPE-163 is unsigned in any case.

### Register bookkeeping, not amendments

Clearing an unmet entry once its scenario is planted is done when the scenario is built and needs no wording from you: REQ-GEN-136 criterion 3 (REQ-GEN-203 criterion 9), REQ-GEN-136 criteria 4, 5, 8, 9 and 11 and REQ-GEN-137 criteria 2, 5 and 6 (REQ-GEN-206; criterion 4's entry is cleared with evidence naming TS-75 and its wording stays, follow-up F13), and REQ-PIPE-170 criterion 23 (REQ-GEN-205). REQ-PIPE-202 criterion 9 changes tests, not a requirement.

## Still open: questions for you (recommended option first)

**Answered since the last version of this list.** Set A was answered by R8, set B waits on running-thoughts #95, and set C was answered by R1. The round 4 fold's three questions were answered by G1 to G3, and all three are folded.

**Answered since:** H1 to H4 (REQ-DASH-182's three and REQ-DASH-209's one) and the four questions of REQ-PIPE-179's own pass, all option A, are folded.

**New, one question, from the TS-63 split.**

### REQ-GEN-218
1. **TS-63's scenario links?** Criterion 39 never said. Without a declared link, a scenario lands on the latest day it has anything to show (REQ-GEN-201 criterion 6). For TS-63 that is long after the gap, where the "Turning off after" marker its Expect quotes no longer shows.
   - A) Two lettered links: "a" after the correction's date and before effective_to, where the marker shows; "b" inside the gap, after the injected gap supply arrives, where it is held and REQ-DASH-180's quiet line counts it. Link "a" needs REQ-GEN-205 criterion 12's link bounded by a correction's date, so REQ-GEN-218 is built after REQ-GEN-205 (recommended).
   - B) The default single link only, built straight after REQ-DASH-180. The register describes the marker but nothing links to it.

### Not questions, but provisional, so say if you want them otherwise
- TS-81's shape (REQ-GEN-206): one grown quarter, no green targeting or lead-ins, and the settlement the day after arrival. This reads F8's "another grown quarter" as one quarter.
- REQ-GEN-218: cp-carers as TS-63's dataset (carried from REQ-PIPE-179), and must.
- REQ-PIPE-179 criterion 34: N counts supplies, and the per-dataset row reads as REQ-DASH-180's quiet line does. Criterion 41: "the newest" correction or entry where there are several; a `turns_off` entry on a version with no effective_to is accepted and read by nothing.
- REQ-DASH-180 criterion 25's "Turning off after <effective_to> - nothing more owed" keeps its hyphen, and REQ-PIPE-179 criterion 29's terminal labels ("Turned off - nothing due") keep theirs: H1 named the page's labels and REQ-DASH-180 criterion 16 only.
- cp-case-workers as TS-61's blocker (REQ-GEN-205).
- New wording in REQ-DASH-208 (criteria 4, 7, 11 and 12) and REQ-DASH-209 (criterion 12's h2, sub-line and rail, and criterion 14's links), and REQ-DASH-182's new wording listed at the top.
- REQ-GEN-205 criterion 16's test now also covers the resumed bootstrap. This is the scoper's addition under G3, and can be dropped.

### Waiting on running-thoughts #95, not on you now
- REQ-DASH-204, REQ-PIPE-210 and REQ-PIPE-211, and the round 4 findings against them (architect B1, H1, H4, M1, M2 and M5; CLI UX 1 to 12; questions C, A2, B2 and C2). R4 (the exit code) is answered and is folded when 211 is.
- REQ-GEN-206's TS-81 Expect (REQ-DASH-204 criterion 15's wording, and the readers' status).

### Build-time checks (for the architect, not for you)
- REQ-PIPE-211: whether REQ-PIPE-121 criteria 9 and 15 need amending for a contest ended by an arrival.
- REQ-GEN-205: whether a correction declared for a version added to a synthetic asset is staged as a correction.
- REQ-GEN-205: whether REQ-PIPE-169's impact preview reports arrivals filed under a new version at receipt, as well as moves.
- REQ-DASH-204: which notice each cause has, to end with "Affects".
- REQ-PIPE-179: criterion 38's remaining check - that a turned-off period reaches verdict.compared as gone, and that agreement_drift._sources includes the effective_to item key.
- REQ-PIPE-179: whether criterion 19's re-filer acts before REQ-PIPE-170's confirmation of a correction that is declared but not yet confirmed.
- REQ-GEN-206: #175's 8 September supply.

## Ready for sign-off: REQ-PIPE-179, REQ-DASH-182, REQ-DASH-209 and REQ-GEN-218

**REQ-PIPE-179.** It has had its own scoper pass, and all four of that pass's questions are answered and folded. Nothing in its open_questions needs you: three provisional choices you can override, and two build checks for the architect. What you would be signing: 41 criteria (criterion 39 now a pointer to REQ-GEN-218), the new wording listed at the top, and the 22 amendments it carries (13, 14, 16, 17, 21 to 26, 28 to 30 and 33 to 41) in their exact wording. Amendment 40 is no longer the scoper's proposal. Signing it does not need REQ-GEN-218 signed, but amendments 45 to 47 should land in the same change that adds REQ-GEN-218, so the register never cites criterion 39 for TS-63 once 39 is a pointer.

**REQ-DASH-182.** Your H1 to H3 are folded, and it has no open questions. What you would be signing: 15 criteria, including the wording you have not yet approved word for word (criteria 3, 8, 9, 11, 13 and 14, listed at the top). It amends no signed requirement.

**REQ-DASH-209.** Your H4 is folded, and it has no open questions. The wording still for your approval is criterion 12 (h2, sub-line and rail) and criterion 14 (the link wording). It amends no signed requirement, since amendment 3 is dropped.

**REQ-GEN-218 (new).** Its content is REQ-PIPE-179 criterion 39 and the TS-63 decisions you already made, now in a requirement of its own. It has one open question for you: its scenario links (above). Your answer decides whether it is built after REQ-GEN-205 or straight after REQ-DASH-180. It carries amendments 45 to 47 (text only), which you would approve with it. It was not reviewed as a requirement of its own, so say if you want a review first.

## Non-functional angles on the three new requirements

**Answered by the scoper:**
- **Scale (thirty datasets):** one row per cause or per dataset, with counting lines.
- **Build rule:** the view looks up the timelines the build already embeds from `qa.slot_holds` and the decision log, and never reads the period schema or `_manifest` (round 4 architect H3).
- **Reliability:** 211's re-check is owed in the settlement's transaction and finished by the processing pass if interrupted.
- **No false quiet or false green:** 210's criterion 4 and 211's re-evaluation never drop a check.
- **Accessibility and portability:** no new asset; the file:// path is unaffected.
- **Auditability:** 211's results name the settlement as their cause.
- **Multi-agency:** the view is per collection.

**Ruled out:** compliance and retention, and cost (no new compute beyond cross-table checks).

**Answered by you:** REQ-DASH-209's page size is measured before and after and reported, with no budget (F15). Every row is shown open at thirty datasets (R6).

**New from F7:** someone settling a pair in the terminal now also waits for the readers' re-check. REQ-PIPE-211 names the re-check in the warning panel beforehand, so the wait is expected.

## Plans files, to apply alongside (drafts only, not written)
- **plans/running-thoughts.md #93:** delete it in the change that adds REQ-DASH-209 to requirements.yaml (it is now scoped), and repoint any reference to REQ-DASH-209.
- **plans/post-build-review.md #174:** append "Keith's answers 2026-10-14 (close-out Q15, Q24): the page fix is REQ-DASH-208, with the jump carried in the URL; criterion 9's wording is amended by REQ-GEN-206 criterion 15." It stays todo until those are built.
- **plans/post-build-review.md #175:** append "Keith's answer 2026-10-14 (close-out Q14): option 1, carried by REQ-GEN-206 criterion 11."
- **plans/post-build-review.md #177:** already done. REQ-GEN-205's draft criterion 19 is now removed, as its last line said it would be.
- **plans/running-thoughts.md #77:** nothing to apply. It already carries the retention of turned-off holds (added 2026-10-14), which is where your own pass Q4 sends it.
- **plans/supply-model.md, TS-63's register entry:** not a plans edit to apply now. Rewriting it is REQ-GEN-218 criterion 5's build duty.

## Keith's answers (2026-10-14 morning, via AskUserQuestion)

- Q1: A - REQ-GEN-207 is its own requirement, built first; today's quarters stay byte-identical.
- Q2: A - Keith's real identity approves the fictional corrections; each reason says it is fictional.
- Q3: A - REQ-GEN-203 builds Child Protection lead-ins and targeting.
- Q4: A - TS-63's turn-off correction is dated before the gap.
- Q5: A - a top-level `corrections:` list in contract/scripted_decisions.yaml.
- Q6: A - two corrections: one confirmed carrying TS-57 to TS-61, one left pending.
- Q7: A - TS-62 on Birth Registrations; every correction dated late in the history.
- Q8: A - each correction edits one grown quarter's date per shape.
- Q9: A - TS-61 stays parked to the end, a standing item.
- Q10: A - TS-48 counts as demonstrated by TS-75; TS-49 and TS-51 not planted, Keith's reason recorded.
- Q11: B (NOT the recommendation) - TS-53 gets a person's promote, and REQ-GEN-137 criterion 2 is amended to match.
- Q12: A - TS-50 planted in full, in a grown quarter under a short Child Protection green-replacement era.
- Q13: A - TS-54 rides TS-76.
- Q14: A - build TS-47's following day green and record why its late file is held.
- Q15: A - reword REQ-GEN-199 criterion 9 to what was observed (clients amber, carers green).
- Q16: B (NOT the recommendation) - draft a period-composition view on the dashboard for TS-55; a new requirement to scope.
- Q17: A - every cross-table cause gets the line.
- Q18: A - row note, "Affects ..." on the contested banner, and one line on the collection card.
- Q19: A - page and terminal; a small pipeline requirement drafted now for the terminal queue.
- Q20: A - REQ-DASH-204 is Must.
- Q21: A - after "reject both", readers are re-checked via a small pipeline follow-up.
- Q22: A - the Child Protection Synthetic-mode picker lists a two-file arrival marked, and refuses when picked.
- Q23: A - the period chooser also replaces the typed period in the settle flow's re-file (amends REQ-PIPE-193).
- Q24: B (NOT the recommendation) - a scenario jump survives a reload, carried in the URL (REQ-DASH-208).
- Q25: A - keep REQ-PIPE-163 criteria 35 and 36.
- Q26: B (NOT the recommendation) - add the "Turning off after <date>" foreshadow marker to REQ-DASH-180.
- Q27: A - amend REQ-DASH-175 ("Placed in <period>"), presented with REQ-PIPE-163.
- Q28: A - a replayed correction's confirmation is stamped at the later of the history's end and the correction's own date (post-build-review #177).

Answers are not sign-off: the draft is re-folded with these, the five
non-recommended answers (Q11, Q16, Q24, Q26, and Q16's new view) get
criteria drafted, and each requirement then goes to Keith for sign-off.

## Keith's answers to the 15 follow-up questions (2026-10-14, via AskUserQuestion)

- F1: A - REQ-DASH-209 has its own address per collection and period, linked from each period row of a dataset's supply history and from the standing-in drill-down.
- F2: A - every collection, daily ones too.
- F3: the person's name, as the rest of the page shows ("the rule" where no person decided). Note: the main session presented this as the recommendation, reversing the scoper's order (it recommended "rule"/"person" as _manifest says), for consistency with REQ-DASH-198's stand-in fix.
- F4: A - datasets holding nothing are listed as "Nothing held" with the slot's state.
- F5: A - a pair ended by a later file that is not promoted also re-checks the readers.
- F6: A - a reader listed beneath its cause does NOT count in "Supplies waiting on a decision (N)".
- F7: A - in the terminal the readers' re-check runs while you wait, with the settlement's own runs.
- F8: B (NOT the recommendation) - plant a "reject both" Child Protection scenario, at the cost of another grown quarter (REQ-GEN-207's dry run must include it).
- F9: B (NOT the recommendation) - the "Turning off after <date>" marker shows from the date the turn-off version was authored (its changelog entry date), on any date on show from then.
- F10: A - a scenario chip becomes a real <a href> link.
- F11: B (NOT the recommendation) - TS-62's Birth Registrations correction is a new daily version near the end of the history with a different claim window. Consequence to carry: once confirmed it would re-judge every later day, but TS-62 is the correction LEFT PENDING, so its moves show as awaiting confirmation; its effective date must fall after every quoted Birth Registrations scenario day (TS-78 ends 2026-09-01) or REQ-GEN-199's quotes move - REQ-GEN-207's dry run / REQ-GEN-205 should check that.
- F12: A - TS-53 is on Birth Registrations.
- F13: A - REQ-GEN-136 criterion 4 keeps its wording; its unmet entry is cleared with evidence naming TS-75.
- F14: B - REQ-PIPE-211 is must; REQ-DASH-209 and REQ-PIPE-210 are should.
- F15: A - REQ-DASH-209's page weight is measured before and after and reported, with no budget yet.

Folded 2026-10-14. Each answer is a decision citing "Keith, 2026-10-14, follow-up FN", and each answered question is gone from its requirement. F5 revised amendment 27. F6, F9 and F11 raised the new questions under "Still open" above. Answers are still not sign-off.

## Keith's answers to the round 4 questions (2026-10-14, via AskUserQuestion)

- R1 (TS-62, scoper's new question 5 + architect D): A - TS-62's new daily version takes effect after 2026-09-08, clear of TS-47's window; REQ-GEN-205's "nothing else moves" rule (criterion 10) is narrowed, for a version-level correction, to the periods the correction's impact preview would move; TS-46's last day checked at build; the new claim window is wider (e.g. 6h) so the default view stays quiet.
- R2 (the still-failing shout, architect C / CLI UX 3): Keith - "Shout, but don't say it's waiting on a person. Wouldn't this be the same shout you'd get if the tables it depends on just never turned up?" So: the still-failing record stays, worded to name what the readers wait on (REQ-DASH-204 criterion 15's cause wording) and never "A person decides", where every red is another table's; a reader with its own fault keeps today's wording. Checked in knock_on.py for his question: NO - today a table that never turns up raises no shout at all, because the shout is only raised by a re-evaluation, and only a move or (after REQ-PIPE-211) the end of a contest causes one. A never-arrived dependency leaves the readers red, explained on the page and in the queue (REQ-PIPE-115's reason), with nothing in the decision log. The asymmetry is that the shout records a decision's consequence; put back to Keith.
- R3 (TS-79b's text, architect A): A - reword to "the oldest of the original fifteen quarters".
- R4 (exit code, CLI UX A2): A - REQ-PIPE-163's distinct "recorded, still owed" code when a settlement is recorded but a run or the readers' re-check is left owed. Amends built REQ-PIPE-193.
- R2 follow-up (should "reject both" still shout, given a never-arrived table raises none?): Keith asked first what the page shows today when a dependency never arrives. Checked (unrunnable.py, qa.check_result): it depends on the dependency's state AT THE READER'S ARRIVAL, recorded once and never revisited. Not yet due -> the cross-table check records `nodata` ("not evaluated - not yet supplied, not yet overdue"), the reader can read GREEN and be promoted, and nothing re-checks it when the dependency later goes overdue or never comes (a false green). Already overdue, contested or awaiting a decision -> the check records `fail` ("could not be evaluated"), which rolls up, so the reader reads RED with no failure of its own (real example: a cp-investigations run, zero own failures, red for a missing cp_carers). Keith's instinct: that is neither a true green nor a true red.
- R5 (a distinct "waiting on another table" state, and re-checking 'not yet due' readers when the dependency goes overdue): SCOPE IT FIRST (Keith) - a design question for the scoper and architect, decided as part of that scoping, alongside this batch. REQ-DASH-204, REQ-PIPE-210, REQ-PIPE-211 and the shout question all hang on it. Logged as plans/running-thoughts.md #95.
- R6 (REQ-DASH-209 at 30 datasets, dashboard UX D1): B (NOT the recommendation) - every row open; no collapsing of rule-promoted-on-green rows.
- R7 (REQ-DASH-209 "Nothing held", D2): A - split: "Not supplied" (owed: red or waiting) at the top, "Not owed" (turned off, not expected, outside agreed months) at the bottom, each counted.
- R8 (REQ-DASH-180 marker date, scoper new Q1 + D3): A - the changelog entry setting the turn-off carries `turns_off: true`, checked by validation; where a correction sets it, the correction's own date; validation refuses a turn-off with no such entry.

## Sign-off walk (2026-10-14)

- REQ-GEN-207: SIGNED by Keith, 2026-10-14, with the round 4 architect's changes folded in (a new earlier calendar version; today's plan passes the widened clash rule; the seven oldest-quarter indexes drawn separately with a byte proof; a before/after results comparison reported as findings; TS-79b reworded). Moved out of this draft into requirements.yaml.
- REQ-PIPE-202: SIGNED by Keith, 2026-10-14, criterion 4's reader status deferred to running-thoughts #95; amendment 7 approved with it. Moved into requirements.yaml.
- REQ-GEN-203: SIGNED by Keith, 2026-10-14, readers' status deferred to running-thoughts #95, REQ-PIPE-211 added as a dependency. Moved into requirements.yaml.
- REQ-PIPE-163: SIGNED by Keith, 2026-10-14, with the nine amendments it carries approved in their exact wording (2, 11, 12, 18, 19, 20, 31, 32, 42). Replaced its older unsigned entry in requirements.yaml; removed from this draft.
- REQ-DASH-182: sent to its own UX review at Keith's ask before signing (review-182-ux.md); his four answers recorded there. Re-folded 2026-10-14 (findings 2 to 11 and Q1 to Q4; finding 1 replaced by a regression guard, criterion 15, after the browser check and post-build-review #178); to be presented again.
- REQ-DASH-208: SIGNED by Keith, 2026-10-14. Moved into requirements.yaml; removed from this draft.
- REQ-GEN-205: SIGNED by Keith, 2026-10-14. Moved into requirements.yaml; removed from this draft. Amendment 47 (re-pointing its criterion 10 at REQ-GEN-218) is proposed against the signed text.
- REQ-GEN-206: HELD by Keith, 2026-10-14, until running-thoughts #95's shape is settled.
- REQ-DASH-182: SIGNED as is by Keith, 2026-10-14, after its own UX review and the H1-H3 fold. Replaced its older entry in requirements.yaml; removed from this draft.
- REQ-PIPE-179: SIGNED by Keith, 2026-10-14, with the own-pass answers Q1-Q4 folded and its 22 amendments approved in their exact drafted wording (13, 14, 16, 17, 21-26, 28-30, 33-41), to be applied when it is built. Its provisional choices (N counts supplies; the newest correction or entry wins; a turns_off entry with no effective_to is accepted and read by nothing) stand as signed. Replaced its older entry in requirements.yaml; removed from this draft.
- REQ-GEN-218: SIGNED by Keith, 2026-10-14, with TS-63's links answered as option A (two lettered links, criterion 8; built after REQ-GEN-205), cp-carers and must as drafted. Amendments 45 to 47 applied to requirements.yaml in the same change, as its criterion 7 requires. Added to requirements.yaml; removed from this draft.
- REQ-DASH-209: SIGNED as is by Keith, 2026-10-14. Added to requirements.yaml; removed from this draft.
- REQ-DASH-180: SIGNED by Keith, 2026-10-14, with R8 folded into criterion 27 (the marker starts from REQ-PIPE-179 criterion 41's authored date: the newest correction setting effective_to, otherwise the turns_off: true entry), criterion 22 narrowed to the two amendments that change text, and amendments 1 and 15 approved in their drafted wording, applied when it is built. Replaced its older entry in requirements.yaml; removed from this draft.
- LEFT IN THIS DRAFT, all waiting on running-thoughts #95's shape: REQ-DASH-204, REQ-PIPE-210, REQ-PIPE-211 and REQ-GEN-206 (held).

## Keith's answers to the round 4 fold's questions (2026-10-14)

- G1 (REQ-DASH-209 previous/next-period links): B (NOT the recommendation) - YES, previous and next period links beside the heading, keeping the date on show.
- G2 (REQ-DASH-209 who decided): A - the page's own wording, "Decided by <name>" / "Applied automatically by the schedule".
- G3 (REQ-GEN-205 which corrections a replay confirms): B (NOT the recommendation) - everything due, as today, unless the script says pending. The provisional "confirm only listed" criteria and amendment 44 (REQ-PIPE-170 c31) are withdrawn.

Folded 2026-10-14 by delivery-scoper. G1 is REQ-DASH-209 criterion 14, and G2 is criterion 3's exact wording; both of 209's open questions are removed. G3 restores REQ-GEN-205 criteria 4, 5 and 6, removes criterion 28 and drops amendment 44. Each is recorded as a decision citing "round 4 fold G<N>". Answers are still not sign-off.

## Keith's answers to the REQ-DASH-182/209 fold's questions (2026-10-14)

- H1 separator: A - the page's em dash; REQ-DASH-180's "Turned off — nothing due" follows suit.
- H2 the "Not owed yet" notice body: A - keep only the way-back sentence; drop "There is no QA run within the accepted freshness window".
- H3 the standing-in heading on a past date: A - "On <date>: <kind label>"; the label alone on the present; the reason in .promo-why.
- H4 REQ-DASH-209's previous/next links at the ends: A - left out where there is no earlier period, or the next had not opened by the date on show.

Folded 2026-10-14 by delivery-scoper. H1 is REQ-DASH-182 criteria 2, 3 and 14 and REQ-DASH-180 criterion 16; H2 is REQ-DASH-182 criterion 3; H3 is criterion 9; H4 is REQ-DASH-209 criterion 14 as already written. Each is a decision citing "Keith, 2026-10-14, H<N>", and the four open questions are removed. Answers are still not sign-off.

## REQ-PIPE-179's own scoper pass: Keith's answers (2026-10-14)

See req-179-own-pass.md: split TS-63 into its own generator requirement built after REQ-DASH-180; refuse keep on a parked move into a gap; one row per dataset in "Received while turned off"; turned-off holds kept quiet, retention to running-thoughts #77.

Folded 2026-10-14 by delivery-scoper. The own pass's REQ-PIPE-179 replaced the draft's. Q1 is REQ-GEN-218 (new), with criterion 39 as a pointer and amendments 45 to 47. Q2 is criteria 36 and 37 and amendment 40. Q3 is criterion 34. Q4 is the PRIVACY NFR and a decision. Each is a decision citing "Keith, 2026-10-14, own pass Q<N>". `req-179-own-pass.yaml` is merged and deleted; `req-179-own-pass.md` stays as the pass's record. Answers are still not sign-off.
