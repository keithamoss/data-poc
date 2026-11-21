# delivery-dashboard-ux on #95 v2 (2026-10-20, advisory)

Line numbers refer to dashboard/qa-reporting-dashboard.template.html in /home/user/ed-wt.

1. **The pill is one word, "Incomplete"** (relay question A).
   - Every pill is `pill(status)`, an icon plus one STATUS_LABEL word (line 4368).
   - `redPromotedBadge` (~6897) already rejected a sentence inside a pill: at 598px it became a short pill with an `.rp-why` sentence beneath (#121 D1/D2).
   - Table names go in the 204 page notice, and in the collection table as an `.incomplete-note` under the pill in `noSupplyNote()`'s shape (line 6108): "No promoted <name>[, <name>] for <period>". The names are links built by `affectsLinks()`. More than three: the first two, then "... and <n> more".
   - 204 c17 restores that row note.
   - Use dataset display names, never table ids.
   - The alternative, if the long pill is kept: "Incomplete: no promoted <first> +<n>".
2. **Colour** (relay question B).
   - Taken: green, amber, red, grey dashed (nodata), grey border (exhausted), slate `--accent`, and violet `--change` (line 55, "definition changed").
   - Proposed: a new blue, `--incomplete:#1D5FB4 / --incomplete-soft:#E3EDFA` (light) and `#7DB0F0 / #16263B` (dark), in all three theme blocks (lines 40, 60, 71).
   - A solid border and a half-filled icon (the gradient technique `.pill.ev-warn` uses).
   - The shape matters under tritan vision. Contrast (~5.3:1 light, ~6.8:1 dark) still needs a real check.
3. **216 c5 must name the counts that would drop Incomplete:**
   - `datasetsNotGreenLine` (3851): n = red + amber; add "z incomplete".
   - `groupWeeklySeries` (3879) drops anything that is not red, amber or green: keep it, as a third series.
   - The exec legend (6449-51) gets an Incomplete key.
   - The exec explanation (6444) gets a sentence on Incomplete.
   - Both cross-table blurbs (5019, 5197) gain "a check that could not run counts against the tables it could read, never the one it could not".
   - c9 tests the weekly trend.
4. **REQ-DASH-204 fixes:**
   - c15 contradicts c7: add "except criterion 7's line".
   - c1 cites an Incomplete notice style that does not exist. Use `.notice-exhausted` role=status with an `incomplete` modifier class, not an inline style.
   - c1 covers only the normal render branch. Name the blocked branch's position (after `blockedBanner`) or exclude it.
   - Side sighting for road-testing: `awaitingCorrectionLine` (6785, 6793) uses `var(--amber, #b7791f)`, and `--amber` is not a token.
5. **Wording.**
   - c2: "**No promoted <dataset> for <period>.** <n> of this dataset's checks need it, so they could not run. That is not a fault in this dataset's own data, and nothing needs doing here: they run again by themselves once there is a <period> <dataset> supply to check them against."
   - c2 has a singular form, uses the page's period formatter, and drops "nothing needs doing here" where the dataset has a red of its own.
   - c7: "**<dataset>'s <period> supply was promoted on <date>.** <n> of this dataset's checks have not been re-run against it yet; they run by themselves, and this line goes once they have."
6. **What the cause's page says** (the c16 table):
   - Contested, held, could not be loaded and closed already have notices. Awaiting a decision has a verdict line.
   - Overdue-still-open has NO notice (only a muted note, line 7748). Not yet due has no notice either, and the page often shows last period's green.
   - Not yet due: no top notice. Instead, a sentence at the head of the cross-table section, generalising `heldCrossTableSentence` (5098): "<n> of these checks could not run: the tables that read this one need its <period> supply first. Affects <links>." Use the same sentence for every cause.
   - Overdue: relay question C.
7. **Readers' rows at scale.**
   - Bounded per collection. Keep the rows, add the section sentence, and make the section pill Incomplete only if a row is.
   - If a hub page is still too long, the post-build critic measures it; a disclosure would change signed 264 behaviour.
8. **Where "Incomplete promoted" shows** (relay question D).
   - Recommended: supply-history rows, the decision log, and the card line.
   - The header and the collection row only when a supply TURNED Incomplete after promotion (case 10).
   - Reuse `.red-promoted`/`.rp-why`, ideally renamed `.promoted-label`.
9. **Navigation.**
   - No new URL state.
   - Links are real `<a href>` elements via `navHref`. A modified click opens a new tab, and the copied address keeps `in-place-on`. Add this to 204 c13 and 216 c9.
   - Optional idea: carry arrival context (REQ-DASH-198's `arrivalBanner`).

Watch item: at every quarter start, cards will read Incomplete for weeks. The post-build critic checks the exec tier doesn't read as alarming.

**Relay questions:**
- A, the pill text. Recommended: one word.
- B, the colour. Recommended: new blue with a half icon. Otherwise violet, or ink only.
- C, a late table's own page. Recommended: reword the muted note to "overdue since <date>", plus "Affects <readers>". Otherwise a new Overdue notice, or leave it.
- D, where "Incomplete promoted" shows. Recommended: history, log and card, and the header only when it turned. Otherwise everywhere red promoted shows.
