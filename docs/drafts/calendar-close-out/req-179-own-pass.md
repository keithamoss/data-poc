# REQ-PIPE-179: its own scoper pass (2026-10-14)

Keith asked for this before signing. Until now REQ-PIPE-179 had only the joint 2026-10-13 pass it shared with REQ-PIPE-163 and REQ-DASH-182. The revised text is in `req-179-own-pass.yaml`, a list holding just this one requirement. It is a draft: nothing is signed, and neither `requirements-draft.yaml` nor `requirements.yaml` was edited.

## Should it split?

**Mostly no, with one exception: TS-63.**

- **The core stays as one requirement.** That covers the declaration, freeze, slots, filing, holds, counts, refusals and inheritance. These parts are not useful on their own. If a turn-off could be declared before arrivals honoured it, every delivery in the gap would raise an ordinary needs-action hold. The filing half also can't be tested without the declaration.
- **The terminal display stays here too** (criteria 28, 29 and 34). Signed REQ-PIPE-163 criterion 17 cites criterion 34 by number, and signed REQ-PIPE-181 criterion 13 cites criterion 29. Moving three criteria would mean amending two signed requirements.
- **TS-63 (criterion 39) should become its own REQ-GEN requirement, built after REQ-DASH-180.** That is my recommendation, and it is question 1 below. Three reasons:
  - TS-63's register entry quotes REQ-DASH-180's quiet line and its "Turning off after" marker. Neither exists when 179 is built, because 179 comes before 180 in the build order.
  - Criterion 39 is the only reason 179 depends on REQ-DASH-180, and 180 depends on 179, so today the two depend on each other. Splitting TS-63 out removes that loop.
  - It follows the pattern already used for REQ-GEN-203 (scenarios for REQ-PIPE-202) and REQ-GEN-205 (scenarios for REQ-PIPE-170).

  The cost is re-pointing two citations: REQ-PIPE-170 criterion 23 (signed) and REQ-GEN-207 criterion 2. Your 2026-10-13 decision that "179 takes TS-63 over from 170" still holds in spirit, because TS-63 would still land with the turn-off work rather than with 170. Until you answer, criterion 39 stays in 179.

## What changed

Criteria 1 to 39 keep their numbers, because signed REQ-PIPE-163, 170 and 181 cite them.

- **(b) Criterion 40 dropped.** It was already met: the register already re-points REQ-PIPE-170's unmet entry. Its number now holds R8's validation rule.
- **(c) Criteria 24 and 32 trimmed.**
  - Criterion 24 no longer names REQ-PIPE-083 criterion 21. That criterion's ticket policy works per slot, and a held supply has no slot, so it never gets a ticket.
  - Criterion 32 now names REQ-PIPE-053 criteria 10 and 15 only. Criterion 4 just says the supply is held, and leaves the label to REQ-PIPE-154.
- **(a) Amendment 40 is now written into the criterion, and I recommend keeping it.** Criterion 36 now says keep is refused "neither when the correction's moves are confirmed nor later while its move is parked".
  - Without this, a supply could be parked and then kept, which ends in exactly the state your round 3 Q9 forbade.
  - The extension has a cost: a parked move can end up with configuration as its only way out. Criterion 37 now says what ends such a move.
- **R8 is wired in through two new criteria.**
  - New criterion 40 refuses a turn-off whose version has no changelog entry with `turns_off: true`. It also refuses any `turns_off` value other than true, and prints a changelog entry ready to paste.
  - New criterion 41 sets the date a turn-off was authored. Where a correction set or moved effective_to, it is the date of the newest such correction. Otherwise it is the date of the newest changelog entry with `turns_off: true`. The build carries that date, with effective_to, the reason and the level, for REQ-DASH-180 criteria 27 and 28.
  - Criterion 39 now has TS-63's version carry that changelog entry. TS-63's register entry quotes the marker from the correction's date.
  - Found in the code: `agreement._changelog` keeps only date, author and change today, so the new field has to be parsed, not just tolerated.
