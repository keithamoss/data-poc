# Three small items for sign-off, 2026-10-24 morning

Drafted overnight 2026-10-23 by delivery-scoper. These are proposals and nothing
is signed. The YAML is `requirements-draft.yaml` beside this file. It validated
clean on its own and when merged into a copy of `requirements.yaml` (251
requirements, zero errors). The REQ-TEST-239 amendment below was also validated
on a merged copy. **Ids used: REQ-TEST-281, REQ-TEST-282, REQ-TEST-283.**
Item 3 amends an existing requirement, so it has no new id.

---

## 1. #88: the browser-test speed-up (REQ-TEST-281 = A, REQ-TEST-282 = B)

**Where the 56 minutes go.** These figures come from the timed full gate of
2026-10-21/22 on this sandbox. `tests/test_dashboard_e2e.py` took **2,441s of
4,730s** and ran alone on one worker, about **41 minutes of wall clock**. The
next slowest were test_checkpoints (293s), test_door_flag_parity (206s),
test_replay_inputs (135s), test_dbt_worker (120s) and test_generate_to_target
(111s). Each of those is about a tenth of the e2e module. So the gate is
roughly "one 41-minute file, with three workers finishing everything else and
then sitting idle". If the 4,730s were spread evenly over four workers it would
be about 20 minutes, plus one dashboard build per worker.

**A: REQ-TEST-281.** The e2e module would spread across every worker, with no
class split between two workers. Every other file stays pinned one-per-worker,
as `loadfile` does today. Each worker builds the dashboard once, into a place
of its own, and symlinks fonts/ and vendor/ there (the variant fixtures already
do this). The suite would no longer write the real `reports/` or the built HTML
at all. **How the loadfile race is avoided:** the race in plans/tooling.md #10
was several workers each running the session build and rewriting the *same
real files*. With a separate output per worker, no two builds share a file, so
the race cannot happen by construction. No lock and no ordering is needed. The
pyproject comment and CLAUDE.md's "--dist loadfile is load-bearing" note get
rewritten in the same change.

**B: REQ-TEST-282.** A class that opts in shares one loaded page across its
tests. Each test resets the page by a same-document navigation and by clearing
storage. A test that needs a real load says so and gets one. This covers
reloads, persistence, first render, the masthead clock, and any test that
rewrites the page in place. Console errors are still checked per test. If the
document is replaced unexpectedly, that test fails rather than the page being
reloaded quietly.

**Questions that change what gets built:**
- **Q1, the target.** I recommend an NFR: full local pytest wall clock on this
  sandbox at most **25 min with A**, and at most **20 min with A + B**. Missing
  it would be a finding for you, not a CI gate. That matches how you said
  runtime should be watched on 2026-09-18. The alternative is "measurably
  faster", which can never fail.
- **Q2, the mechanism for A.** I recommend switching to `--dist loadgroup`,
  with conftest giving every test a group: its file for every module, and its
  file plus class for e2e tests. Everything else then behaves exactly as today.
  Bare `loadgroup` would spread every other module test by test, so the groups
  are needed. The alternative is splitting the e2e file into several themed
  files and keeping loadfile. That is simpler config, but the files have to be
  balanced by hand and each one pays its own build.

**Provisional:** I haven't re-measured the build cost per worker on today's
history. The last figure is 12.9s from 2026-09-27, on a much smaller history.
The criteria require it to be measured.

## 2. The test-database tidy command (REQ-TEST-283), already built

This describes what commit 8e6f745 shipped (2026-10-22 Perth, a checkpoint with
no test claims). You asked for it on 2026-10-20. The criteria cover:
- the three options (`--older-than-hours`, default 12; `--dry-run`; `--prefix`);
- the name pattern;
- skipping connected databases;
- working out a database's age from its PG_VERSION file;
- plain DROP, keeping a database somebody connected to since the listing;
- the session-start hook.

**Decisions recorded:**
- **No FORCE.** A connection that arrives after the listing means somebody is
  using the database, so the drop should fail rather than kill their session.
  conftest's own FORCE is different: it drops its own database, and FORCE there
  was part of the 2026-10-05 incident where two sessions killed each other's
  databases.
- **Connected databases are skipped at any age.** A database left behind for
  inspection looks the same as an abandoned one.
- **Age comes from PG_VERSION.** PostgreSQL stores no creation time, and
  PG_VERSION is written once, when the database is created.

`linked_tests` and `implemented_by` are filled in but **commented out**. The
validator refuses them on a `not_started` requirement, so they could not be
left live. On the flip, uncomment them, add `signed_off` and evidence, and set
`built`. I checked a built-status copy of this requirement and all eight links
resolve.

**One question:** the five tests don't cover these criteria:
- criterion 2: MOTHMAN_TEST_DSN unset;
- criterion 7: the keep-on-late-connection path;
- criterion 8: the listing fails;
- criterion 9: the hook.

I recommend adding small tests for 2, 7 and 8 before the flip, under the
minor-fix rule, and recording 9 as verified by reading the hook. The
alternative is to flip with those four in `unmet_criteria`.

