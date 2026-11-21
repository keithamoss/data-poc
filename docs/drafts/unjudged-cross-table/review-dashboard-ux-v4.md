# delivery-dashboard-ux on requirements-draft-v4 (2026-10-22)

(Returned as a report - the agent has no write tool - and saved here verbatim by the main session.)

Line numbers refer to `dashboard/qa-reporting-dashboard.template.html` in `/home/user/ed-wt`. None of Keith's decisions in `summary.md` are re-opened here.

**HCI contexts used.** The notices (204, 275), the package-waiting state and the not-due line are **error/failure states**, which get the most scrutiny. I checked them for non-punitive framing, a next step the reader can act on (no learned helplessness), and no stale promise. The grid (272) is **at-a-glance scanning plus drill-down**. I checked it for pre-attentive status, recognition over recall, progressive disclosure and consistency with the other scope sections.

**SPA/URL.** Nothing here needs new URL state. Opening a check reuses `STATE.columnName`. Hiding a column (see Q2) is derived from the data, not stored state. Every name link goes through `navHref`/`affectsLinks` and keeps `in-place-on`. This is carried correctly in 204 c5, 272 c15 and 275 c7.

## 1. Carry-over from my three v3 reviews

Almost everything landed. The carry-over tables in `summary-v4.md` are accurate, except for the gaps below.

- **"M4" was a bad citation on my part.** I meant **post-build-review #258's M4**: the relationship-then-name-then-tool row order. It is built as `crossTableRowOrder()` (5148-5161) and its comment cites "#258 M4". It is in no requirement, so nothing signed needs amending. The scoper was right to amend only 264 c2 and NFR 2.
  - **Note:** add a 272 decision saying Option C keeps `crossTableRowOrder`'s relationship-then-name sort. Its tool rank (`_TOOL_RANK`) becomes the mark order in c8 rather than a row order. Otherwise a builder may delete the function as dead.
- **Should-fix: 204 c1 says "with a modifier class (never an inline style)".** The page's existing pattern for notice variants is a **data- attribute** on `.notice-exhausted`, never a class: `data-no-supply`, `data-blocked`, `data-waiting-blocker`, `data-census` (lines 344, 7625-7651). Reword it to "a `data-` attribute on `.notice-exhausted role=status`, as `data-blocked` is". Give 275 c1 its own attribute too, so the e2e tests have a hook.
- **Should-fix: the order of 275's notice against 204's notice and the blocked/waiting-blocker banners is unspecified.** S6 can put both on one page. Put 275's notice directly before 204's (a failing verdict ranks above a could-not-run), and state it in 275 c1.
- **Should-fix: S15 (the partner superseded) is only half carried.** 275 c6 covers the package-mate being **rejected**; 210 c6 covers "rejected **or superseded**". If Notifications v3 supersedes the held-back v2, Clients v2's notice would still say "That file (received <v2>) was held back", which is now stale. Make 275 c6 "rejected or superseded", worded from the decision log, e.g. "The <dataset> received with it has been replaced by the one received <instant>; ...". 204 c2's package form has the same staleness after a rejection: its "was held back" should become "was turned down", matching c16.
- **Note:** two small v3 items were dropped:
  - the root page's "If this file is turned down, the <dataset> supply needs its own decision" (v3 shape 3);
  - the exec explanation sentence on sibling hold-backs (v3 shape 4).

  Neither is decision-bearing. Fold them in or drop them knowingly.
- **Landed correctly:** D1-D5, N1-N5, links everywhere, the card line (275 c4), the root and chain (275 c2-c3), the joint-promotion history row (272 c20), `promotionStateOn` (272 c4), `sameDelivery` (272 c18), the reject-returns-to-warehouse test (272 c19), and the 264 c1/c2/c7/NFR 2 amendments.

## 2. Blocking

- **B1. 272 c7 puts results read against a superseded or rejected partner under "Against what's staged".** c7 has only two buckets: the other table's supply was in the warehouse, or it wasn't. A supply that has left (superseded or rejected) is neither.
  - Staggered S1: Notifications v2 arrives at 9:00 and is read against Clients v1. Clients v2 arrives at 9:05 and promotes alone. Notifications v2 is held on its own red.
  - Notifications v2's page then shows its 9:00 result in **"Against what's staged", "Client Register received 1 Jul"**. Clients v1 is not staged; it has left the warehouse. That is a false label in the column whose whole job is to say which view a result belongs to.
  - c18 only protects pages of in-warehouse supplies, not waiting ones.
  - **Fix:** add a third bucket to c7. A result that read any other-table supply that is neither waiting nor in the warehouse at the date on show goes in **neither** cell. It stays in the panel's history only, under its "Read against ..." sentence. Add an e2e case for this staggered sequence.

## 3. Should-fix