- **Criteria 20 and 37 now say which amendments they carry.** These are batch amendments 33 (REQ-PIPE-141 criterion 12) and 39 (REQ-PIPE-170 criterion 26). Both were marked "not promised by the draft", so every one of the 22 amendments now traces to a criterion that names it.
- **Criterion 38 was reworded after reading the built code.**
  - `verdict.compared` already treats a recorded slot as gone when it is no longer generated or is now not expected, and `agreement_drift` refuses the dataset in that case. So the old open question is answered for the comparison itself.
  - Two things are still missing: a declared correction of effective_to being accepted as accounting for the change, and a refusal that names the turn-off instead of calling the period "not expected".
- **Criterion 19** now files through REQ-PIPE-163 criterion 40's one shared placer, so it matches 163's placement rules.
- **NFRs.** Auditability now covers `turns_off`, and security says `turns_off` accepts only true. New NFRs:
  - fail loud: no consumer falls back to "owing" or to "turned off";
  - scale;
  - privacy (provisional);
  - tests of their own for the amendments no other criterion states;
  - per deployment.
- **Dependencies.** A duplicate REQ-PIPE-111 entry was removed.

## Check against REQ-PIPE-163 (signed)

These all agree:

- 163 criterion 7 gives way to 179 criterion 20.
- 163 criterion 17's "Held" group sits above the slot rows; 179 criterion 34's quiet group sits after them.
- 163 criterion 38's responses are worked out by 179 criterion 18.
- 163 criterion 37: a held pair moves whole, and 179 criterion 19 re-files it whole.
- 163 criterion 40's shared placer is now named in 179 criterion 19.
- Neither requirement amends the other.

## Carry-over check

I walked through REQ-PIPE-110's decisions and Keith's answers it was split from, running-thoughts #77 and #92, morning reports, the TS-63 register entry, the three round 3 reviews, the summary's amendments, and F9 and R8.

Three things had been carried by nothing, and each is now a decision or criterion:

1. **The rejected `active:`/`enabled:` flag.** It sat only inside a decision marked SUPERSEDED for three other rulings, so it read as withdrawn too.
2. **Why turned_off_reason is kept separate from reason.** One version can be both partial and turned off. This was recorded only in REQ-PIPE-110.
3. **R8, and F9's promise that 179 would carry the authored date.** These are now criteria 40 and 41.

Two more are noted but not added here:

- **The TS-63 register text in plans/supply-model.md is out of date.** It still uses the 15th-of-month configuration and the pre-T8 marker wording. Criterion 39 already says to rewrite it.
- **REQ-DASH-155 criterion 3** has a corner case about the time after a schedule ends that was left for the architect. It belongs to REQ-DASH-180.

Everything else (Q-K, Q-B, Q-F, Q-G, T1 to T7, round 3 Q2, Q3, Q6, Q8 and Q9, set 2 Q5 to Q8, A4, A5, E21, F24, close-out Q2 and Q4) is carried by a criterion or a decision.

## New wording that needs your approval

- **Criterion 36:** "THE SYSTEM SHALL amend, in the same change, REQ-PIPE-170 criteria 5 and 28 so that IF a corrected configuration makes a supply's current period one its dataset owes nothing in - by participation, not_expected or a turn-off - THEN keep is not offered for that supply, neither when the correction's moves are confirmed nor later while its move is parked, and the correction proposes moving it to the owed slot the filing rule gives it or holding it, saying that the period no longer owes a supply."
- **Criterion 37:** "...say so naming the gap, its turned_off_reason and what ends it - keeping the supply where it is, where criterion 36 still allows that, or changing effective_to or effective_from in contract/calendar.yaml - ... and THE SYSTEM SHALL amend, in the same change, REQ-PIPE-170 criterion 26 to except such a move."
- **Criterion 38:** "...a judged period which an effective_to added or moved without a declared correction now leaves owed nothing counts as changed, as one a not_expected entry declares owed nothing does - the refusal naming the turn-off rather than calling the period not expected - and is accounted for only by a declared correction of that effective_to."
- **Criterion 40:** "IF a participation version - a dataset's, or a collection's participation_defaults version - states effective_to and none of its changelog entries carries turns_off: true, or IF any changelog entry in contract/calendar.yaml carries turns_off with a value other than true, THEN THE SYSTEM SHALL reject the configuration, naming the dataset or collection and the version by its effective_from, and printing a ready-to-paste changelog entry - date, author, change and turns_off: true - on lines of their own."
- **Criterion 41:** "THE SYSTEM SHALL take the date a turn-off was authored as the date of the newest declared correction (REQ-PIPE-111) that set or moved that version's effective_to, where there is one, and otherwise as the date of the newest changelog entry on that version carrying turns_off: true; and SHALL carry, for every participation version stating effective_to, its effective_to, its turned_off_reason, its level and the date it was authored into what the dashboard build reads, for REQ-DASH-180 criteria 27 and 28."
- **Criterion 20's added clause:** "...and THE SYSTEM SHALL amend, in the same change, REQ-PIPE-141 criterion 12 so that for a period inside a turned-off gap this refusal is given in place of its un-inherit advice."

