# Suite timings

Moved here verbatim from CLAUDE.md on 2026-11-18 (Keith's approval of the
move and of CLAUDE.md's pointer, the same day). The running log of
full-suite runtimes, newest last; add a real number whenever a full local
run happens anyway.

- **The full local `uv run pytest` run took a real, measured ~193s
(346 tests) as of 2026-09-18 evening - up from the ~2min/302-test
figure recorded earlier the same day - not because the suite grew
meaningfully, but because of a real, since-fixed performance bug.**
`qa_tools/common/changelog.py`'s `_committed_at_by_run_timestamp()`
(walked by `dashboard/embed_dashboard_data.py`'s `embed()`, which
several tests exercise - `test_embed_dashboard_data.py`,
`test_dashboard_e2e.py`'s `TestBuiltDashboardRenders`/`TestTicketBadge`)
used to spawn one `git show <sha>` subprocess PER commit that ever
touched a dataset's `qa_results/` subtree, diffing that commit's
ENTIRE changed tree - real cost that scales with both commit COUNT
and DIFF SIZE, and both grew a lot the same day this was found
(several qa_results/ regeneration commits touching 80-900+ files
each, mostly full-file rewrites). Measured before the fix: ~13s for
Birth Registrations' own 12 commits alone, 225MB/5.3M lines of raw
diff output. Fixed two ways: one `git log -p` call instead of N
`git show` calls, AND narrowing the pathspec to `dataset_stats.json`
files specifically - the only file this function (or its caller)
ever actually reads, so excluding the real, verbose dbt.json/soda.json
tool output (the bulk of the diff volume) is what did most of the
work - measured after: 0.7s, 1.7MB/56K lines, a ~13x reduction on
that one call; full local suite back down to ~122s/346 tests after
the fix, in line with the earlier ~2min baseline. The STANDING
lesson: this class of "walk real git history" logic scales with real
repo growth, not just row/run counts - a real `pytest --durations=30`
profile is the way to find where new growth actually went, the same
diagnostic step that caught it here, not a guess.
**Standing practice, 2026-09-18 evening (Keith's own explicit ask):
keep an eye on this going forward, informally - report back if
runtime has grown noticeably since the last time it was checked, the
same way this entry itself does. Deliberately NOT a CI-enforced gate
(unlike `pytest-cov`'s real, measured coverage threshold) - Keith's
own words: "no need to put it into CI or anything." A rough running
log of full-suite `uv run pytest` timings, newest last, so "has this
grown" has a real number to compare against rather than a vague
feeling: ~2m43s/163 tests (pre-2026-09-18) -> ~2min/302 tests
(2026-09-18 morning, after `test_generate_runs.py`'s own fixture
consolidation) -> ~193s/346 tests (2026-09-18 evening, the git-walk
bug above) -> ~122s/346 tests (2026-09-18 evening, after that fix)
-> ~59s/411 tests (2026-09-18 night, `pytest-xdist` `-n 4` - see
`plans/running-thoughts.md` #12's own real fix/verification account;
plain serial `uv run pytest` is still ~122s-equivalent at today's test
count, `-n auto` is the fast path, not the new default - see that
item for why) -> **~220s/649 tests serial (2026-09-19 evening,
item 74's fix)**. The suite has grown ~58% in test count since the
last entry, and that's most of the runtime growth - nothing pointed
at a new hot spot this time. Two real, environment-only gotchas hit
on a genuinely fresh sandbox during that run, both worth knowing
before reading a red result as a code problem: the documented
one-time `uv run dbt deps ...` step had never been run here (8 real
dbt test failures until it was), and `PLAYWRIGHT_CHROMIUM_PATH=/opt/
pw-browsers/chromium` was needed for the e2e module (16 errors until
it was set). Neither is a code fault; both are one-line fixes.
-> **~83s/653 tests (2026-09-19 evening, parallel now the default)**.
The race that used to make `-n auto` unreliable for a full-suite pass
is fixed (`plans/tooling.md` #10 - two of them, actually: the embed
tests reading real `reports/` build artifacts mid-rewrite, and the
e2e build fixture running once per worker), so this number is a
like-for-like replacement of the 220s serial one above, not an
optimistic best case. The real CI coverage command
(`--cov=qa_tools --cov=pipeline --cov=generator --cov=dashboard`)
passes at 94.76%, comfortably over the 92% floor.
-> **~81s/673 tests (2026-09-19 late evening)**. Flat against the
previous entry despite 20 more tests - no new hot spot.
-> **~83s/680 tests (2026-09-20 morning)**. Flat again.
-> **~84s/695 tests (2026-09-20 midday)**. Flat again, 15 more tests.
-> **~85s/719 tests (2026-09-20 afternoon, REQ-QAC-023)**. Flat again.
-> **~86s/754 tests (2026-09-20 afternoon, REQ-DOCS-029/REQ-TEST-030)**.
Flat again, 35 more tests.
-> **~85s/772 tests (2026-09-20 evening, REQ-QAC-024's authoring-rules
doc and failure_indicates gate)**. Flat again. Worth knowing for the next fresh sandbox: the run
before this one reported 20 failures across `test_run_dbt_*`,
`test_cli_*` and `test_orchestrate_single_run.py`, all from the
documented missing `dbt deps` step rather than any code fault - more
than the "8 real tests fail" this file records elsewhere, and the
symptom is a `FileNotFoundError` on a dbt `manifest.json`, which does
not name `dbt_utils` anywhere. Check each asset's `assets/<asset>/dbt/dbt_packages/`
exists before reading that shape of failure as a regression.
-> **~87s/792 tests (2026-09-20 evening, the requirements sign-off
gate)**. Flat again, 20 more tests.
-> **~97s/809 tests (2026-09-20 evening, REQ-DASH-026)**. Up ~10s on
17 more tests - the new ones are all real-browser e2e, which cost far
more per test than the rest of the suite. No new hot spot.
-> **~91s/812 tests (2026-09-20 evening, the detail-panel authored-text
fix)**. Flat.
-> **~96s/833 tests (2026-09-20 night, REQ-GHUB-027)**. Flat, 21 more
tests.
-> **~98s/839 tests (2026-09-20 night, REQ-DASH-033)**. Flat.
-> **~154s/1048 tests (2026-09-23, REQ-GEN-043)**. Up ~56s on 209
more tests, and that is where the growth went - no new hot spot.
Worth knowing for the next fresh sandbox: the test count has grown
~25% in three days across the supply-model sprints.
-> **~149s/1114 tests (2026-09-23, REQ-PIPE-050)**. Flat against the
previous entry despite 66 more tests.
-> **~149s/1154 tests (2026-09-23, REQ-PIPE-051/052)**. Flat again,
40 more tests.
-> **~153s/1185 tests (2026-09-23, REQ-PIPE-053)**. Flat again, 31
more tests - eleven of them real-browser e2e, which usually shows.
JS suite 183 tests in ~13s.
-> **~148s/1217 tests (2026-09-23, REQ-QAC-047)**. Flat again, 32
more tests. JS suite 218 tests in ~15s.
-> **~132s/1236 tests (2026-09-25, the post-build fix pass)**. Flat
against the previous entry, 19 more tests. JS suite 227 tests in
~17s. One real, environment-dependent failure surfaced in the run
before this one and is fixed rather than waived - a test computing
"today" from `date.today()` while the page computes it on the asset
clock, so it went red only in the eight-hour window where UTC and
Perth are on different calendar days (plans/post-build-review.md
#59). Worth knowing for anyone reading a red e2e result late in a
UTC day: check whether the assertion depends on an ambient date
before reading it as a regression.
-> **~174s/1407 tests (2026-09-25, REQ-DASH-071)**. Up ~42s on 171
more tests, and that is where the growth went - no new hot spot. Most
of the new ones are real-browser e2e, which costs far more per test
than the rest of the suite: one class alone walks all seven dataset
pages in a real Chromium, and another deliberately waits fifteen
seconds to prove the masthead does NOT tick. JS suite 294 tests in
~19s.

-> **~171s/1438 tests (2026-09-25, REQ-PIPE-068)**. Flat against the
entry above on 31 more tests. Worth knowing for the next fresh
sandbox: the per-run DuckDB files under `data/duckdb_runs/` and
`data/cp_duckdb_runs/` are gone, replaced by one supply database
and one database per TEST WORKER - so a stale pair of those
directories in an old checkout is dead weight rather than state
anything reads. (That one supply database was `data/supply.duckdb`
when this entry was written; REQ-PIPE-087 moved it to PostgreSQL
two days later, so the shape of the fix is what this entry is
about, not the engine.)


-> **~180s/1734 tests (2026-09-25, REQ-DASH-070)**. Up ~9s on 296
more tests since the entry above, and that is where the growth went -
no new hot spot. JS suite 315 tests in ~18s.

-> **~200s/1830 tests (2026-09-26, the overnight sprint batch)**. Up
~20s on 96 more tests since the entry above; most of the new ones are
real-browser e2e, which costs far more per test than the rest. JS
suite 335 tests in ~22s. One REAL, TIME-DEPENDENT test defect
surfaced in the run before this one and is fixed rather than waived:
an e2e assertion drove the DEFAULT as-of date - today on the asset
clock - against Birth Registrations, which is daily, so the moment
the Perth date rolled past the newest generated run its row correctly
went quiet and the assertion had nothing to find. Nothing about the
page was wrong. Worth knowing before reading that shape as a
regression: anything asserting on a DAILY dataset's current-cycle
state has a shelf life of one day unless it takes the as-of date from
the data rather than from the clock.

-> **~215s/1872 tests (2026-09-26, REQ-QAC-037's display half)**.
Up ~15s on 42 more tests since the entry above - no new hot spot. JS
suite 346 tests in ~24s.

-> **~220s/1905 tests (2026-09-26, REQ-PIPE-038's re-key)**. Flat
against the entry above on 33 more tests. JS suite 346 tests in ~24s.

-> **~294s/2007 tests (2026-09-27, after the e2e sleep/fixture fixes)**.
Up ~74s on 102 more tests since the entry above - and the growth is
real rather than a regression: this day added the PostgreSQL switch's
own tests plus four new modules. Two things worth knowing. The
`mothman check` total is ~5m53s, of which pytest is 294s. And the e2e
module itself went 249.66s -> 184.84s (plans/tooling.md #24), which
moved the SUITE only 325s -> 294s: `--dist loadfile` pins that file to
one worker while the rest run beside it, so it only costs the suite
what it costs beyond the slowest of the others. The module figure is
the flattering one; this log should carry the suite figure.
Measured on a real PostgreSQL, which every run from here needs.

-> **~211s/2049 tests (2026-09-27, after the Soda dotenv fix)**. Down
~83s on 42 more tests, and the drop is the point rather than the
count: the suite had been FLAKY - three full runs failed eight, then
four, then one different tests, all passing in isolation - because
Soda Core reloads this repo's `.env` over the process environment on
its first scan, moving that xdist worker off its own database and
onto the real `supply` one for every test after it
(`plans/tooling.md` #26). Part of the time went with it: two tests
were staging the whole real forty-two-arrival delivery tree on every
run, eighty seconds, because they passed a `raw_dir` the loader had
stopped reading. Full `mothman check` 268s; JS suite 351 tests.

-> **~244s/2155 tests (2026-09-27, REQ-PIPE-089's last phase)**. Up
~33s on 106 more tests since the entry above, and the count moved for a
reason worth knowing: ten test modules were rewritten against the
database rather than the committed tree, and several gained tests
they could not have had before - "it writes no files at all" is only
assertable once that is true. No new hot spot. Three runs are in this
figure's history rather than one: 55 failed / 22 errors, then 13
failed, then green, which is what a wide refactor's sweep looks like.

-> **~257s/2189 tests (2026-09-28, REQ-DASH-054)**. Up ~46s on 140
more tests since the entry above; nothing pointed at a new hot spot.
Full `mothman check` 300s, of which pytest is 257s and `npm test`
~41s (377 tests).

-> **~294s/2501 tests (2026-09-28 night, promotion wired into the
pipeline)**. Up ~37s on 312 more tests since the entry above, and
that is where the growth went - nothing pointed at a new hot spot.
Full `mothman check` 370s, of which pytest is 294s and `npm test`
~40s (392 tests). Worth knowing before reading a slow BOOTSTRAP as a
regression on the same day: the pipeline now runs one arrival at a
time rather than in parallel, which is a separate ~2.4x and has its
own note under `mothman pipeline run` above.

-> **~300s/2724 tests (2026-09-29, REQ-QAC-108's wiring)**. Up ~43s
on 535 more tests since the entry above, which is where the growth
went - no new hot spot, and the count moved because two days of
sprint work landed without this log being updated. Full `mothman
check` 6m25s, of which pytest is 300s and `npm test` ~40s (440
tests). Measured against a `supply` database rebuilt from empty.

-> **~311s/2887 tests (2026-09-29, REQ-GHUB-082's TUI adapter)**. Up
~11s on 163 more tests since the entry above - no new hot spot. Full
`mothman check` 6m42s, of which pytest is 311s and `npm test` ~52s
(440 tests). NOT A CLEAN RUN, and said so rather than rounded off:
one test failed, a new one of this session's own asserting on the
NEWEST decision-log entry for a dataset when a promotion also writes
an `inherit-refused` for each later period it cannot carry into. It
passed alone and failed beside another module on the same worker.
Fixed, and the figure above is still the honest cost of the tree that
produced it.

A FIGURE FOR CI, WHICH IS NOT THE SAME NUMBER AND IS WORTH KNOWING
BEFORE WAITING ON ONE. On `ubuntu-latest`, 2026-09-29: setup ~1m,
**`mothman pipeline bootstrap` 8m55s**, the dashboard build 8s, and
the suite itself **9m18s** - about 19 minutes end to end, against
6m42s locally. The bootstrap is the difference and it is structural
rather than slow hardware: since REQ-PIPE-089 the suite's source is a
database, so a runner has to generate the whole QA history before it
can run at all, and since 2026-09-28 it does that one arrival at a
time.

**SINCE REQ-TEST-375 (2026-11-02) THE TWO HALVES BELOW RUN ONLY WHEN
`test.yml` IS STARTED BY HAND**; a push runs `critical.yml`, whose job
fails on any skip itself, and a `critical` test needing a deployment or
a browser fails collection. The halves and the skip-count rule still
hold for a hand-started run.

**CI RUNS IN TWO HALVES SINCE 2026-09-29** (plans/tooling.md #27), so
the figure above is the OLD one and what to budget now is different.
Measured on run 36573107713:

| Job | Wall clock |
|---|---|
| `test` - the 2,622 tests needing no deployment | **6m 40s** |
| `test-deployment` - bootstrap 8m32 + 277 tests 4m49 | **14m 34s** |
| `js-tests` | 43s |
| `coverage` - combines both halves, enforces `fail_under` | 19s |
| **run total** (the two halves are parallel) | **15m 03s** |

**STALE BY 2026-10-05 - re-measure before quoting any of this.** CI
run 37315439654 (commit 4305585): the bootstrap step took **23m29s**
(it was 8m32s here), the deployment half's tests 7m35s, the other
half 17m13s, the whole run **33 minutes**. This sandbox took 25m56s
for the same bootstrap, so the two machines are about level - the
"GitHub is much faster" impression was this table going out of date
as the history grew (one arrival at a time, 150 arrivals, knock-on
re-runs, a census per run, file checks). See
REQ-PIPE-188 to 192, which took a bootstrap from empty to 4m24s here
on 2026-10-12. Re-measured 2026-10-13 after REQ-GEN-195 and REQ-GEN-200
(TS-67's re-files and their re-checks): 4m42s from empty. Re-measured
2026-10-13 after REQ-GEN-196 (an 80-day Birth Registrations history,
seven two-file pairs settled by script): **6m29s** from empty, Birth
Registrations 330s and Child Protection 261s in parallel; **6m43s** the
same night at 85 days with the pairs spaced out (post-build-review #172).
Re-measured 2026-10-13 night after REQ-GEN-199 (TS-75 to TS-79): **7m00s**
from empty, Birth Registrations 342s and Child Protection 270s in parallel.
Re-measured 2026-10-15 for REQ-GEN-207 criterion 9, Child Protection grown
ten years at its old end (Keith's call, 55 quarters where there were 15):
**8m08s before** (Birth Registrations 393s, Child Protection 317s) and
**31m52s after** (Birth Registrations 550s, Child Protection 1792s) - Child
Protection now dominates, at roughly 32s a quarter. Budget a cache-miss CI
bootstrap accordingly; profiling it is the obvious next speed-up.
Re-measured 2026-10-31 for REQ-PIPE-336 criterion 4, from empty and
`--sequential`, before and after Linkage Products (a third Department of
Health collection whose checks read Child Protection and Emergency
Department): **1439s before** (Birth Registrations 512s, the quarterly
stream 1291s) and **3509s after** (Birth Registrations 814s, the quarterly
stream 2507s). The linkage collection adds 55 arrival runs and 6 knock-on
re-checks, and 14 more Child Protection and ED runs caused by a decision.

So a RED IN THE COMMON CASE reports in about SEVEN minutes rather
than nineteen - 2,622 of 2,898 tests are in the fast half. The whole
run is 15 minutes, not the ~10 an earlier estimate in #27 claimed;
that estimate was wrong because the two halves are not comparable in
cost, and the correction is recorded there rather than quietly fixed.

**WHICH HALF A TEST IS IN IS DERIVED, NOT LISTED.** `tests/conftest.py`
marks anything requesting the `deployment_history` fixture
`needs_deployment`; modules reading a generated artefact carry the
mark themselves. A test in the WRONG half does not fail loudly - it
SKIPS, which is a green that proves nothing. **So the number to watch
on the fast half is the SKIP COUNT, and it should be zero.**

**AND THE WAY TO DEBUG A CI-ONLY FAILURE IS TO REPRODUCE ITS
CONDITION, which is now three things rather than one.** The fast half
has an EMPTY deployment database, no `data/` and no `reports/`.
Recreating all three locally - a scratch database, both trees moved
aside - reproduced ten CI-only failures exactly, in under three
minutes rather than a fifteen-minute round trip:

```
sudo -u postgres psql -c 'CREATE DATABASE ci_probe OWNER "user"'
mv data /tmp/data_aside; mv reports /tmp/reports_aside
MOTHMAN_SUPPLY_DSN=postgresql://user:password@localhost:5432/ci_probe \
  uv run pytest -m "not needs_deployment" -q -rs
```

Restore both trees afterwards, and mind that a test run RECREATES
`data/`, so a bare `mv /tmp/data_aside data` nests it.

-> **~1444s/5621 tests (2026-10-16 evening, REQ-QAC-242)**. Full
`mothman check` 27 minutes, of which pytest is 24m04s and `npm test`
2m11s (830 tests). The ~5-minute gate figure further up is long stale;
this sandbox's suite now runs against a database bootstrapped from the
grown Child Protection history (REQ-GEN-207). Not profiled yet.

-> **~988s/5619 tests (2026-10-18, REQ-PIPE-243)**. Down ~456s on the
entry above with two fewer tests: the shared orchestrator runs a
bootstrap 675s faster (after-242 1920s against after-243 1245s), and
the suite's own bootstrapped fixtures feel the same gain. Full
`mothman check` 18m31s, of which pytest 16m28s and `npm test` 88s
(830 tests). One failure in that run, a defect of the change itself
caught by the gate before the push (a config slip read as `<unicode
string>`); fixed and the affected modules re-run rather than the whole
suite, under commit rule C.

-> **REQ-TEST-281 (2026-10-25): the browser-test module across every
worker.** `tests/test_dashboard_e2e.py` alone, default worker count:
**1283s -> 717s / 659s / 667s** (three runs, 322 -> 326 tests, zero
skips), each of four workers paying its own ~65-105s build. Its floor is
now one class, `TestEveryScenarioJumpLands` (two tests, ~400-500s on
one worker, scheduled late because xdist hands out bigger groups first),
so it misses the 10-minute module target by about a minute. The
last full gate before it was 24m12s, pytest 1309.8s. **With it built
(7d7c828, after #271/#272's fixes): pytest 1215s/6244 tests, full
`mothman check` 22m37s** - about 95s off the suite, less than the
module's own ~620s saving because the rest of the suite now shares the
workers with it rather than running beside one busy worker.

Whenever a full local run happens anyway (not a reason to run one
that selective testing above would otherwise skip), note the real
number here.

-> **2026-11-18, the profile (Keith: profile first).** From the full chunked gate
on dc1881c2 (both halves, run in 20 module chunks with 4 workers each plus the
browser module; read from each chunk's junit file, so a module's time includes
its fixtures' setup). 1 failed (an order-dependent test_period_opening case,
post-build-review entry pending), coverage 95%. The slowest modules:

```
dc1881c2 chunked gate, 2026-11-18: 8452 tests, summed test time 164.7 min (wall 22:31-23:48 UTC, 77 min, 20 chunks + browser chunk)
  47.8 min    439 tests  tests/test_dashboard_e2e.py
  10.0 min     46 tests  tests/test_package_gate.py
   8.4 min     50 tests  tests/test_cli_package_gate.py
   7.3 min     66 tests  tests/test_door_flag_parity.py
   3.3 min     14 tests  tests/test_strict_cross_table.py
   3.1 min     12 tests  tests/test_settlement_rechecks_readers.py
   3.0 min      7 tests  tests/test_queue_beneath.py
   2.8 min     34 tests  tests/test_replay_inputs.py
   2.8 min     31 tests  tests/test_embed_dashboard_data.py
   2.7 min     23 tests  tests/test_config_pin.py
   2.7 min      2 tests  tests/test_one_asset_beside_another.py
   2.6 min     33 tests  tests/test_cli_cp.py
   2.4 min     13 tests  tests/test_root_cause_shouts.py
   2.3 min     24 tests  tests/test_last_planted_scenarios.py
   2.2 min     56 tests  tests/test_choose_file.py
```

The browser module is over a quarter of all test time; the three gate-support
modules (package gate, its CLI, door-flag parity) another sixth.

-> **2026-11-18, the speed batch's after measurement (REQ-PIPE-403 criteria 2, 4, 5
and 7).** Each asset from empty on this sandbox, `mothman env reset-synthetic` then
`mothman pipeline bootstrap`, quarterly then daily, at commit 1127e1a4, under py-spy
(raw, 20 Hz, subprocesses and idle threads). The before is 2026-11-16's (quarterly
2437s, daily 357s).

```
quarterly  1413s  OVER the 720s budget by 693s   load 2.42 -> 1.82
  generation 1m 38s (of it target trials 33s), the one stream (Child Protection,
  Emergency Department, Linkage Products) 21m, confirmations 17s
daily       375s  within budget                  load 1.82 -> 1.62
  generation 58s (of it target trials 45s), Birth Registrations 5m 16s,
  confirmations under 1s
```

Where the quarterly stream's 1275s go, from the stream worker's main thread: 825s
waiting on a run's four tools, which run side by side; the gate 152s; filing 112s;
recording results 63s; staging 59s. Inside the four tools the dbt worker is the long
pole (815 thread-seconds against datacontract-cli's 248; Soda and Evidently are
negligible), and inside the dbt worker parsing the manifest takes 433s of the 695s it
is busy - once per run. Also running: a session building in another worktree ran
short test files, single gates, one `mothman check --no-pytest` and a few synthetic
generations into a scratch folder; no other bootstrap and no full gate.

