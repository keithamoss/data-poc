# Proposed CLAUDE.md row: asset_model/ (REQ-PIPE-380 c19), for Keith's approval

The step 2 builder drafted this row for CLAUDE.md's layout table, to go between the
`assets/` and `generator/` rows. CLAUDE.md edits need Keith's approval, so it was left
out when step 2 was merged (2026-11-16) and is waiting here. Question Q13.2 in morning
report 13.

| `asset_model/` | **The shared reading code (REQ-PIPE-380, built 2026-11-15).** Its charter is **configuration and the delivery tree, never the database** (QB, Keith 2026-11-14): asset time and its clock, the hierarchy, the schedule and slots, the collection registry's declaration half (`asset_model/collections.py`; loading an adapter stays in `qa_tools/collections/`), the check-file readers (`check_lifecycle`, `check_sources` - the working-tree read; the git-ref read stays in `validate_check_lifecycle`), drift arithmetic (`drift`), the declared corrections, the status order and words (`statuses`, REQ-PIPE-390), and arrival recognition over the delivery tree (`arrivals`, `delivery` - reading only; the writer stays in `qa_tools/common/delivery.py`). The pipeline, the generator, `scenarios/` and the bootstrap may import it; it imports none of them, no database driver, pandas, numpy or QA tool at module level, runs no subprocess or git and opens no connection. `mothman check`'s imports gate (REQ-TEST-384) fails a forbidden edge, an underscore-led `asset_model` name used outside it (REQ-PIPE-376) and a status ranking defined outside it (REQ-PIPE-390). A module split across it names its other half in its docstring. |
