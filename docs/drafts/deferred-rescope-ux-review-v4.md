# delivery-dashboard-ux on deferred-rescope-v4.yaml, 2026-11-21

Pre-build advice on REQ-DASH-436, REQ-DASH-444, the page-facing parts of
REQ-PIPE-435/438/443 and REQ-GHUB-433. Read-only. Summary of findings, ranked;
the agent's suggested wording is quoted where it gave it.

1. **An undecided page can read as released [kind-neutral].** A filled green Pass
   with a small "undecided" line reads as cleared. Proposed for 444 c3: "WHERE no
   release-or-withhold decision has been recorded, THE SYSTEM SHALL say, on every
   view of the page and above its QA status, 'No release decision recorded. This
   page reports QA results only; it does not release or withhold the data.', and
   SHALL NOT show the words released, withheld, approved, cleared or pending."
   Plus: the decision in its own vocabulary, never a Pass/Warn/Fail pill or colour;
   the QA status labelled as the QA result.
2. **The decision on every view**, including a cold-loaded deep link [kind-neutral].
3. **A downloaded copy can be stale** - show the publish instant and address beside
   the decision line [kind-neutral].
4. **"Released" means recorded as released** - "Released by <actor>, <instant>:
   <reason>"; its own word table, never decisionWords()/causeNoun(), whose "held
   back" would clash [kind-neutral].
5. **Withheld is an error state** - the reason prominent, neutral words; earlier
   decisions "Replaced by the decision of <instant>", the standing one "Current".
6. **Published before QA finishes** - 'Not yet checked' (`.pill.notchecked`), out
   of the rollup with that reason, never No data (436).
7. **Derived products have no words** - 'Derived product, not counted in the
   extraction's status', and 'derived product' in the not-counted line (438).
8. **Today's tooltip becomes false** - `unagreedMarker()` says every `never` dataset
   is not counted (438).
9. **The one-off marker would repeat on ~30 rows** - say it once in the masthead
   (438 c4).
10. **Controls meaningless on a one-off** - the in-the-warehouse date, the period
    control and tier, trends, sparklines, run comparison, the supply-history list;
    key 436 c4 on the folder root, not on every dataset declaring no_calendar.
    Links carrying in-place-on/period get a notice, not a blank page.
11. **Masthead and title** - '<one-off id> · <project> · QA report'; the build
    commit shown on the page as a criterion, not only an NFR.
12. **The recipe display (extraction's own)** - progressive disclosure: id,
    project, recipe version and filter on the home view; each table's declared
    columns etc. on its own view; a word marker for default vs recipe layer.
13. **REQ-GHUB-433** - the ticket says commands are acted on at the next processing
    pass, and when that last ran, so nobody re-posts.
14. **Split 444**: a kind-neutral one-off page requirement (decision block, the
    undecided wording, header, routes) and an extraction requirement for the
    recipe display.

Questions it put for Keith: Q1 the header's PoC development controls on a one-off
page (remove, or keep); Q2 where the decision sits (above the status on every view,
or a home-view section); Q3 the undecided words ('No release decision recorded...'
or 'Awaiting a release decision').
