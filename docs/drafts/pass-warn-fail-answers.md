# Pass / Warn / Fail - Keith's answers

## 2026-10-31
- Q1, phrase form: (a) Pass / Warn / Fail as labels, passing / warning / failing in prose, e.g. 'went in failing, failing since 3 May'. 'Red promoted' becomes 'Promoted, failing', and 'Amber promoted' becomes 'Promoted, warning'. REJECTED (b), the exact words in prose, and (c), a straight swap ('Fail promoted').
- Q2, depth: (a) displayed words only, now: page, terminal and GitHub Issue text. Identifiers stay (CSS classes, stored values, amber_setting, --dirty amber|red). PARKED for later, not rejected: (b) renaming the configuration people type and (c) renaming stored values. Logged as running-thoughts #133.
- Q3, the amber setting's displayed name: (a) 'Warn setting'; the config key amber_setting is unchanged.
- Q4, history and docs: (a) history stays as written (CHANGELOG past entries, decisions, plans). Built criteria quoting displayed words are amended. Reader-facing docs (README, docs/) and the scenario text the dashboard shows are reworded.
- Q5, capitals: (a) title case - 'Pass', 'Warn', 'Fail' - matching the grid and every other pill.

## Review round (Keith, 2026-10-31)
- UX Q1, counts: (b) the -ing form - '2 failing, 1 warning', 'latest 2 failing and 1 warning of 15' - matching '2 not checked' and the prose rule, and avoiding '1 pass' (ambiguous with 'processing pass'). This amends A6, A7, A9, A12, A14, A15 and B1. REJECTED (a), the label form '2 fail, 1 warn'.
- UX Q2, re-check tag: (a) 'Re-checked <t>: became Fail - <cause>', keeping Keith's verb 'became' and using the label for a status reached. REJECTED 'became failing' and the draft's 'now failing', which goes stale.
- UX Q3, 'not passing': (a) always paired with its split, e.g. '2 of 6 datasets not passing (1 failing, 1 warning)', aria names included.
- Architect Q-A: (a) 'false pass' on the dashboard (scenario headings and titles, e.g. 'the false-pass family'); history keeps 'false green'.
- Architect Q-B: (a) old recorded reasons are shown as recorded, never translated as the page renders them.
- v2 Q1, the promoted-then-re-checked heading (Keith, 2026-10-31): (a) 'Promoted, then failing on re-check' (and the same shape for warning). It replaces the 2026-10-29 wordings 'Promoted green, re-checked amber', '1 re-checked red after promotion' and the heading 'Promoted, then re-checked <verdict>' in the seven built criteria A28-A34. REJECTED (b) 'Promoted, then re-checked: became Fail'.
- Sign-off (Keith, 2026-10-31): "approve all but significant changes I've not already discussed and approved/decided on". All four requirements and amendments A1-A39 and B1 SIGNED; the five word-for-word wordings (A5, A7, A14, A18, A24) apply answers already given. The two undiscussed changes were put separately: BUILD ORDER (a) this batch, then geocoding, then the asset split; TICKET DUPLICATE (a) accept and note. Written into requirements.yaml as REQ-DASH-359, REQ-TEST-360, REQ-TEST-361 and REQ-DOCS-362, status not_started, signed 2026-10-31. The amendments are applied to their target criteria by REQ-DOCS-362 at build, as drafted.
- #289 D8d/D8e (Keith, 2026-11-01): fixed in this batch's build, D8e test-first (a not-evaluated point must not draw as a 0% dip).
