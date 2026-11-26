CLI UX review round 3 (2026-10-14) - key items:
1 HIGH 202 c8: CP Synthetic-mode trial (cli/cp.py run_check -> _load_delivery_from_folder loads f"{table}.csv") silently checks cp_clients.csv of a pair; cp load_manifest doesn't exclude contested (bdm does). Reference folder same. Fix wording: every CP load route attributes by pattern; refuse dataset matching 0 or >1 files naming files + settle path; never trial either.
2 HIGH 205 c4: keep must name scenario + DATASET + supply index (TS-67 style); c5 refuse dataset the arrival does not carry.
3 MED 163 c39: refusal of promoting a held supply must give the hold's own responses (place+reject plain/turned-off; add dates for schedule-ended); commands each on own line (built text is inline backticks; _show lifts only lines starting 'mothman ').
4 MED 163 c2 'every surface says placed': fd.apply message lacks destination; filing_tui where/period None; _NOUN lacks place; supply decisions renders 'None -> P'; supply filings raw branch; refiling lock refusal says re-filing. Wording: every route calls it placement into <period>, never re-file/None/machine name; 'place' stays in OPERATIONS.
5 MED 163 c19: run panel says 'again'/'earlier verdict stands' - wrong for a placement; say 'not yet been checked in <period>'.
6 MED 163 c37 held pair: one row naming both files, counted once; moving second file is a consequence line (--acknowledge); outcome panel offers settle now; --wait refusal prints choose-file with filenames.
7 MED 163 c22: schedule-ended hold in door -> dead end 'nothing to decide'; show reason+advice+draft-correction.
8 MED 163 c16 chooser: collapse runs of owed-nothing periods into one row (as DASH-182 c2); nearest owed periods either side; reuse settle_tui Option.unavailable.
9 MED 205 script shape: validator/Player assumptions; refuse timing fields, pending+keeps, confirm with no keeps; field names change_reference/keep/keep_reason; update file header.
10 MED 205 c7: stop message should list proposed moves as scenario/dataset/index; c8 print how many owed runs and ~1 min each.
11 LOW 163 c12: refusals fill in typed values.
12 LOW 163 c15: refuse place without --supply; --help names place.
13 LOW 163 c7 + 179 c20 combine into one refusal wording.
14 reuse notes (offer_after_run, queue_table, Tier 1 door).
15 LOW 202 terminal: readers -> Q B.
QUESTIONS: A 205 where scripted confirmation lives (rec separate top-level corrections: list); B readers red in terminal queue (rec small PIPE req now); C CP Synthetic picker for a pair arrival (rec list marked, refuse on pick); D chooser also replaces settle flow's typed re-file period prompt (rec yes, amend 193).