- **S1. The cell's word when tools disagree.** c8 says "the result's word" with one mark per tool. If dbt passes and Soda fails, the cell must not read "Pass ✓ ✗ ✓". Say the word is the worst of its marks (`rollupStatuses`), which is the false-green direction to guard. Add a JS test.
- **S2. The marks are positional.** The key line "The marks are dbt, Soda and datacontract-cli" only decodes if every check has all three tools. A two-tool check's "✓ ✗" is ambiguous. Say a tool with no such check holds its position with a placeholder (e.g. "·"), and that the accessible name spells out each tool.
- **S3. The row should stay one `<button class="scope-check">`, with links only in the panel.**
  - c12 makes "each check's name the control", while c15 makes "every dataset name in this requirement's sentences" a link. If the cell notes carry links, the row cannot be a button. The click target then shrinks from the whole row (as in every other scope section, line 7855) to the name only.
  - That breaks consistency within the section family, and "the row's accessible name" (c12) stops being well defined.
  - **Recommend:**
    - The cell notes ("Investigations received 2 Oct") are plain text.
    - The whole row stays the existing button with its `aria-label` (as line 7906 builds today), extended with both full sentences.
    - Real `<a href>` links live in the panel sentences and in the 204/275 notices, where c15 still applies.
    - Reword c12 and c15 accordingly.
- **S4. At phone width the stacked results need their view label.**
  - The phone mock-up is not stacked yet. It squeezes three columns and clips the pill off the right edge, so c16's test is right to exist.
  - Once stacked, the column headings are gone, and "Pass ✓ ✓ ✓ / —" no longer says which view each is.
  - c16 should require each stacked result to start with "Staged:" / "In the warehouse:", and an all-dash result to be omitted rather than shown as a bare dash.
- **S5. The dashboard has no state for "checked, waiting for the rest of its delivery".**
  - 266 c15 and 276 c10-c11 give the terminal this state. With Q3 = A it can last until the next pass, overnight if a sibling's run crashed.
  - On the dashboard, the supply falls through to "Awaiting a decision", which invites a decision the terminal refuses. That is the learned-helplessness pattern, in the context weighted highest.
  - **Add a 272 (or 266) criterion:** while the package-gate item is owed, the verdict line reads "Checked, waiting for the rest of its delivery (received <instant>): <n> of <m> files checked. Nothing needs deciding yet." In the crash case, add "<dataset>'s run stopped; the next processing pass re-runs it."
  - It should be computed at build from the owed item (266 c3). Add an e2e case.

## 4. The scoper's reviewer question: the staged column on an in-warehouse page (272 OQ1)

**Recommend: hide a column that has no result in any row of the page, keep the other column's heading, and never show a column of dashes.** The scoper recommends keeping it.

- An in-warehouse page is the **common** daily view. Under c18 every staged cell there is a dash. A full column of dashes on the most-seen page is noise, and "Against what's staged" invites "is something staged? did it not run?", which is the moment of confusion Keith's bar asks us to remove.
- Showing the second column only when it holds something makes its appearance a pre-attentive signal that a staged file is in play. That serves at-a-glance scanning better than a fixed layout.
- The same rule covers the mirror case: a waiting supply whose partners are all staged has no warehouse results.
- The headings still say which view is on show, so the reader does not lose the two-views model. Rows with only one filled cell already looked like this in the mock-up Keith accepted.
- Criteria:
  - c6 gains "SHALL omit a column with no result in any row".
  - Add an e2e assertion: an in-warehouse page shows one result column, headed "Against what's in the warehouse", and no "—" cells.

This is presentation within Option C, not a change to Keith's choice. Mention it at the walk-through rather than ask.

## 5. Open questions A and B

- **A. Date label: agree with "In the warehouse on"**, keeping the `in-place-on` ids and parameter (amend 081 c23).
  - It answers the question the picker asks ("what was in the warehouse on this date?") and fits the narrow control.
  - Stable deep links beat a label-matched parameter (spa-best-practices: never break a shared link). The cost is a visible `in-place-on` in a copied URL, which is acceptable.
  - Make sure 277 c3 names both places the label appears today: the button (line 952) **and** the panel's `<label for="in-place-on-input">` (line 1058). It also appears in REQ-DASH-182's sentence (line 7239), which the amendment list already covers.
- **B. A held table's could-not-run rows: show them, but the row pills must agree with the section pill.**
  - The recommendation as drafted leaves red rows under a section pill that ignores them. That re-creates post-build-review #258's D1 defect (a section pill reading No data over red rows), fixed on 2026-10-20 by making the pill follow the rows shown.
  - Under 272 c6 a row's pill is "the result counted toward the supply on show". On Clients' page, a could-not-run counts toward nothing (269 c4), so the **row** pill is grey No data too, not red.
  - The page stays red by 115 c10, and 264 c4's banner sentence ("the tables that read this one need its supply first") explains it.
  - Add to the 264 c5 amendment: "and each such row's pill reads No data on that page". Add an e2e assertion that no red row sits under a non-red section pill.

## 6. Notes

- The section blurb ("...so it counts against both") is still true for evaluated failures. Under Q13 = B it is not true for could-not-run rows. Consider one clause in the panel for those, rather than in the blurb.
- Staggered Clients v2 at 9:00 (dropping clients) and Notifications v2 at 9:05: Clients reads red and is ticketed for five minutes, then promotes jointly. This is the accepted flicker. The joint-promotion history row (272 c20) is what explains it afterwards, so make sure 272 c20 also fires when the earlier supply was first held back by an earlier gate application, not only for a single zip.
- The S2 package form's "That is not a fault in this supply's own data" stays correct under Q13 = B, because the absent table is the referenced one. Good.

## Questions for Keith

None. B1 and S1-S5 are presentation and correctness within his decisions. Q2 above is a presentation call to mention at the walk-through.
