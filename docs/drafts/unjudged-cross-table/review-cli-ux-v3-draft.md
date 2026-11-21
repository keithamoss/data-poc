# delivery-cli-ux on requirements-draft-v3 (2026-10-21)

## Landed / partly / missing

- **267 c11 (exit code): landed.**
  - Reword: count the re-evaluation's red toward `has_failures`/`PassReport.red`; `exit_status` precedence stays (backstop 3 > red 1).
  - Add a failing-first test: S1 red, `mothman cp qa --commit` exits 1 and shows a "re-checked against the warehouse" table.
- **266 c5 (not gated yet): landed.**
- **267 c12 (next step): landed.**
  - Add a condition: "while the package-mate is waiting; once it is rejected or superseded, the supply's own decisions".
  - Name the surfaces: `outcome_panel` and `_recheck_panel`.
- **Vocabulary contradiction.**
  - c13 opens "Refused:", which REQ-PIPE-163 c20 forbids for a gate outcome, and 266 c9's "refusal" names no decision-log action.
  - Fix: make the action `promotion-withheld`, and c13 "Held back: <check>, re-checked against the <dataset> in place (received <instant>) because the <dataset> received with it was not promoted".
  - Missing: the supply never appears in "Held - no period yet", and there is no NO_COLOR/pipe test per surface.
- **267 c13 is missing two things.**
  - The locus clause "This supply's own checks passed."
  - `Unrunnable.describe()` has no text for 270 c4's new reason "not promoted with its package", so it falls to the wrong catch-all. Criterion: no reason reaches the fallback.
- **Terminal grouping at ~30 datasets: missing.** Under `_grouped`, one line for the root's own red, then one line per outcome; for a cascade, final states naming the root.
- **267 c15 (override text) misses T13/S5.**
  - In S1 red, cp-clients v2's re-check read Notifications v1, which IS in place, so c15 is silent. Add the "will become Promoted, then re-checked worse" warning when a knock-on would re-run a check already recorded red for the same pair.
  - Add a line when promoting Notifications v2 ("re-checks cp-clients' waiting supply... if green, the rule promotes it").
  - Both go in `apply_decision`'s consequences key.

## New scenarios

- **N1.** After a hand decision, the terminal says nothing about package-mates the knock-on promoted (`_follow_up` prints only incomplete ones). List each one re-gated and its outcome.
- **N2.** A cascade in the queue: list flat under the root, each line naming what it traces through.
- **N3.** Deciding mid-gate: refuse ("The delivery received <instant> is still being checked or gated (1 of 2 files checked); decide once it is gated"), before the reason prompt.
- **N4.** A crashed sibling: "checked, waiting for its package - cp-notifications' run stopped at the soda stage; the next pass re-runs it and gates both."
- **N5.** Re-filed siblings (T14): warn on re-filing one without the other.

## Questions (merged)

- **Q8 (queue).** Recommended A': listed beneath its cause, not counted ("1 waiting on a decision (1 more waits on it)"), but pickable, with "Deciding cp-notifications 2024-Q3 settles this one" and a hand promotion one step away. It becomes its own row once the cause is rejected.
- **Q10 (rejected sibling).** Recommended A: no re-check, and every surface words the reason from the decision log as it stands now.
- **New, a decision on a package still being gated.** Recommended: refuse.
