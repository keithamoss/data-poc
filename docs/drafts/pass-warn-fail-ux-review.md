# Pass / Warn / Fail v1 - dashboard UX review (2026-10-31)

The review found 3 MUST, 4 SHOULD and 4 NIT items, and has 3 questions for Keith. Nothing was edited.

## MUST
1. REQ-DASH-359 c4 changes 'Re-checked <t>: became <status>' to '... now <verb>'. 'became' is Keith's own wording (template :8946, 2026-10-29), and 'now' goes stale on a history row once a later re-check changes the verdict. Use 'Re-checked <t>: became Fail - <cause>'.
2. A2: in '3 waiting for a person: 2 no supply, 1 promoted, failing' the comma makes four items. Use '1 promoted while failing' in counts, and keep 'Promoted, failing' for the standalone badge.
3. 'Re-checked failing' reads as the re-check itself failing. Replacements:
   - 'failing on a re-check after promotion';
   - 'Promoted, then <verb> on re-check';
   - 'Promoted passing, warning on re-check - awaiting acknowledgement' (A19 too).

## SHOULD
4. Lowercase label nouns in prose ('makes its dataset fail', 'keeps failing') read as events. Use 'Puts its dataset at Fail', 'each hold their dataset at Fail', 'The dataset stays at Fail'.
5. The guard (REQ-TEST-361) can pass while words leak:
   - scan textContent and attributes, including groups collapsed on load and hover-only tooltips;
   - add a re-checked supply and an 'Arrived <X>' row, the raw-value leak sites (:8893, :8948, :8975);
   - its self-test should restore a raw-value leak, not only the 'Red promoted' literal.
6. 'Not passing' alone reads as failing. Require the fail/warn split wherever it appears, aria names included.
7. xtStatusCounts (:5885) lowercases labels ('1 pass, 2 fail, 1 no rule defined'). 'Pass' as a noun is ambiguous ('processing pass'), and it mixes forms with REQ-DASH-299's '2 not checked'. See Q1.

## NIT
- 'Warn - in the warn band'.
- Scenarios panel: 'Which problems were on purpose'.
- Terminal: 'this supply, now warning'.
- REQ-DASH-299 A1: 'neither a Fail'.

## REQ-DASH-299
- B1 is consistent; check at build that its criterion 15 (9) tag is amberPromotedTag.
- Include scenario (j) in the guard's page set.
- Agrees with building this batch first.

## Questions for Keith
1. Heading and trend counts: (a) '2 fail, 1 warn', or (b) '2 failing, 1 warning'. Recommends (b), which amends A6, A7, A9, A12, A14, A15 and B1.
2. Re-check tag: 'became Fail' or 'became failing'? Recommends 'became Fail'.
3. Pair 'not passing' with its fail/warn split everywhere? Recommends yes.
