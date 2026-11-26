# Signed but unbuilt: triage of 68 deferred criteria, 2026-11-21

From `delivery-architect`, read-only, at Keith's request ("2, 3 and 4 once the
current work is done; send any to the architect and scoper now"). Groups: 2 =
deferred to delivery sprints 11/12; 3 = unowned; 4 = waiting on another
requirement. REQ-PIPE-250, REQ-GEN-044, REQ-DASH-394, REQ-DOCS-259 and REQ-PIPE-257
c1-5/c14 were handled separately and are not counted here.

A claim to verify, not a verdict (post-build-review's standing rule). Spot-checked
by the main session the same day: eras.yaml exists for both assets;
`landed_on_accepted` has no caller outside its own test; `arrival_history.last_promoted()`
is a stub only a test calls; `scenarios/register.py:35` reads `plans/supply-model.md`.

Totals: A (buildable as signed) 19 · B (superseded or already met) 24 ·
C (needs re-scoping, sent to delivery-scoper) 4 · D (Keith's or external) 21.

**Headline: group 2 is almost entirely stale.** Every requirement sprints 11 and 12
own is now built (REQ-PIPE-074/075/076/078/079/080/081/086, REQ-TEST-150,
REQ-PIPE-151/152, REQ-QAC-108, REQ-GHUB-082; REQ-PIPE-077 retired). What the two
sprints still need is one thing, REQ-GHUB-082 c1. Clearing the stale entries
should also flip sprints 9 and 10 from `blocked`.

## Class B - retire or mark met (needs Keith: these touch requirements.yaml's claims)

| criterion | proposal | citation |
|---|---|---|
| DASH-070 c1 (held by assignment rule) | mark met | `outstanding.py:350` `_from_holds` |
| DASH-070 c1 (closed unfilled slot) | mark met | `outstanding.py:447` `_from_unfilled_periods` |
| DASH-070 c9 (uncertain-filing qualifier) | retire, and c1's "under ambiguity" clause | REQ-PIPE-065 c1/c2 retired by REQ-PIPE-131 |
| PIPE-034 c3 (hold most recently promoted) | mark met; delete the stub `arrival_history.last_promoted()` | `decision_log.promoted_supply()` via `promotion_state.py:361` |
| QAC-037 c3 | mark met | restated as REQ-PIPE-079 c2; `orchestrate.py:554` |
| QAC-037 c4, c5 | mark met | REQ-PIPE-079 c6/c7; `qa_store.py:273-287` |
| GEN-045 c1, c2 (vacuous) | mark met | scenarios injected, `driver.py:352` |
| DASH-046 c2 (click path) | mark met | `test_dashboard_e2e.py:4289` |
| PIPE-062 c1 (assignment before checks) | mark met | `orchestrate.py:537-551` |
| PIPE-064 c3 (held not promoted) | mark met | `promotion.py:1060`; `verdict.py:157` |
| PIPE-066 c9 | mark met | REQ-PIPE-080 c1 |
| PIPE-066 c10, c11 | mark met | REQ-PIPE-080 c2/c3 |
| PIPE-066 c12 | mark met | REQ-PIPE-080 c4 |
| PIPE-067 c4 | mark met | REQ-PIPE-080 c5 |
| PIPE-098 (all vacuous) | mark met | REQ-GEN-251 evidence: 2015-Q4 inherits |
| TEST-116 c6 | retire | superseded by REQ-PIPE-403 and REQ-PIPE-431/432 |
| PIPE-202 c4 | mark met, once Keith confirms | #95 built: REQ-PIPE-270 c4, REQ-DASH-204 c1 |
| PIPE-233 c3 (per-collection time) | retire or amend | one stream per calendar since REQ-PIPE-262 |
| PIPE-233 c5 | mark met | REQ-PIPE-336 evidence, CI run 41144293386 |
| DASH-277 c5 | mark met after the 80-column CLI check | all seven blockers built |
| PIPE-341 c3 | mark met | `linkage_products.py:19-20` |
| GEN-370 c1 | mark met | `assets/*/synthetic/eras.yaml` |
| PIPE-352 c5 | retire | duplicates REQ-PIPE-250 (REQ-PIPE-403 SR7) |
| PIPE-382 c7 | mark met | `embed_dashboard_data.py:446,775` |

## Class A - buildable as signed, in batches

1. **Register and evidence pass** (no product code): DASH-139 c3 (31 of 66 scenarios
   name no requirement); DOCS-358 c4's #131 half (carry-over check, then delete);
   TEST-375 c4-7 (read a critical.yml log); TEST-260 c7/c8 (`ci-usage --days 7`).
2. **Generator claim refusals**: GEN-205 c10 and GEN-251 c4 together (placements
   and participation gaps checked against scenario claims), then GEN-334 c12 (the
   scheduling rule moves into the shared driver).
3. **Anchor rolling**: GEN-406 c5 (L), then c1 quarterly and c8; GEN-405 c10;
   GEN-408 c8. After batch 2 - both edit the driver and providers.
4. **#95 dashboard follow-ups**: DASH-204 c16 (a reader's queue item says nothing
   needs deciding - share the terminal's wording), DASH-272 c17 and c24, DASH-291
   c16; QAC-333 c3 alongside.
5. **Quiet measurement**: PIPE-432 c6, last, nothing else running.

## Class D - Keith's or external

- **One hand-started test.yml, a cache miss then a hit (~225 billable minutes)**
  clears PIPE-296 c8, TEST-353 c1/2/5, c6 and c7, PIPE-403 c3 and TEST-375 c8, and
  gives REQ-PIPE-250 c5 its figure. One go/no-go.
- Keith's earlier calls still open: PIPE-098 c4 (open-a-period command, "leave
  until needed"); GEN-232 c4 (accept the 2013 start or re-size); DASH-275 open
  question 1; DASH-292 c9 (left unmet on purpose, 2026-10-25 - amend or keep);
  PIPE-322 c2 (#286 item 7); QAC-330 c3 (conflict with REQ-GEN-335); PIPE-336 c7
  (amend to the refusal, or schedule cross-stream checkpoints); TEST-402 c1/c9/c10
  (where a profile may use deployment databases); DOCS-358 c3 (waits on 259).
- Needs another platform: PIPE-129 NFR7 (event-trigger guard on e.g. RDS);
  PIPE-343 c4/c7 (a Docker host for the dev container).

### Outcome, 2026-11-23

Keith answered all nine of the earlier calls on 2026-11-23, and PIPE-233 c3 and
DASH-277 c5, left over from Class B, were settled the same day:

- PIPE-098 c4: amended - a period opens at the first filing or by time once its
  due instant has passed (REQ-PIPE-323); the open-a-period command is withdrawn. Met.
- GEN-232 c4: amended (option B) - the history starts at the oldest quarter a
  planted scenario claims, 2013-Q1; the count recorded (54 owed quarters to 2026-Q3). Met.
- DASH-275: Q1 = A confirmed - a failed re-check is its own root, on the page as in
  the tickets; criteria 2, 3 and 9 reworded, the open question closed. Met.
- DASH-292 c9: built - an archived snapshot carries its six fonts inline and keeps its
  typeface opened alone; the demo player is left out, and the criterion amended to
  allow only its failure. Met.
- PIPE-322 c2: built as signed - a rise on a frozen version is one numbered refusal,
  the correction to paste as its step 2. Met.
- QAC-330 c3: amended - the contract carries one id column more than any linked
  dataset declares. Met.
- PIPE-336 c7: amended to the refusal Keith chose on 2026-10-30. Met.
- TEST-402: c1 amended; c9 and c10 recorded from the full chunked gate of 7daa6ad1
  (9039 passed, 1h56m30s). c10 met; c9 met but for the generation count, which that
  gate did not take. The 30-minute target is not met.
- DOCS-358 c3: CLAUDE.md's hosting bullet replaced with Keith's approved wording. Met.
- PIPE-233 c3: amended - each bootstrap stream's time, naming its collections, in
  docs/suite-timings.md. Met.
- DASH-277 c5: built - the kept report lays its lines out within 80 columns and caps
  the re-checked checks at eight. Met.

## Class C - sent to delivery-scoper the same day

PIPE-065 c8 (is a 'landed on accepted' warning still wanted beside the queue and
the gate?); GHUB-082 c1 (what carries a GitHub comment to the handler now Actions
cannot reach the database - running-thoughts #53); PIPE-352 c6 (re-baseline or
retire the pre-split comparison); PIPE-379 c5 (what a no-period supply means: the
project-extraction shape, running-thoughts #141).

## Surprises

1. Dead product code only tests call: `arrival_history.last_promoted()` and all of
   `qa_tools/common/landed_on_accepted.py`.
2. REQ-TEST-260 c1 (keep test.yml's push trigger) is contradicted by REQ-TEST-375,
   yet still counted met.
3. Product code reads a plans file: `scenarios/register.py:35` parses
   `plans/supply-model.md`, which is meant to be deleted thread by thread.
4. `unowned` deferrals go stale silently - the sprints gate warns only on named
   blockers. Several carried false premises ("#95 not yet scoped", "zero injected
   scenarios", "eras.yaml does not exist").
5. Harder at ~30 collections: QAC-333's hand-written check pairs; GEN-334/205/251's
   refusals; PIPE-336 c7 (a quarterly stream can never resume once a collection
   reads another); DASH-204 c16's queue must group readers by cause.
6. REQ-GEN-251 c3's wording ("the quarter after the gap") disagrees with its own
   decision (the gap quarter inherits).