Also worth knowing: `pg_stat_file` needs a superuser or `pg_read_server_files`.
On a least-privilege role the command fails with an error, and the hook ignores
that failure without saying anything (criterion 9), so the tidy simply doesn't
run there.

## 3. Retiring the equivalence harness: REQ-TEST-239 amendment wording

`requirements.yaml` is not changed. This is the exact wording proposed.

**Status stays `built`, not `retired`.** `retired` stops the validator checking
its links while the code still exists. It also makes the validator refuse every
live requirement that depends on 239: REQ-PIPE-240, REQ-QAC-242, REQ-GEN-246,
REQ-PIPE-250 and REQ-PIPE-265. The criteria stay unchanged, because they still
describe the command truthfully.

**(a) New decision, appended:**
> "PAUSED AND RETIRED FROM USE, KEPT, NOT DELETED (Keith, 2026-10-22, answering REQ-PIPE-279 K6, plans/running-thoughts.md #122: \"The equivalence check is all about the refactor ... to have a single set of registration stuff ... this is about genuine changes, so we don't need to run the equivalence check. That was a point in time thing and can be paused and retired ... But not yet deleted.\"). It served the collection-registry series, REQ-PIPE-240 to REQ-TEST-252, which is built. From 2026-10-22 no requirement is obliged to run a capture or a compare [Q3 decides whether REQ-PIPE-250 criterion 4 is the one exception]; a change that genuinely alters behaviour is proved by its own tests and an ordinary bootstrap from empty. `mothman debug equivalence capture/compare`, qa_tools/common/equivalence.py and tests/test_equivalence.py stay; the fast tests keep running in the gate so the code does not rot unnoticed, and the full_capture self-check stays deselected. Nothing deletes any of it until Keith says so. Status stays built rather than retired, because retired would stop its links being checked while the code exists and would refuse the requirements that depend on it."

**(b) New decision, appended (the CLI UX reviewer's point):**
> "A COMPARE ACROSS A SCHEMA VERSION BUMP IS NOT A REGRESSION (CLI UX review of REQ-PIPE-279, 2026-10-23): a capture at qa schema 45 compared with one at 46 (REQ-PIPE-279) differs on S1 and S5 everywhere, because the recorded history's shape changed, not its meaning. A baseline records the harness and normaliser versions but not qa_store.SCHEMA_VERSION, so compare cannot say why. Not fixed while the harness is paused; if it is revived, recording the schema version and refusing a cross-version compare, as criterion 2 does for the harness version, is the first change."

**(c) NFR 3, old to new:** add a prefix only. The rest stays word for word.
- old: `"COST, STATED SO IT IS PLANNED FOR, ACROSS THE WHOLE SET: captures are CHAINED - ..."`
- new: `"HISTORICAL, THE SERIES IS FINISHED (2026-10-22): COST, STATED SO IT IS PLANNED FOR, ACROSS THE WHOLE SET: captures are CHAINED - ..."`

**Q3, which changes what gets built tonight.** Two requirements that are not
yet built still oblige a 239 comparison:
- **REQ-PIPE-265 criterion 9** requires before/after captures, and 265 is due
  to flip tonight after 279. 265 is a genuine behaviour change. Its "after"
  capture would also land after 279's schema 45->46 bump, so the comparison
  would differ everywhere (see (b)). As written, criterion 9 cannot be met
  usefully.
- **REQ-PIPE-250 criterion 4** says each bootstrap speed-up shall show "by
  REQ-TEST-239's compare that it changed nothing a bootstrap records". A pure
  speed-up is exactly the refactor case the harness exists for.

Recommendation:
- Release 265 criterion 9: retire the criterion, proved instead by 265's own
  tests and a bootstrap from empty, as 279 was under K6 = C.
- Keep 250 criterion 4 as the one named exception.

Both are amendments to signed requirements, so they need your yes. The other
options are to release both, or to keep both. Keeping 265 criterion 9 means
taking its before and after captures without 279 between them.

---

## Draft plans edits, for a human to apply

- **plans/running-thoughts.md #88:** part (2), "THE GATE ITSELF", and its
  2026-10-13 measurement move into REQ-TEST-281/282 once they are signed.
  Replace the block with: "**Scoped 2026-10-23 as REQ-TEST-281 (the e2e module
  across workers, per-worker build) and REQ-TEST-282 (one page per class),
  with the 2026-10-21/22 gate profile as their evidence.**" Part (1), the
  practice ask, has no requirement and stays.
- **plans/tooling.md #24:** the "Fix 3 ... is still open" paragraph becomes
  "Fix 3 is REQ-TEST-281." Keep the rest until 281 is built, then delete the
  entry whole. Its decisions (keep pytest; the masthead floor) are already
  carried in 281's decisions.
- **plans/running-thoughts.md #122:** delete it when the REQ-TEST-239
  amendment lands. Its content is the amendment's decision (a).
- **REQ-TEST-283:** there is no plans entry to delete. The tidy command was
  never written up in plans.
