# delivery-cli-ux on #95 v2 (2026-10-20, advisory)

Summary of the reviewer's report; the full findings are carried here so they survive the session.

1. **214 c7 is too vague to prevent a terminal false green.** There are four fall-through paths:
   - (a) `filing_tui._HOW_IT_READS[PROMOTED]` is green "promoted", and `_LISTED_AS` says "in place (promoted)". Both are wrong if "Incomplete promoted" is PROMOTED plus a flag. `tests/test_cli_filing_tui.py:53` checks only that the keys exist, so it would not catch this.
   - (b) `outcome_panel`/`_recheck_panel` colour Incomplete yellow by accident, and their text prints "checked incomplete".
   - (c) `CollectionCLI.report_table`'s `_STATUS_STYLE` and caption drop incomplete from the totals.
   - (d) `has_failures()` would make a scripted `mothman cp qa` exit 0.

   Proposed replacement c7: name every surface; show the word "Incomplete" and the dataset ids under NO_COLOR and a pipe; never the green or red style, a bare "promoted", or a raw state id; the caption counts incomplete as its own figure; a NO_COLOR test per surface, failing first.
2. **Exit code, a question for Keith.**
   - A: a distinct documented non-zero code (e.g. 3) for "not fully checked". Recommended.
   - B: exit 0 and rely on the printed word.
3. **Q12 = B recommended.** Drop 210 and fold it into 214 c7: "where the supply also waits for a reason of its own, that reason is shown first and the Incomplete datasets after it". Otherwise the queue gets two wordings.
4. **One vocabulary.**
   - "Incomplete promoted" goes through `decision_words.said()`.
   - The CLI puts the state first: "promoted, Incomplete: no promoted <dataset>" and "in place, Incomplete: …".
   - Use dataset ids (cp-clients), not table names.
   - Lifecycle gate line: "promoted by the rule (<actor>), not by you - Incomplete: no promoted cp-clients for 2024-Q3; its cross-table checks run again once cp-clients has a supply for 2024-Q3 they can read."
5. **211 c8 at ~30 collections.**
   - One line per resulting status, up to eight readers and then "and <n> more" (`lifecycle_report._grouped`).
   - Readers left Incomplete get a note that nothing needs deciding on them, and when they will run again.
   - Reuse `_run_owed`'s wait line.
6. **Narrow terminals and colour.**
   - In table cells, truncate with `filing_tui._short()`. Panels and the Why column in `supply decisions` name every dataset.
   - Never the green or red style. Take the dashboard's hue at its nearest ANSI colour, not plain yellow, which already means amber.

No new command or flag is needed. 217 needs no terminal change.
