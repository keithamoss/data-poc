# delivery-cli-ux review of 164/165/166/177/178 (2026-10-14)

Advisory; recorded by the main session from the agent's report. Not folded yet.

## High
- H1: the bulk re-check is asset-wide but drafted inside a per-collection queue
  (177 c13/c19; `supply queue` needs --collection, so c20 too). Proposed: offer
  it above the collection choice beside calendar corrections, "Supplies checked
  before a check changed (N)"; each collection's queue shows its own count plus
  "(M more in other collections)". (Q1)
- H2: with more than one changed check, `supply queue` prints one aggregate line
  and a recheck command needing a --check the person cannot see. Proposed c20:
  one plain line per check (check_id, supply count, date changed, changelog
  headline), ready to paste as --check (as `supply superseded` does).
- H3: the backstop refusal (164 c23, 177 c28) gives no next step. Proposed: give
  REQ-PIPE-173's own finding and paste-ready fix (agreement_freeze Finding.fix),
  and say the re-check can be raised again once declared. Same gap in signed
  REQ-PIPE-163 c35 - flagged, not amended.
- H4: `_say_owed` lists one line per owed run, so a 400-supply hand-off prints
  400 lines. Proposed new 177 criterion: one line per bulk re-check, "k of N
  re-checks for <check> still owed (raised <date>)" - also the only progress view
  of a handed-off run.

## Medium
- M1: state duration (info only; the >10 threshold stays): "about a minute per
  supply, so roughly N minutes/hours"; progress lines in `_step`'s shape
  `[k/N] re-checking <dataset> <period> (received <day>)...` with measured
  elapsed/remaining; changed verdicts marked inline ("now amber, was green"); the
  flag panel says closing the terminal leaves the rest owed. (Q2)
- M2: exit codes for `supply recheck`: 0 all ran or all handed off; 1 refusal;
  REQ-PIPE-163's distinct code when any run left owed. (Q3)
- M3: non-TTY without --yes: show the panel and refuse with the
  `--yes --acknowledge <key>` hint (NotInteractive convention; 178 c17 has it).
- M4: withdrawal confirmations (166) name the entry withdrawn (who, when, reason)
  and its public consequence (acknowledgement: page stops showing it, stays in
  history, supply needs a person again; mark: period reads overdue/never-supplied
  again, ticket reopens), and say it can be recorded again.
- M5: `supply recheck --check X --list` prints covered supplies (to find
  --supply ids for a trial), records nothing.
- M6: a trial ends by printing the real run's command with the number it would
  cover; in the TUI, back to the bulk run's confirmation.

## Low
- L1: re-check label says what and what it costs ("run its checks again where it
  is (about a minute; recorded and published)"), ordered after gate decisions.
- L2: rejected/superseded refusals name promote / un-supersede with flag form;
  177's panel counts rejected/superseded supplies not covered.
- L3: bulk reason prompt says it's published against each of the N supplies.
- L4: hand-off wording where no pass is scheduled: "nothing runs until
  `mothman pipeline process` does".
- L5: 165 c1's un-supersede entry carries a count.

## Questions for Keith (recommended first)
1. Bulk re-check placement: A above the collection choice (asset-wide) / B inside each queue.
2. Approximate duration shown: A yes, info only / B counts only.
3. Exit code when a foreground bulk run leaves any owed: A 163's distinct code / B 0.
4. >10 warning order: A "Hand it to the processing pass" first / B "Run it here now" first.

## Keith's answers (2026-10-14 afternoon)
1. **A** - above the collection choice, beside calendar corrections; each
   collection's queue shows its own count plus "(M more in other collections)".
2. **A** - approximate duration shown, information only; the >10 threshold stays.
3. **A** - REQ-PIPE-163's distinct "decision stands, checks still owed" code.
4. **A** - "Hand it to the processing pass" listed first.
