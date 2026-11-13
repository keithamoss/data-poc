# Asset split v1 - architect review (2026-10-31)

Reviewed docs/drafts/asset-split-v1.yaml against the code in off-wt. Advisory; nothing edited.

## BLOCKING
1. REQ-PIPE-354's "a publish replaces only its own path" contradicts signed REQ-PIPE-255, a Cloudflare direct upload of the whole tree (requirements.yaml:38355-38357), and REQ-DOCS-259, which deletes gh-pages (:38940). REQ-PIPE-255, 257, REQ-GHUB-258 and REQ-DOCS-259 are missing from the amendments. Keith's question 1 below.
2. REQ-TEST-357 c5's freeze-gate fix is too narrow. Every read at the base commit loses the old file after the move:
   - validate_check_lifecycle._sources(ref) at :57-60;
   - the amber and replacement-setting freeze at validate_schedule.py:993-996;
   - PEOPLE_REL at :897;
   - _version_added_on at :838, with no --follow;
   - correction_trial.py:623 and 651-653;
   - .github/CODEOWNERS:12-14.
   Fix: one committed map from old path to new path, used by every base-commit read and self-expiring like migrate_pre_039_check_id. It must hold for any push whose base predates the move.
3. REQ-QAC-344's rename has no gate mechanism. find_disappeared_check_ids (check_lifecycle.py:942-945) excuses only REQ-QAC-039's transform, so once blocker 2 is fixed about 82 Birth Registrations ids fail as disappeared. It needs a narrow, self-expiring id transform.
4. The CLI builds every collection's command group at import (cli/app.py:50-51) by reading the hierarchy. That clashes with three criteria: REQ-PIPE-342 c6 (refuse before reading any asset configuration), c8 (refuse mothman bdm by name, which means reading the other asset) and c10 (check and --help with no asset set). REQ-PIPE-343 c3 also needs another asset's folder to name it, which c7 forbids.

## SHOULD
- Reuse what exists:
  - check_id.py:303-311 already enforces the asset segment.
  - Grow the resolver from hierarchy.DATA_ASSET_YAML and validate_schedule.Source, replacing about 12 path constants, some of them import-time defaults that 27 test files monkeypatch. It must resolve at call time.
- Shared code that names a calendar: scenario_injection.py:1315 tests == "daily", and child_protection.py:736 asks for "quarterly". Bring both into scope.
- REQ-PIPE-343 c5 (one process, one asset) conflicts with REQ-TEST-353 c3. Also:
  - replay_inputs.cache_key() needs the asset;
  - rebuild-results and build-data run per asset (test.yml:508-511);
  - data/scenario_placements.json (test.yml:414) is missing from c12;
  - checkpoints need per-asset scoping.
- More amendments are missing:
  - REQ-PIPE-248 (reports/results_* paths; short ids unique across the asset);
  - SCENARIOS.md in REQ-GEN-045, REQ-PIPE-131, REQ-DASH-139 and REQ-GEN-201;
  - REQ-TEST-117's cache path list;
  - the four hosting requirements from blocker 1.

## NIT
- 354 c4 says the landing page uses names only, but c5 needs an agency-to-asset map.
- 356 c5: much of what it asks for is already embedded (build_dashboard_data.py:247-252, 627, 942; slot_timeline.py:284). Show what is actually missing first; take the period choices from PERIOD_SEQUENCES.
- REQ-PIPE-342 is extra-large. Split it into three: the resolver and the move; gates run per asset; per-asset state directories.

## Geocoding in parallel
It edits the same contract files the move rewrites. Land geocoding's contract changes before the move commit, or hold contract/ while the move is in flight. The seed ranges and, under Q2 (a), check ids do not clash.

## Questions for Keith
1. Hosting: one Cloudflare project per asset (recommended: its own Access allow-list, matches the two-team target, per-path publishing goes away) or one combined project?
2. Is pytest exempt from "one process, one asset", with each test opening one asset's database? Recommended: exempt.
3. mothman bdm under the wrong asset: a repo-wide identifiers-only read so the refusal names the right asset (recommended), or "no such command"?
4. Which lands first, geocoding or the move? Recommended: geocoding's contract changes first.

On the draft's Q1-Q5: agrees with (a) on all five. Q2 needs blocker 3's transform. Q4's blanket rule should widen to reports/, SCENARIOS.md and snapshot paths. Q5 should also record the cache-miss figure.
