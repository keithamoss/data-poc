# TS-113: a geocoding file that drifts on purpose (draft for Keith, 2026-11-16)

**Why.** REQ-GEN-392 made Child Protection's red Client Registers cleaner: a
single-tier Fail now plants 5 rows. The 2019 geocoding files then held fewer
postcode placements, and the only three drift Warns in the geocoding history
went green: TS-93c (2019-Q1), TS-100c (2019-Q3) and the ordinary 2019-Q4 file.
Those Warns were side effects, recorded as a finding in REQ-GEN-298's decisions.
This draft replaces them with one planted on purpose. Keith chose this option
on 2026-11-16 (REQ-GEN-392 criterion 12).

## The scenario (proposed wording for SCENARIOS-quarterly.md)

### TS-113 - A Client Register geocode whose placed mix drifts

**What it demonstrates.** The drift check on `match_level` reads Warn: the
share of records placed at each match level has moved from the quarter before.
Every other check of the file passes.

**What it would look like if the rule were wrong.** The drift check reads Pass
on a file whose placed mix visibly moved. Or the drift is read against the
wrong reference: anything other than 2019-Q3's file, which the replay has
promoted by then.

*Config: 2019-Q4's ordinary Client Register Geocodes. Enough records are moved
from suburb placement to postcode placement to land the drift check's PSI in
its warn band. The size is derived from the check's own band, as REQ-GEN-392
derives fault sizes.*

| Where to look | |
|---|---|
| Dataset | geo-cp-clients |
| Period | 2019-Q4 |

## How it would be built (PROVISIONAL until approved)

1. A new named geocoding row fault, `placed_mix_shift@geo-cp-clients`, in
   `GEO_ROW_FAULTS`, aimed at `match_level.drift_psi_evidently`
   (`GEO_FAULT_AIMS`), built to amber (`GEO_FAULT_VERDICT`). It moves whole
   records from `suburb` to `postcode` in every year, as many as put PSI
   against the reference at the middle of the warn band. It reads that band
   through `check_bands`, as REQ-GEN-392's Warn rule does. The planner refuses
   it if no count lands in the band.
2. TS-113 registered as a named scenario in 2019-Q4 (one geocoding scenario a
   quarter; 2019-Q4 has none today).
3. The two failing tests then hold through TS-113:
   - "the history holds drift" is true again by design;
   - 2019-Q4's file is tried again, so its recorded reference is 2019-Q3's
     file, which the replay has promoted (TS-100c), as before.
4. REQ-GEN-298's recorded finding that "the drift check reads Warn on TS-93c and
   TS-100c, and on 2019-Q4" would be amended as history: it was true before
   REQ-GEN-392 and is replaced by TS-113. That is an edit to a built
   requirement's decisions, so it needs your sign-off.
5. Regenerate SCENARIOS-quarterly.md and the scenario map, then confirm on the
   replay that TS-113 lands Warn on the drift check alone. That confirmation
   comes from REQ-GEN-392 c11's from-empty bootstrap.

## Questions

- Is 2019-Q4 the right quarter? It keeps the reference test's meaning. Any
  quarter with a promoted predecessor would do.
- Is Warn the right verdict, or do you also want a Fail drift scenario?
