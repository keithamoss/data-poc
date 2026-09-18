# Dashboard

The QA reporting dashboard itself (`dashboard/`) - features, UI, and
hosting/deployment of the published site. Split out of `plans/wider.md`
2026-09-18 (see that file's own intro for the full account of the split
and `plans/running-thoughts.md` item #10 for the schema this file's own
item tags follow). Distinct from `plans/publishing-and-history.md`
(the publish PIPELINE - how a build gets from committed `qa_results/`
history to the deployed site) and `plans/qa-pipeline.md` (the check
battery itself, plus a lot of dashboard-rendering follow-ups from that
work) - this file is specifically the dashboard's own open questions and
built-history as a thing in its own right.

Status values: `todo` / `investigate` / `in-progress` / `parked` /
`done` / `superseded`. Every item also carries a Component tag - see
`plans/running-thoughts.md` item #10 for the shared taxonomy this and
`CHANGELOG.md` both use. IDs (`dashboard-N`, referenced elsewhere as
`plans/dashboard.md #N`) are permanent once assigned - never renumbered
or reused, even if an item is later retired, matching `qa_tools/
common/check_lifecycle.py`'s own `check_id` convention.

1. **[done]** **[Dashboard UI]** Wired the Child Protection collection (6
   tables, real FKs) into the QA dashboard end to end, across 4 phased
   pushes: (1) periodic snapshot generation + per-table ODCS contract,
   (2) the 7 `relationships` checks + 3 cross-table business rules
   across all three tools, a fix for 2 business rules that used to
   always fail (a real generator gap, see `plans/qa-pipeline.md` #9),
   and (3) the dashboard Collection tier itself — merged with real-tool
   wiring (originally its own separate phase) since a genuinely real
   dashboard tile needed it anyway, and `engines/*.py`'s equivalents
   don't support cross-table checks at all. **Department for Child
   Protection and Family Support → Child Protection**, 6 datasets, all
   tagged "Real pipeline data" — see README.md's "The Child Protection
   collection" section for the full account, including a real dashboard
   display bug (a `severity: warning` check's missing fail_threshold
   defaulting to 0) caught only by actually rendering it in a browser
   before calling this done. This proves the birth-registrations
   pipeline's approach generalizes rather than being a one-off, and was
   the highest-value item on `plans/wider.md`'s original list.

2. **[done]** **[Dashboard UI]** The old claude.ai Artifact copy is no
   longer a concern — decided to stop maintaining it; this repo's HTML
   is the sole source of truth going forward. **Public hosting live**:
   the repo itself is now public (Keith's call, given the data involved
   is synthetic), so GitHub Pages works on the free plan with no
   workaround needed. `.github/workflows/deploy-pages.yml` publishes
   `dashboard/qa-reporting-dashboard.html` (as `index.html`) on every
   push that touches `dashboard/` — no separate build step, since the
   file already has its data baked in at commit time. Pages source
   flipped to "GitHub Actions" in Settings, workflow run confirmed
   successful (`conclusion: success`, run `34756094074`) — **live at
   https://keithamoss.github.io/data-poc/**. This also means: as more
   datasets get wired in (item #1 above) and a scheduled re-run job
   exists (`plans/publishing-and-history.md` #1), the public dashboard
   updates itself automatically on every push — no extra work per
   dataset added.

   **Parked, not actioned**: Keith wants to move this repo back to
   private. That directly breaks free-plan GitHub Pages hosting (only
   works for public repos) — a known, deliberate trade-off to flag now
   rather than rediscover later, not something to pre-solve. Don't reach
   for a different (paid Pages tier, a separate cloud host, etc.)
   hosting solution until the private-repo move actually happens and a
   public dashboard is still wanted at that point — may turn out not to
   be needed at all.

3. **[todo, low]** **[Dashboard UI]** Explore alternative dashboard
   output types/tools — Streamlit and Power BI named specifically — as
   alternatives or complements to the current hand-rolled static HTML
   dashboard. Not yet scoped: worth comparing what each would actually
   buy (native interactivity and widgets, real data-source connectors
   instead of a baked-in JS const, embedding into BI tooling the agency
   likely already runs) against the cost of a rebuild and what it'd mean
   for the "publish as a static file, zero external dependency" property
   the current dashboard was deliberately built to have (self-hosted
   fonts, no CDN calls — see `plans/qa-pipeline.md`'s
   dashboard-readability entries). Decide replace vs. supplement before
   committing to either.

4. **[todo]** **[Dashboard UI]** Secure/authenticated hosting for the
   dashboard - Cloudflare Access or equivalent - near-term work Keith
   flagged, not scoped yet. Directly relevant to item #2 above: the
   dashboard is currently public with zero access control at all
   (`https://keithamoss.github.io/data-poc/`, GitHub Pages free-tier, no
   login of any kind), because the repo itself is public. This is a
   different, narrower question than item #2's "move the repo back to
   private" - auth-gating the *deployed site* is a real option
   regardless of whether the underlying repo is public or private, and
   item #2's own "don't pre-solve this" stance was specifically about
   not reaching for paid Pages tiers/alternate hosts before the
   repo-privacy question was live; this is Keith asking for exactly that
   now, on its own merits, not contingent on the repo going private. Not
   scoped: which mechanism (Cloudflare Access sitting in front of the
   existing GitHub Pages URL vs. moving hosting to Cloudflare Pages
   directly vs. a different provider entirely), who needs access (just
   Keith, a small reviewer group, anyone with a shared password), and
   whether the `.github/workflows/deploy-pages.yml` auto-publish-on-push
   flow needs to change at all or just gets a login wall in front of it.

5. **[done, 2026-09-16]** **[Dashboard UI]** "Time travel" - the ability
   to go back and see the entire reporting solution exactly as it was
   for any previous run, not just a single check's own history (which
   `plans/qa-pipeline.md` #45 already covers within the live dashboard's
   own rolling window). Keith's own framing up front: "think big, think
   architecturally, and consider this solution will run for years" -
   built through several explicit rounds of AskUserQuestion (intent,
   then scope, then solution architecture) before any code was written,
   per his own request.

   **Round 1 - intent.** Confirmed against the actual codebase first,
   not assumed: this project has NO persistent, accumulating run history
   today - `data/`, `reports/*.json`, and `dbt_project/target/` are all
   gitignored and fully regenerated, and both generators
   (`generate_runs.py`/`generate_cp_runs.py`) recompute a ROLLING window
   of runs anchored to `date.today()` on every regeneration, not an
   ever-growing log - so "time travel" had no historical spine to stand
   on yet, a genuinely architectural gap, not a UI feature to bolt on.
   Keith's answers: covers data AND the check definitions in effect at
   the time AND the dashboard UI itself, not just today's UI rendering
   old data; driven by audit/compliance and incident-debugging (a third
   option, general trend exploration/convenience, was explicitly parked
   for a later discussion); per-dataset vs. whole-system-at-a-point-in-
   time granularity left open pending scope.

   **Round 2 - scope.** The PoC's own rolling-window architecture was
   deliberately left as-is (not changed to accumulate real infinite
   history) - time travel just needs to work correctly for whatever
   window exists at snapshot time. Snapshot trigger: gated behind a
   manual on/off flag rather than an automatic "is this a real refresh"
   heuristic, since this PoC has no clean signal to distinguish a
   genuine scheduled run from a developer iterating on code (both use
   the same script) - Keith's own call, plus wanting the mechanism
   covered by real tests and a handful of demo snapshots committed to
   the repo so there's something to actually show. Retention: keep
   everything for now, no thinning - explicitly deferred to whichever
   future storage backend (S3/SharePoint/Cloudflare/etc, per `plans/
   wider.md` #8) eventually replaces "just commit it to the repo".

   **Round 3 - solution architecture.** Three real approaches were
   compared before picking one, not just the first idea Keith floated:
   - **A - full self-contained snapshot**: archive the exact same fully-
     built static HTML the pipeline already produces (shell + CSS + JS +
     embedded data, zero external dependencies), one complete file per
     snapshot.
   - **B - data-only + shared shell ("hybrid")**: archive just the data
     payload, tagged to a commit SHA pinning which version of the
     rendering code understands that shape; viewing means loading an old
     commit's shell against archived data.
   - **C - archive inputs, rebuild on demand**: archive the raw tool
     outputs (`results_bdm.json`/`results_cp.json`) plus a commit SHA,
     and regenerate the dashboard from them at view time.

   B and C both trade real integrity for storage savings: replaying old
   data through a DIFFERENT commit's rendering code (B) is exactly the
   kind of thing that can silently misrender history if the JS
   interpretation logic ever changes - the opposite of what an audit
   feature needs; C additionally depends on the entire toolchain
   (dbt-core, Soda Core, `uv`, Python itself) still installing and
   behaving identically years from now just to produce a view at all.
   Given the audit/incident-debugging driver from round 1, Keith
   confirmed the hard requirement this settled it: a snapshot must be
   openable with nothing but a browser, forever - which only A
   satisfies. Storage growth (A's real cost) settled as
   gzip-compression-only, no harder cap, matching round 2's "keep
   everything for now". One more scope question resolved here too:
   whether snapshots need to support cross-snapshot querying/comparison
   ("show me every snapshot where this check was red") - Keith's own
   correction sharpened this: that's the LIVE dashboard's trend-chart
   job (operating on its current rolling window), a genuinely different
   concern from an archived, opened-one-at-a-time forensic record - so
   no separate JSON payload alongside each snapshot, just the plain
   self-contained HTML. Build order: the snapshot mechanism + tests +
   demo snapshots this round; a browse/picker UI for opening past
   snapshots explicitly deferred to a later, separate round once
   snapshots exist to browse.

   **Built**, per the above:
   - `dashboard/snapshot_dashboard.py` - `take_snapshot()` (a pure,
     testable function - injectable `html_path`/`snapshots_dir`/`now`)
     gzips the current fully-embedded `dashboard/qa-reporting-
     dashboard.html` into `dashboard/snapshots/<UTC timestamp>_<git
     short sha>.html.gz` and appends an entry to a plain `manifest.json`
     alongside it (bookkeeping for this script and its own tests - NOT
     the cross-snapshot query feature ruled out above). The timestamp
     format (`%Y%m%dT%H%M%SZ`, no colons) is deliberately Windows-
     filesystem-safe, given `plans/wider.md` #8's own flag that this
     needs to run on Windows EC2s eventually. `main()` is gated on
     `SNAPSHOT_DASHBOARD=1` (unset by default) so a normal `./run_
     pipeline.sh` run stays a no-op for this step unless explicitly
     asked for.
   - The check-defining thresholds that determine each check's pass/
     fail status (`check.warn`/`check.fail`) are already embedded in the
     data payload itself, so a single frozen HTML snapshot genuinely
     captures "data AND the check definitions in effect then" for
     status-determination purposes without needing to separately embed
     raw contract/Soda/dbt YAML - nothing in the dashboard renders that
     content today anyway (see `plans/qa-pipeline.md` #43). The
     snapshot's git commit SHA is enough provenance to look up the exact
     check-definition files in git history if that's ever needed later.
   - `run_pipeline.sh` gained a 5th step calling the snapshot script
     unconditionally (the script itself no-ops without the env flag) -
     `SNAPSHOT_DASHBOARD=1 ./run_pipeline.sh` to actually archive one.
     Documented in `README.md` and `CLAUDE.md` (including flagging that
     `dashboard/snapshots/*.html.gz`, unlike every other generated
     artifact this project produces, is deliberately committed to git,
     not gitignored - the whole point is that it accumulates).
   - `tests/test_snapshot_dashboard.py` (9 tests): gzip round-trip
     byte-for-byte integrity, filename has no Windows-unsafe characters
     (regex-checked), manifest entries are correct and accumulate
     correctly across multiple snapshots, a missing dashboard HTML
     raises rather than silently producing an empty snapshot, and
     `main()` is a genuine no-op without `SNAPSHOT_DASHBOARD=1` set to
     exactly `"1"` (not `"true"`/`"yes"`/empty).
   - 3 real demo snapshots generated and committed (`dashboard/
     snapshots/`), confirmed genuinely distinct (different `md5sum`s
     after gunzip) by regenerating the whole pipeline twice more under
     `GENERATOR_ANCHOR_DATE` overrides a week and three weeks back
     before restoring the live dashboard to today's real, un-overridden
     state as the final step - so the committed `dashboard/qa-
     reporting-dashboard.html` isn't left backdated. One of the three
     verified with Playwright: gunzipped to a plain file, opened cold in
     a real browser (no dev server, no repo context) - renders with zero
     console/page errors, `card count: 6`, confirming genuine standalone
     integrity, not just "the gzip round-trips".

   Known, accepted side effect: `dashboard/snapshots/` sits inside
   `dashboard/`, so a commit adding new snapshots also matches `.github/
   workflows/deploy-pages.yml`'s `dashboard/**` trigger path - a
   harmless, no-op-content GitHub Pages redeploy alongside the real
   publish whenever a snapshot-only commit happens. Not worth narrowing
   the workflow's trigger path for - the redeploy costs nothing and
   always republishes the correct, current dashboard either way.

   `uv run pytest` (80) and `uv run ruff check .` both clean.

   **Originally deferred** (per round 3's build-order answer): any UI
   for browsing/listing/opening past snapshots from the live dashboard.

   **Picker built, same day (2026-09-16), its own short round of
   AskUserQuestion first:** confirmed it needed to work on the live
   public GitHub Pages site now (not just from a local clone), which
   forced a real design question - GitHub Pages can't be told to serve a
   `.html.gz` with `Content-Encoding: gzip`, so a plain link to one
   would just download it, not render it. Keith's own steer settled it:
   keep gzip as the git storage format (already built, tested, no
   reason to undo it for a marginal complexity saving), but decompress
   at DEPLOY time so the published site serves plain `.html` files -
   normal links, no client-side decompression JS needed at all.

   Built: `.github/workflows/deploy-pages.yml`'s "Prepare site" step now
   also gunzips every `dashboard/snapshots/*.html.gz` into `_site/
   snapshots/*.html` (plus publishing `manifest.json` alongside, for
   direct inspection) - nothing decompressed is ever committed to git,
   only produced at deploy time. The picker itself lives INSIDE the live
   dashboard (Keith's call, not a separate page) - a "🕐 Past snapshots"
   button in the header opens a panel listing every snapshot (date/time,
   commit SHA, compressed size), each linking to its decompressed page.
   Deliberately reads an embedded `SNAPSHOT_MANIFEST` const (re-embedded
   by `dashboard/snapshot_dashboard.py` every time a snapshot is taken,
   same mechanism as `embed_dashboard_data.py`'s `REAL_BIRTH_REG_DATA`/
   `REAL_CP_DATA` replacement) rather than `fetch()`-ing `manifest.json`
   at runtime - a fetch would silently fail under `file://` (CORS),
   breaking the picker for exactly the offline/local-open workflow this
   dashboard's own dev loop (and every Playwright check this session has
   run) has depended on all along. A snapshot's own archived copy still
   only ever reflects the manifest as it stood before that snapshot was
   taken - it re-embeds AFTER archiving, not before, so a snapshot never
   "knows about" itself or later snapshots.

   **Real bug found and fixed, 2026-09-17** (Keith: "I'm not seeing any
   snapshots on the live published dashboard. I thought we'd done
   that."): the picker had been genuinely broken on the LIVE published
   site since Phase 3's template/build-output split, not visible locally
   because a dev's own `dashboard/qa-reporting-dashboard.html` had
   already been manifest-embedded in place by a previous
   `take_snapshot()` call in the same working tree (a side effect that
   file itself is gitignored, never committed). Root cause: `_embed_
   snapshot_manifest()` was only ever called from `take_snapshot()` -
   `embed_dashboard_data.py` explicitly never touches `SNAPSHOT_
   MANIFEST` (its own docstring: "the separate SNAPSHOT_MANIFEST const
   dashboard/snapshot_dashboard.py owns"), and `prepare_deploy_site()`
   (what CI's "Prepare site" step actually calls) just byte-copied
   `qa-reporting-dashboard.html` straight to `_site/index.html` with no
   manifest embed at all. So every CI build - a fresh checkout, no prior
   local mutation - shipped `_site/index.html` with the template's
   untouched placeholder (`const SNAPSHOT_MANIFEST = [];`), even though
   every individual snapshot file WAS correctly landing in `_site/
   snapshots/` and openable directly by URL. The picker panel's own
   `if(!SNAPSHOT_MANIFEST.length)` branch rendered "No snapshots yet" on
   every real deploy since this split - not a design gap or a recent
   regression, just never actually verified against a real
   fresh-checkout CI build until Keith looked at the live site itself
   (earlier "verified in the live picker" claims, `plans/qa-pipeline.md`
   #53's included, were checking a locally-mutated file, not the
   deployed artifact).

   Fixed by extracting the regex-replace itself into a shared
   `_embed_snapshot_manifest_into_html(html, manifest, source_desc)`
   (both `_embed_snapshot_manifest()` - `take_snapshot()`'s local
   mutate-in-place path - and `prepare_deploy_site()` now call it), and
   a small `_read_manifest(snapshots_dir)` helper. `prepare_deploy_
   site()` now reads the real, committed `manifest.json` and embeds it
   into the `_site/index.html` copy specifically - `html_path` on disk
   stays untouched, same one-way relationship `embed_dashboard_data.py`
   already has with its own gitignored build output. Added a regression
   test (`test_prepare_deploy_site_embeds_the_real_manifest_into_index_
   html`) that reproduces the bug against a real manifest.json with an
   actual entry and fails without the fix. Verified end to end against
   this repo's real 5-entry `dashboard/snapshots/manifest.json`: ran the
   exact CI sequence locally (`embed_dashboard_data` -> `snapshot_
   dashboard --prepare-site`) and confirmed with real headless Chromium
   that the picker panel lists all 5 real snapshots (dates, commit SHAs,
   sizes) rather than "No snapshots yet." `uv run pytest` (178, up from
   177) and `uv run ruff check .` both clean.

   Verified end to end with Playwright, not just unit-tested: served a
   real simulation of the Pages deploy output (`gunzip` step run
   locally, exactly as the workflow does it) over a local HTTP server,
   opened the live dashboard, clicked "Past snapshots" (4 rows shown,
   correctly formatted), clicked "Open" on one, and confirmed the
   resulting new tab actually rendered the archived page - real title,
   real card count, zero console errors, correct decompressed URL.
   Checked both color schemes render legibly. 6 new/updated tests in
   `tests/test_snapshot_dashboard.py` (12 total) cover the manifest
   re-embedding: it matches `manifest.json` exactly, a snapshot's own
   archive excludes itself, and a missing `SNAPSHOT_MANIFEST` placeholder
   raises a clear error rather than silently doing nothing. 83 tests pass
   repo-wide; `uv run ruff check .` clean.

   **Explicitly checked, Keith's own ask**: the "first time" case - a
   brand new dashboard build with zero snapshots ever taken (`const
   SNAPSHOT_MANIFEST = [];` still its untouched placeholder value) and
   `dashboard/snapshots/` not existing on disk at all. Verified rather
   than just assumed correct: simulated both with Playwright (a real
   dashboard file with its manifest reset to `[]`) and by running the
   deploy workflow's own shell logic against a directory tree with no
   `dashboard/snapshots/` at all. Both already worked without changes -
   the picker shows a clear "No snapshots yet - run SNAPSHOT_DASHBOARD=1
   ./run_pipeline.sh..." message instead of an empty/broken panel, and
   the workflow's `if [ -d dashboard/snapshots ]` guard means a missing
   directory is a clean no-op, not an error.

   **Important clarification, same day (2026-09-16) - Keith's own
   correction, checked and confirmed before writing anything further:**
   the "rolling window" referenced throughout rounds 1-2 above is PURELY
   an artifact of how this PoC fabricates plausible-looking recent demo
   data cheaply (`generate_runs.py`/`generate_cp_runs.py` anchoring their
   date range to `date.today()` and regenerating a fresh ~10-15-run
   window each time) - it is NOT a property of a real production BDM/CP
   feed, and must never be treated as a real architectural input to how
   time travel, or anything else, *should* work. A real feed genuinely
   accumulates forever: a new file arrives, joins the record, the record
   never resets - there is no "window" in reality at all, just growing
   history.

   Checked against what was actually built: `take_snapshot()` doesn't
   know or depend on how the dashboard's underlying data was produced -
   it archives whatever `dashboard/qa-reporting-dashboard.html`
   currently contains, whether that's this PoC's narrow rolling window
   or (in a real deployment) years of genuinely accumulated history. So
   the snapshot MECHANISM needed no changes. What did need tightening
   was this very writeup: "time travel just needs to work correctly for
   whatever window exists at snapshot time" (Round 2 above) is accurate
   but risks being misread later as endorsing the rolling window as a
   legitimate design constraint, rather than naming it as the specific
   reason THIS PoC's OWN demo snapshots only ever show a shallow ~15-run
   slice - a limitation of the fake data generator, not of the feature.
   Read every "rolling window" reference above with that in mind.

   Previously parked, both pieces now **done, 2026-09-16** (Keith's own
   call, revisited together as one piece of work while scoping Phase 4
   of `plans/publishing-and-history.md` - "what's next in this phase"
   naturally led here, since Thread C/Phase 4 needs real deep,
   differently-cadenced history to demo "as of" viewing against, not the
   previous ~10-15-run rolling windows):
   - **Child Protection widened from weekly to quarterly**, and deepened
     at the same time from 10 runs (~10 weeks) to **16 quarterly runs
     spanning 4 years** (Keith's own follow-up call, after an initial "3
     years" was corrected mid-build) - `generator/generate_cp_runs.py`'s
     `RUN_PLAN` is now built by `_build_run_plan()` (a seeded
     ratio-preserving severity assignment: ~70% clean/~25% amber/1 fixed
     red, first run always clean - the Evidently reference run - last
     always red, unchanged from the original design intent) rather than
     hand-listed, and `START_DATE`/each run's date now come from
     `_quarter_start()`/`_add_quarters()` (real calendar-quarter
     boundaries - Jan/Apr/Jul/Oct 1 - not week arithmetic).
   - **Birth Registrations deepened from 10 scheduled deliveries (15
     manifest entries incl. resupply attempts) to 60 (85 entries)**,
     spanning ~2 months instead of ~10 days - `generator/
     generate_runs.py`'s `RUN_PLAN` is now built the same way
     (`_build_run_plan()`, seeded, ~60/20/20 clean/amber/red, first and
     last always clean).
   - Verified for real: both real orchestrators re-run end to end
     against the deepened data (6884 BDM / 2832 CP check results, across
     85/16 runs respectively - up from 1214 BDM / 1770 CP across 15/10
     runs before this), qa_results/ history fully nuked and regenerated
     (no way to backfill run_by-less old runs onto a completely
     different date/severity plan anyway - same "happy to throw it
     away" call as the run_by field's own rollout).
     `build_results_from_history.py`'s history-only rebuild produced
     byte-identical counts to the live orchestrator run for both
     datasets. Both CI gates (check-lifecycle, dashboard render) pass
     clean. Full pytest (149 tests) + ruff clean.
   - Real timing, for future reference: BDM's 85-run real-tool
     orchestration took several minutes (4-core parallelism, ~9.6s/run
     baseline from `plans/performance.md` scaled up); CP's 16-run
     orchestration stayed fast (a few minutes) since run count barely
     grew from the original 10. See `plans/performance.md` if this
     matters again at a future depth increase.

   **Local/offline viewing gap found and fixed, same day (2026-09-16),
   right after the picker build:** Keith's own catch - "a developer...
   does a QA run... opens the latest file that was generated... they
   can't actually go back and select any of the previous runs, can't
   they? Because they're all just gzipped up in the repository."
   Correct: the picker's links (`snapshots/<name>.html`) only ever
   resolved on the published GitHub Pages site, where
   `deploy-pages.yml` decompresses every `.html.gz` at deploy time -
   nothing decompressed anything locally, so `dashboard/snapshots/` on
   a real clone only ever held the gzipped originals, and opening the
   dashboard via `file://` would 404 on every "Open" link. (Briefly
   thought this was already handled - it wasn't; confirmed by reading
   `take_snapshot()`, which only ever called `gzip.open()`, never wrote
   a plain `.html` copy anywhere.)

   Fixed with `sync_local_snapshots()` in `dashboard/snapshot_
   dashboard.py`: decompresses any `*.html.gz` in `dashboard/snapshots/`
   lacking a local `.html` sibling, writing to the exact same relative
   path the picker's existing links already use - so neither the
   dashboard's JS nor its link markup needed any change, locally or on
   Pages. Called from two places: unconditionally at the top of
   `main()` (so a plain `./run_pipeline.sh`, no `SNAPSHOT_DASHBOARD`
   flag needed, backfills local copies of whatever snapshots already
   exist - the literal fresh-clone scenario Keith described), and again
   at the end of `take_snapshot()` itself (so a snapshot just taken is
   immediately locally openable too). Idempotent - a `.gz` with an
   existing `.html` sibling is left untouched.

   Scoped via two quick questions rather than assumed: whether
   decompression should be automatic vs. a separate explicit step
   (Keith's read - correctly - was that automatic is how it already
   should work, confirming the fix's direction), and whether the local
   `.html` copies should be committed or gitignored-and-regenerated -
   "Gitignored, regenerated from .gz," so `dashboard/snapshots/*.html`
   was added to `.gitignore`; the `.gz` files stay the only thing
   actually committed, same single-source-of-truth pattern as `data/`/
   `reports/` elsewhere in this repo.

   Verified two ways: `uv run python3 -c "from dashboard import
   snapshot_dashboard; snapshot_dashboard.sync_local_snapshots()"`
   against the real repo's 4 existing committed `.gz` snapshots -
   correctly backfilled 4 local `.html` copies, confirmed gitignored
   (`git status` shows nothing new). Then real Playwright against the
   live dashboard opened via `file://`: clicked "🕐 Past snapshots",
   clicked "Open" on a row, confirmed the resulting popup actually
   rendered the archived page from its local `file://.../snapshots/
   <name>.html` path - real title, real content, zero console errors. 6
   new tests in `tests/test_snapshot_dashboard.py` (18 total, up from
   12): `sync_local_snapshots()`'s decompress/skip-existing/missing-dir/
   idempotent behaviour, `take_snapshot()` leaving a local copy behind
   too, and `main()` syncing even with no `SNAPSHOT_DASHBOARD` flag set
   (the existing `main()` tests were also updated to mock out `sync_
   local_snapshots()`, since it otherwise touches the real repo's
   `dashboard/snapshots/` directory as a side effect of running the test
   suite). 89 tests pass repo-wide; `uv run ruff check .` clean.

   **Unified with the deploy pipeline's decompression, same day
   (2026-09-16), right after the fix above:** Keith flagged the local
   sync and the GitHub Pages deploy step (`.github/workflows/deploy-
   pages.yml`'s "Prepare site") were two separate implementations of the
   same "unzip a snapshot" logic - the deploy step was a bash `gunzip`
   loop, `sync_local_snapshots()` was Python's `gzip` module - that
   could quietly drift apart. His ask: make local sync literally
   exercise the same code path deploy uses, so running it locally is a
   real dry run of what CI will do, not just something that resembles
   it. First separately confirmed the local-sync feature itself was fine
   to keep as-is (his worry it might undercut "push to the shared site"
   incentives didn't hold up: `sync_local_snapshots()` only ever
   decompresses `.gz` files already on disk - either pulled from git,
   already shared, or just taken by that same local run - so it can't
   let anyone see history they didn't already have access to).

   Extracted `_decompress_snapshot(gz_path, dest_path)` as the one place
   a `.gz` becomes a plain `.html`, called by both `sync_local_
   snapshots()` (unchanged behaviour) and a new `prepare_deploy_
   site(site_dir, ...)`, which now builds the entire `_site/` tree
   deploy uploads (index.html + decompressed snapshots + manifest.json
   copy) - replacing the old bash loop entirely. Wired up via a
   `--prepare-site <dir>` flag on `snapshot_dashboard.py`'s own `main()`
   rather than a separate script, so there's no risk of the workflow
   importing a stale copy. `deploy-pages.yml`'s "Prepare site" step is
   now: `uv run --no-project python3 -m dashboard.snapshot_dashboard
   --prepare-site _site`.

   Verified for real, not just unit-tested: ran `python3 -m dashboard.
   snapshot_dashboard --prepare-site <dir>` from the repo root -
   correctly produced `index.html` plus all 4 real committed snapshots
   decompressed under `snapshots/`, confirming namespace-package `-m`
   resolution works without `dashboard/` needing an `__init__.py`. 6 new
   tests (24 total in `tests/test_snapshot_dashboard.py`, 95 repo-wide):
   `prepare_deploy_site()`'s copy/decompress/manifest/no-snapshots-dir
   behaviour, an explicit byte-for-byte-identical check between the
   local and deploy decompression paths, and the `--prepare-site` CLI
   flag itself (including its usage-error case). `uv run ruff check .`
   clean.

   **Correction, same day (2026-09-16) - Keith's own catch:** this entry
   originally said the deploy step should invoke a bare `python3` since
   the script only needs stdlib, "so no uv/dependency install needed" -
   wrong. Keith asked directly: are we sure GitHub Pages deployment
   can't use uv? It can - nothing stops it, and this repo's own
   convention (CLAUDE.md: "Always through `uv run`, not a bare
   `python3`... nothing should depend on... a system Python that happens
   to have the right packages") applies in CI too, not just to local dev
   machines. "Needs no third-party packages" and "so skip uv" had been
   quietly conflated. The actual constraint was narrower: a plain `uv
   run` in this repo's directory would sync the FULL project dependency
   set from `pyproject.toml` (dbt-core, Soda Core, datacontract-cli,
   Evidently, pandas...) before running anything - genuinely unwanted
   for a step that only needs stdlib and would slow every deploy. `uv
   run --no-project` resolves that: it skips the project-context
   dependency sync entirely while still running through uv's own pinned
   Python rather than trusting whatever `python3` happens to be
   preinstalled on the runner. Verified locally (`uv run --no-project
   python3 -m dashboard.snapshot_dashboard --prepare-site <dir>`,
   ~0.15s, no dependency sync triggered) before changing the workflow.
   `.github/workflows/deploy-pages.yml` now adds an `astral-sh/setup-uv`
   step before "Prepare site" and runs the script through `uv run
   --no-project`.

   **That deploy actually failed in CI, same day - real bug, caught
   because Keith checked the run rather than assuming green:**
   `astral-sh/setup-uv@v10` errored with "Unable to resolve action...
   unable to find version `v10`" - a second wrong guess about that
   action, not just the first one. Confirmed via its actual tags list
   (`astral-sh/setup-uv` doesn't publish floating major-version tags at
   all - only exact ones like `v10.1.0` - unlike `actions/checkout`/
   `actions/deploy-pages` etc., which do) and its own README, which
   recommends pinning to the full commit SHA rather than any tag, a real
   supply-chain-security convention for third-party actions. Re-pinned
   to `astral-sh/setup-uv@bec219d24cd3e171d82865faccec3312
   0bb574f4 # v10.1.0`. Lesson worth naming plainly: the earlier "v10"
   guess was asserted without checking the actual tags list first time
   round either - looked up a release page, not the specific ref format
   this workflow needed. Verified this time by listing the repo's real
   tags before writing the pin, not by re-guessing a plausible-looking
   one.

   **Relationship to the newer "as of" viewing idea, same day
   (2026-09-16)** - see `plans/publishing-and-history.md` Thread C.
   Different mechanism, both staying in the design: this item's
   snapshots are whole-page freezes taken at explicit past moments; "as
   of" viewing queries real accumulated per-run history (once `plans/
   publishing-and-history.md` Thread B exists) for an arbitrary date
   someone picks. How the two UI entry points should relate to each
   other is flagged as not yet designed there.