Amendment 40's wording in the summary still matches criterion 36. If you approve the extension, the summary's note "PROPOSED BY THE SCOPER, not promised by the draft in words" can come out.

## Questions for Keith (one set; recommended option first)

1. **Split TS-63 out?**
   - **A, recommended:** make it its own GEN requirement, built after REQ-DASH-180. Its Expect quotes 180's marker and quiet line, the two requirements stop depending on each other, and it matches the REQ-GEN-203 and 205 pattern. The cost is two re-pointed citations.
   - **B:** keep it in 179, as decided on 2026-10-13. TS-63's dashboard Expect can't be checked until 180 is built.
2. **Refuse keep on a parked move as well (amendment 40)?**
   - **A, recommended:** yes, as now written in criteria 36 and 37. Otherwise a supply can be parked and then kept, which leaves it kept in a period with no slot, the case Q9 forbade.
   - **B:** drop the extension, so keep on a parked move stays allowed.
3. **How should the terminal's "Received while turned off" group list supplies at thirty datasets?**
   - **A, recommended:** one row per dataset showing its count and earliest receipt, opening to list its supplies. A supplier still sending daily files would otherwise add 365 rows a year.
   - **B:** one row per supply, as drafted.
4. **What happens to turned-off holds, which pile up because nobody is asked to act on them?**
   - **A, recommended:** leave them quiet and kept, and move the retention question (real personal data the agency asked the supplier to stop sending) to running-thoughts #77.
   - **B:** add one action per dataset in the terminal that rejects everything received while turned off, with one reason.

Provisional choices I did not put to you:

- cp-carers as TS-63's dataset;
- "the newest" correction or entry when there are several;
- a `turns_off` entry on a version with no effective_to is accepted and read by nothing.

Build-time checks for the architect:

- whether criterion 19's re-filer acts before REQ-PIPE-170's confirmation of a correction that is declared but not yet confirmed;
- criterion 38's remaining check (`_sources` and the key for the effective_to item).

## Non-functional angles

- **Answered myself:**
  - performance: the existing helper NFR;
  - reliability: fail loud (new);
  - security: reasons rendered as text, `turns_off` true only;
  - auditability: changelog plus `turns_off` plus corrections, with the changelog date unfrozen, a cost already accepted in F9;
  - maintainability: consumers enumerated, and the amendments no other criterion states each get their own tests;
  - multi-asset: each deployment has its own calendar.
- **Put to you:**
  - scale (question 3);
  - privacy and retention (question 4).
- **Ruled out:**
  - compatibility: configuration only, no new assets or dependencies;
  - cost: file checks on unwanted files are trivial;
  - the one-off project-extraction asset shape: it has no participation versions, so a turn-off does not apply.
- **Not re-asked:** whether a turn-off before its freeze should need an approver. You rejected that at Q-K as "the gate that fires on legitimate work".

## Validation

- Merged into a copy of requirements.yaml, replacing the register's older REQ-PIPE-179, at `/tmp/claude-0/-home-user-data-poc/5735d9c2-23bf-590b-afe1-e67b136c7e21/scratchpad/merged179.yaml`, `uv run mothman dashboard validate-requirements --draft` gives "requirements validation OK - 199 requirements, zero errors."
- The one-item file on its own reports only the 24 expected cross-reference errors, one for each dependency the file doesn't contain.

## Keith's answers (2026-10-14)

1. Split TS-63 out: A - its own generator requirement, built after REQ-DASH-180.
2. Refuse keep on a parked move into a gap (amendment 40): A - yes, as written in criteria 36 and 37.
3. "Received while turned off" group: A - one row per dataset with its count and earliest receipt, opening to its supplies.
4. Turned-off holds that pile up: A - keep them quiet and kept; the retention question goes to plans/running-thoughts.md #77.
