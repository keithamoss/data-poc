# Geocoding v5 - architect delta review (2026-10-31)

Resolved by a criterion that would hold against the built code: B3, S1 (the provider side), S3, S4, S5, S6, S7, S8. Only partly resolved: B1 and S2, see BLOCKING 1 and 2.

BLOCKING:
1. The real-tool trial (REQ-GEN-186) cannot see the checks it is meant to confirm (REQ-GEN-298 c3/c4/c7, REQ-GEN-295 c7):
   - A trial is never filed, so it has no period: period_overlay.py:10-17 and :334-336 return None, and one_table.py:78-81 runs it on a local file.
   - With no period, the year checks are recorded not evaluated (REQ-QAC-297 c4).
   - target_agreement.own_results (:132-146) drops cross-table checks recorded not evaluated, so orphan and coverage are never judged.
   - Only injected targets are tried (one_table.py:69), so the ordinary share-driven ambers are never confirmed.
   - targets.csv_of refuses a delivery of two CSVs (:180-182).
   Fix: give the trial its slot's period, with its declared foreign reads coming from that period's warehouse.
2. The valid-values rule (linked_datasets.py:92-95) compares every valid-values list against the mapping's codes, which are {None} for a code-less entry, so geocoding's match_level check fails the gate. REQ-QAC-294 c5 must limit the rule to the check on the code column, and skip it when the entry has no code.

SHOULD:
- The generator driver assumes one dataset (driver.py:162,173,192,222; one_table.py:65,87). Interleaved geocoding jobs shift linkage's bookkeeping run ids, which breaks 295 c2's byte-identity. Put the driver in 295 c1's scope, or fix the job order. 295 c10's own-stream half is redundant.
- Census words would reach shared code: REQ-QAC-300 c2's key in schemas.py and validate_schedule.py:856, describe() worded for amber and assuming a string (amber_setting.py:126,150), and address columns and match levels on LinkedDataset (schemas.py:562-571, hierarchy.py:187). Use a generic container of list settings instead.
- The page cannot render REQ-DASH-299 c6/c7 from what is recorded:
  - the build must carry the key's column names, since the page cannot tell id parts from census_year;
  - '2 rows' needs a count that 341 c6 forbids recording;
  - '(in force from 2026-Q3)' contradicts c9's 'never re-resolve'.
- REQ-PIPE-341 sampling:
  - state the sort order, since sorting lists that hold None raises TypeError (soda_common.py:138, datacontract_common.py:271);
  - dbt_common.py:339-340 and the datacontract pk filter still lose samples silently;
  - c5's gate covers Soda only, so make a missing key column loud in every sampler.
- REQ-QAC-300 c4: offsets resolve on the ROUND date (agreement.py:171-175), so name the date. 2017-08-01 is 2017-Q3 only by the round date.

NIT: 300 c5 should say 'any dataset whose checks name the setting'; 341's linkage query edits need non-breaking changelog entries; comparing samples across a change of key shape shows every sample as new.

Amendments A1-A4 are each buildable; their claims about the current page are accurate.
REQ-PIPE-341 can be built first and alone. Its c7 needs a before-and-after compare of a from-empty bootstrap (about 30 minutes or more).

QUESTIONS FOR KEITH:
1. An id column that is always empty (N=2, one id used): (a) always show '—'; (b) drop trailing empty parts from the display only. Recommends (b).
2. How should the trial get a period (BLOCKING 1)? (a) Use its slot's period and read that period's warehouse; (b) confirm those verdicts from the recorded results after the bootstrap instead. Recommends (a).
