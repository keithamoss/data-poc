Dashboard UX review round 3 (2026-10-14) - key items:
1 HIGH 182 carry-over: Keith's 2026-10-13 answers missing: recurring owed-nothing rows short generated label "Not owed - outside its agreed months (Feb, Aug)" + authored reason once on SLA tile (c2); current cycle shows owed-nothing row instead of "No deliveries in the current cycle yet." (new); c7 N-day form "by 22:00, N days before each date". Add decision.
2 HIGH 204: reader's own page (verdictLine; outstanding _from_awaiting "You can: promote / reject") tells reader to decide; new criterion: say nothing needs deciding here; settling <dataset>'s pair re-checks and re-gates (REQ-PIPE-121).
3 HIGH 204 Q1 premise wrong: held tables recorded by held_blast_radius (tool held, held_tables/held_reason), not unrunnable_code; unrunnable also has past-due and staged-awaiting-decision; overdue commonest at 30 datasets. Re-offer Q1 option A': every red not-evaluated cause rooted in another table (contested, could-not-be-loaded, past-due, staged-awaiting-decision, held), each with own wording/next step; nodata never; c10 carries held_tables.
4 MED 204 c1 placement/style: ONE notice in red notice style (.notice-exhausted + red selector), after waiting-blocker banner before exhausted-schedule banner, one line per table; bold first sentence.
5 MED 204 c5: real <a href> built as affectsLinks() builds (middle-click/copy keep date).
6 MED 204 Q3: note under each reader's pill in collection table (noSupplyNote shape); card line redPromotedMarker shape.
7 MED 204: contested dataset's banner ends "Affects <reader links>" via affectsLinks().
8 LOW 204 c7: settled-but-not-re-checked line names what makes them run again.
9 MED 163 'placed' on page has no owner: REQ-DASH-175 (unsigned, 2026-10-10) c12 forbids raw operation name = now re-file; add to 175 "a re-file with empty from-period reads 'Placed in <period>'"; present 175 with 163; 163 c12 dashboard held item names place instead of 'file it to a slot yourself' (supply_holds.RESPONSES).
10 MED 180 c13 marker order: after status pill AND red-promoted badge, before standing-in marker.
11 LOW 180 c14 quiet line position: .accepted-gaps-note slot.
12 LOW 182 c9 standing-in heading names the kind label.
13 MED 205 c12: before/after moments need lettered siblings (201 writes one date per id); before-link bounded by correction's date and history end -> extend 201 event vocabulary.
14 MED #174 fix = own DASH req (option A): scenario jump scrolls+focuses subject like drillToPeriod; (a) subject named semantically in placement; (b) expand collapsed history; (c) static accent border, no animation; (d) reload lands at top (state in history.state) - say so; (e) reword 199 c34 'brought into viewport by the jump'; build before 205/206 bootstraps.
15 MED 206 TS-55: no page shows _manifest; Expect quotes terminal/query, chip to substituted dataset page (Q).
16 NOTE process: 179/180/182 note 'not yet through scoper as own req'; 180's source lacks the joint pass; say so when presenting. 180 OQ foreshadow marker: lean no.
QUESTIONS: Set A (204): 1 causes (A all other-table causes rec / B contested+unloadable / C contested only); 2 collection level (A row note+Affects / B A+card line rec / C none); 3 reader's waiting item (A says nothing to decide rec / B leave); 4 MoSCoW (A must if TS-42/80 built / B should). Set B (chips): 1 jump survives reload? (A no rec / B yes via query); 2 TS-55 (A terminal/query expect + chip to substituted page rec / B separate period-composition view item).
