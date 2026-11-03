# Geocoding v5 - dashboard UX delta review (2026-10-31)

Every earlier finding is resolved: N1 by REQ-DASH-299 c3, N2 by c5, N3 by c16, N4 by c10, N5 through A1 to A3, attribution by REQ-QAC-340 c10, the G1 route by c15, Q11 by c2.

MUST:
- M1. A1 does not say what a group heading shows when the checks in it are left out. Its pill is rollupStatuses over the rows, and groups are collapsed on load, so the heading is all a reader sees. Fix: the pill ignores left-out rows; it is a neutral 'Not checked' when nothing in the group was evaluated, never green and never 'No data'; and the count uses the row's word ('3 checks: 1 pass, 2 not checked'). Pick one word: 'Not checked' (row), 'Not run' (.nia-tag) and 'not checked' (A1) disagree today.
- M2. c15's proof for A1 and A2 cannot fail in the ways that matter. Fix: name the scenario and period; assert at least one such row exists; assert it is absent from .not-in-agreement; assert the heading count says 'not checked'; assert the pill excludes it.

SHOULD:
- S1. Test c5's 'No examples were recorded for this result.' and its percentage-only branch (no heading, no sentence) in Vitest (c16). No real page shows the first once REQ-PIPE-341 fixes #291.
- S2. Carry the .nia-note sentence ('neither red nor a result, and does not count toward this dataset's status') into the group, once per group.
- S3. A2's stated reason for the short name is wrong on the source page, where the row sits in the Linkage Products group. Fix the reason; the wording itself still reads clearly.
- S4. A check with no phrase keeps 'Example failing rows (primary key only)' and 'Rows flagged'. Use 'Examples (key only)', 'Flagged, this run' and 'Examples vs. the compared run' instead.
- S5. Add c12's three trend breaks to c15: three breaking markers on one year check.

NIT: say 'dataset', not 'table', in A3's blurb; say plainly that c9's tile is absent on a date with no recorded result; add a regex proof for c13 (no area code shown).

QUESTIONS FOR KEITH:
1. 'source record' or 'source row' in the sample lines? Recommends 'source record'.
2. A2 drops 'by decision'. Keep it: 'Not checked: Client Register not supplied for 2024-Q2, by decision'? Recommends yes.
3. Should A1 cover every left-out reason, not_in_agreement included? Recommends yes.
