# One-offs v6: what changed from v5, for re-signing (2026-11-21)

Keith signed v5 on 2026-11-21. Three reviews then ran against it
(`deferred-rescope-reviews-v5.md`) and Keith answered their questions the same
day. v6 folds in both. **Nothing here is applied to requirements.yaml.** Every
requirement in `deferred-rescope-v6.yaml` and every amendment in
`deferred-rescope-amendments-v6.yaml` is a proposal until Keith signs it again.

How to read the list:

- **[BEHAVIOUR]** means the change alters something he approved in v5: what the
  system does, what it refuses, what it shows, or a decision that has been reversed.
- **[CORRECTION]** means v5's intent is kept, but the wording was wrong against the
  code or contradicted another criterion.
- **PROVISIONAL** means the text rests on one of the questions at the end.

Criterion numbers are v6's unless they say v5.

Scale: 12 of the 14 requirements change in substance. REQ-PIPE-434 changes one
NFR's wording only. REQ-PIPE-439 has no change. In the amendments, REQ-PIPE-363
changes. Set A, REQ-PIPE-342 and REQ-PIPE-106 do not.

## Reversals of earlier signed decisions (both are Keith's own)

1. **Copy nothing from the kind's template** (Keith, answering CLI Q4). In v5,
   opening an extraction copied people.yaml, presentation.yaml, the default check
   layer and the publishing destination into the folder. In v6 the folder holds
   only what is generated from the recipe. presentation.yaml is now generated
   from the recipe's own names rather than copied. The default checks, people.yaml
   and the destination are read live from `one-offs/<kind>/_template/` at each
   step. This touches REQ-PIPE-440, REQ-QAC-441, REQ-PIPE-435, REQ-PIPE-443 and
   REQ-PIPE-446.
2. **No REQ-DOCS-259 hold** (Keith, architect Q-A2). In round 5, building 440 and
   running any real one-off waited on the repository going private. In v6 nothing
   waits on that. REQ-DOCS-259 comes out of 440's and 442's dependencies. The
   PRIVACY NFRs now say that a real deployment's one-off folders would need a
   private repository. The architect's alternative, a guard on `open`, is recorded
   as REJECTED.

## By requirement

### REQ-GHUB-433 (comment polling)

- [CORRECTION] c2: the listing anchor is now "updated since the creation instant
  of the newest comment already handled". v5's "since the oldest unhandled comment"
  named an instant the pass cannot know before it has listed (architect C).
- [CORRECTION] c8: a failed stage now names its cause (CLI C6).
- [BEHAVIOUR] c12: marked SETTLED (round 6). "How often passes run" now comes from
  the environment's declared configuration, never a number in code (dashboard UX).
- [BEHAVIOUR] c14, new: the pass report counts comments read, decisions raised
  and refusals, and never says "nothing to process" when it did read comments
  (CLI C6).
- New ROLLOUT COST NFR: the first reconciliation after c12 lands rewrites every
  open ticket once (architect C).
- Decisions: there is no cut-over criterion, per Keith ("No one has used GitHub").
  Both of the architect's cut-over options are recorded as REJECTED. A note says
  that one-offs cannot reach this stage.
- Open question added: where the interval is declared. This is a build detail.

### REQ-PIPE-434 (no-calendar filing)

- [CORRECTION] The MAINTAINABILITY NFR now says `is_sample` stays the routing
  question (architect G). No criterion changed.

### REQ-PIPE-435 (release decision)

- [BEHAVIOUR] c1: the command is now `mothman one-off decide --id <id>`, in the
  `mothman one-off` TUI. **PROVISIONAL (Q4)**: a could-not-load or
  could-not-check result counts as an outcome, so such a one-off can still be
  decided.
- [BEHAVIOUR] c4: deciders are read live from the kind template's people.yaml,
  not from a copy. This removes the G5 failure, where someone added as a decider
  after open failed the digest.
- [CORRECTION] c8: rests on REQ-PIPE-446's new "never GitHub" rule.
- [BEHAVIOUR] c10, new: apply_decision's order (actor, refusals, reason,
  confirm), with flag forms `--decision`, `--reason` and `--yes`. The QA summary
  and the decision in force are shown before the confirmation (CLI C2).
- [BEHAVIOUR] c11, new: if the page is already published, decide says the page
  still shows the earlier state, and names the publish command (CLI G1).

### REQ-DASH-436 (no-calendar dashboard)

- [BEHAVIOUR] c2: a one-off's declared table that never arrived shows as **Fail**,
  never as No data. v5 forbade "anything marked missing", and that conflicted
  with REQ-QAC-441 c3 (dashboard UX A).
- [BEHAVIOUR] c4: 'Not yet checked' becomes a dataset-level status of its own in
  STATUS_WORDS and status-cases.json. It is separate from the check-level
  'Not checked', in the same dashed, muted style (dashboard UX C). A new
  CORRECTNESS NFR ties it to 438's item-74 parity rule.
- [BEHAVIOUR] c6: links to removed tools now get the nearest view plus a notice,
  where they previously resolved. This covers #/plans, #/demo, #/scenarios,
  #/feedback, `?panel=` naming a removed tool, and `cmp=` (dashboard UX D).

### REQ-PIPE-438 (never counts; derived excluded)

- [CORRECTION] c2: `derived: true` is declared in **calendar.yaml only**, beside
  `no_calendar`. In v5 it was in data-asset.yaml (architect B).
- [CORRECTION] c4: the mechanism is now spelled out (architect G). The result is
  recorded as agreed, shared with every participant (share_cross_table_results)
  and counted only for counted participants. If every participant is derived, it
  is recorded in development. This is Keith's round 5 answer, made buildable.
- [CORRECTION] c5: `<kind>` means the kind's display word, never the folder name.
- [BEHAVIOUR] c7: unagreedMarker() shows for `not-yet-agreed` only, and its
  `never` wording goes. v5's c6 and c7 contradicted each other (dashboard UX B).
- [CORRECTION] c8 and c9: the refusals belong to the **schedule gate** of
  `mothman check`, not the loader (architect B). c9 also fails at a one-off's
  load, because load now runs its gates.
- NFRs: share_cross_table_results and 436's state join the parity list. A new
  NFR splits is_sample (routing) from supply_state (counted) (architect G).

### REQ-PIPE-446 (resolver and gates)

- [BEHAVIOUR] c1: a bad one-off folder name fails `mothman check` and never
  causes another folder to be selected (architect J).
- [BEHAVIOUR] c2: a kind plug-in must also supply its display words: singular,
  plural, and its own layer's name (dashboard UX E, CLI C7).
- [BEHAVIOUR] c3: **a one-off is selected by `--id`** or in the TUI, not by
  MOTHMAN_ASSET (Keith, CLI Q2). It is refused if MOTHMAN_ASSET names anything
  else (CLI G4). PROVISIONAL on Q2, which asks whether MOTHMAN_ASSET may still
  name a one-off at all.
- [CORRECTION] c7: `assets.handoff()` carries the one-offs root to a child
  process (architect J).
- [CORRECTION] c8: no collection groups are built **at import** while a one-off
  is selected (architect A).
- [BEHAVIOUR] c9: replaced by an **allowlist**. Only `mothman one-off`,
  `mothman check` and `--help` run while a one-off is selected (CLI G7,
  architect A). The v5 blocklist missed `pipeline process`.
- [CORRECTION] c10: `_has_synthetic`'s default for unknown names must not decide
  a one-off, and the not-applicable words are per kind (architect K).
- [BEHAVIOUR] c11: changed folders are digest-checked too, and untracked files
  count. Only the gitignored dbt artefacts are excluded (architect H).
- [BEHAVIOUR] c12: check's output (CLI C5):
  - counts of folders gated in full and by digest
  - the first file that differs is named in a digest failure
  - non-applicable gates go on one line
  - nothing is shown when there are no one-offs
- c15: the 363 amendment list grows to criteria 1, 2, 4, 5 and 6.
- [CORRECTION] c16, new: selected, select, why_not_selected and adopt consult
  the one-off listing, and `_layout` carries each kind's root (architect J).
- [CORRECTION] c17, new: the Asset states its kind, taken from its folder's
  location (architect M).
- [BEHAVIOUR] c18, new: **every one-off folder of every kind names a project.**
  `mothman check` fails one that does not (Keith, dashboard question (a)).
- [BEHAVIOUR] c19, new: **one-offs never use GitHub.** That means no ticket, no
  comment and no API call. A git push of configuration is allowed (Keith).
- [BEHAVIOUR] c20, new: a kind's template is gated when it changes, because
  every one-off reads it live. This was the scoper's call, following "copy
  nothing".
- The extraction kind's gate list moves `caches` to DO NOT APPLY (architect K).
- NFRs: SECURITY now mentions c19. A PRIVACY NFR was added (no 259 hold).
- Note: 446 has grown from 15 criteria to 20. See Q6.

### REQ-PIPE-442 (TUI, load, drop)

- [BEHAVIOUR] c1: **every** `mothman one-off` command runs with MOTHMAN_ASSET
  unset. In v5 only open and list did (Keith, CLI Q1 and Q2). c1 now also says
  exactly what open and list read: open reads the package, the template, and
  the assets/ and one-offs/ names. list reads the root, git, and an admin
  database listing (CLI G6, architect L).
- [BEHAVIOUR] c2, new: **bare `mothman one-off` opens its own menu**, with no
  asset needed. It browses and selects, and works on one one-off per session
  (Keith, CLI Q1).
- [BEHAVIOUR] c3: load takes `--id`. It **runs every gate its kind declares over
  its folder first**, refusing on a failure (Keith, Q-A4). It records the
  package digest in the database and files one delivery per collection
  (architect A2).
- [BEHAVIOUR] c4, new: an undeclared file is recorded as failing and is **not
  filed** (architect A2).
- [BEHAVIOUR] c5 (v5 c3): an existing database holding **the same package is
  resumed** rather than refused. Only a different package is refused (CLI G2,
  first contradiction). The "folder already existed" check stays in 440 c6. The
  "already published" refusal moved to 443 c7.
- [BEHAVIOUR] c6 to c8 (v5 c4 and c5), the drop:
  - the confirmation lists each item with its counts, and now includes the dbt
    target/, logs/ and dbt_packages (architect F)
  - **typed id only**: `--yes` never skips it, and with no terminal the drop is
    refused in NeedsATerminal's words (Keith)
  - "Deleted <item>" is printed as each item goes
  - a partial failure names what it could not remove and can be re-run (CLI C1)
- [CORRECTION] v5 c6, the unpublished-drop warning, moved to 443 c8. The
  behaviour is unchanged.
- [BEHAVIOUR] c10: list becomes a status board (CLI D2), showing stage (opened,
  committed, pushed or loaded), age and next step, with an empty-state hint.
  **PROVISIONAL (Q5)** on which stages it can see.
- [BEHAVIOUR] c12, new: each command ends by naming the next step (CLI D1).
- [BEHAVIOUR] c13, new: the environment line reads `One-off: <id> (extraction)`
  (CLI C7).
- [BEHAVIOUR] c14, new: `mothman one-off` is Tier 1 in --help's Tools panel
  (CLI C8).
- [CORRECTION] c15, new: cli/app.py's "one-off command" wording is renamed
  (CLI C7).
- Dependencies: REQ-PIPE-443 and REQ-DOCS-259 removed.
- Open question added: where load finds the package. This is a build detail.

### REQ-PIPE-443 (publishing)

- [BEHAVIOUR] c1: the destination is read live from the kind's template. The
  build is rebuild, reshape, embed and render-gate only (architect D2).
- [BEHAVIOUR] c2, new: no snapshot archive into dashboard/snapshots/, no
  fingerprint compare and no publish-environment gate (architect D2).
- [BEHAVIOUR] c3, new: publish confirms first, showing the address, the decision
  in force and the count of datasets not yet checked. `--yes` confirms, and the
  address is printed afterwards (CLI C3).
- [CORRECTION] c7, new: moved from 442. A load is refused if the one-off's page
  is already published (second contradiction).
- [CORRECTION] c8, new: moved from 442 v5 c6. This is the warning for dropping a
  one-off that was never published.
- [BEHAVIOUR] c9, new: the **stale-page warning** at drop. If a decision was
  recorded after the last publish, the drop says so and offers to publish first
  (CLI G1).
- Dependencies: REQ-PIPE-442 added. 443 now depends on 442, not the other way
  round.
- Decisions: the v5 claim "no vendor/ needed because Demo is removed" was false.
  The template loads asciinema in its head. Publishing vendor/ is REJECTED. The
  page is built without those references instead (444 c11) (architect D).

### REQ-DASH-444 (one-off page)

- [BEHAVIOUR] c1: the site name is '<id> · <project> · QA report' and is used as
  the **suffix of every view's title**, so each view keeps its own name. The kind
  is shown in its display word (dashboard UX E). Every kind has a project (Keith).
- [CORRECTION] c3: the banned words (released, withheld, approved, cleared,
  pending) apply to the undecided line only, not to the whole page.
- [CORRECTION] c4: the label is exactly 'QA result', everywhere.
- [BEHAVIOUR] c8:
  - it adds "a decision recorded after this instant appears only on a later
    publish" (dashboard UX's optional point)
  - **PROVISIONAL (Q1)**: it also shows the commit the checks ran at, beside the
    build commit
- [CORRECTION] c10: there is one layer vocabulary, 'Default check' and the
  kind's layer name ('Recipe check'), used here and in 447.
- [BEHAVIOUR] c11, new: the page has no vendor/ references (architect D).

### REQ-DASH-447 (recipe display)

- [BEHAVIOUR] c1: the recipe digest is added, and the id and project are dropped
  because the masthead already carries them.
- [CORRECTION] c2 and c3: these use 438's derived-product words and the label
  'Recipe check'.
- [CORRECTION] c4: points at 440 c2, which now generates what this view reads
  (architect M).

### REQ-PIPE-439 (recipe)

- No change. A decision notes that the recipe's required project is what meets
  446 c18 for this kind.

### REQ-PIPE-440 (generated folder)

- [BEHAVIOUR] c1: **copies nothing** from the template (Keith).
- [CORRECTION] c2: data-asset.yaml now also carries the following (architect M
  and A2):
  - an arrival_pattern per dataset
  - column types and identifier marks
  - cohort bounds
  - expected row counts
  `derived: true` moves out of data-asset.yaml.
- [CORRECTION] c3: calendar.yaml carries `derived: true` (architect B).
- [BEHAVIOUR] c4:
  - presentation.yaml is generated from the recipe
  - no people.yaml, default layer or destination is written
  - the dbt project reaches dbt_shared four levels up (architect I)
  - its packages name the deployment's local dbt_utils copy at the assets' version
- [BEHAVIOUR] c9: the folder's commit must be **pushed** to the remote branch the
  working branch tracks. In v5 committed was enough (Keith, CLI Q3). Untracked
  files count (architect H). The refusal gives filled-in git commands and the
  reason (CLI C4). **PROVISIONAL (Q1)**: the template must be committed and
  pushed too.
- [CORRECTION] c11, new: gitignore the one-offs' dbt target/, logs/ and
  dbt_packages (architect F).
- [BEHAVIOUR] c12, new: **dbt_utils comes from one local copy per deployment**,
  installed by a `mothman` setup command. Load makes no network fetch, and is
  refused if the copy is absent or the wrong version (Keith, Q-A3).
- [BEHAVIOUR] c13, new: the default layer, people.yaml and the destination are
  read live from the template (Keith).
- NFRs: PRIVACY is rewritten (no hold). PORTABILITY now covers the local copy.
  MAINTAINABILITY is reversed, and a second MAINTAINABILITY NFR covers the
  dbt_utils copy.
- Decisions: "DEFAULTS ARE COPIED" is now recorded as REJECTED, with the
  reversal. The "blocked on going private" decision is gone.

### REQ-QAC-441 (two check layers)

- [BEHAVIOUR] c1: the default layer is read live from the template and is never
  copied (Keith).
- [CORRECTION] c3: an undeclared file is recorded without being filed
  (architect A2).
- A new MAINTAINABILITY NFR: a change to the default layer reaches later loads,
  and the page's commit says which version ran.

### REQ-TEST-437 (end-to-end test)

- [BEHAVIOUR] c1: the fixture gains a declared-but-absent table and an
  undeclared file. The test now uses `--id` steps and pushes to a temporary local
  remote.
- [BEHAVIOUR] c2: it asserts that the absent table reads Fail and never No data,
  that the undeclared file is recorded and not filed, and that no vendor/
  reference appears (dashboard UX A).
- [BEHAVIOUR] c3: it adds tests that:
  - load is refused while the folder is not pushed
  - a MOTHMAN_ASSET mismatch is refused
  - a stopped load resumes
  - a drop with no terminal is refused
  - the drop removes the dbt artefacts too
- [BEHAVIOUR] c4, new: it asserts no GitHub API call is made at any step.
- NFRs: they now mention a temporary remote and the dbt_utils setup. The 259
  sentence is gone.

### Amendments: REQ-PIPE-363

- [BEHAVIOUR] c1: a one-off is named by `--id`. MOTHMAN_ASSET, if set, must name
  the same one-off. PROVISIONAL (Q2).
- [CORRECTION] c2: no collection groups are built while a one-off is selected
  (architect A and L).
- [BEHAVIOUR] c4 and c6: a kind with no folders is left out (Keith, yes to D3).
  c6's exemption widens from open and list to every `mothman one-off` command.
- [BEHAVIOUR] c5: --help's Collections line gains the one-off counts, in c4's
  and c6's words (Keith, yes to D3). This replaces the architect's "leave c5
  alone". **The exact c5 text is new and needs his yes.**
- c11, new: tests for all of the above.
- plans_drafts: sprint 29 gains the architect's build order and loses the 259
  line.

## Carry-over check

Every finding in `deferred-rescope-reviews-v5.md` is listed below. It is
marked applied (and where), or not applied (and why). Nothing is left
unaccounted for.

### delivery-dashboard-ux (13 items)

| # | Finding | Result |
|---|---|---|
| 1 | A. A missing table reads as No data | Applied: 436 c2; 437 c1, c2 |
| 2 | B. 438 c7 contradicts c6 | Applied: 438 c7 |
| 3 | C. 'Not yet checked' clashes with 'Not checked'; 436 should join the parity NFR | Applied: 436 c4 and its CORRECTNESS NFR; 438 NFR |
| 4 | D. Removed tools' routes still resolve | Applied: 436 c6 |
| 5 | E. Title loses per-view names; kind given in display words | Applied: 444 c1; 446 c2 (display words) |
| 6 | 444 c3: scope the banned words | Applied: 444 c3 |
| 7 | 444 c4: 'QA result' everywhere | Applied: 444 c4 |
| 8 | 444 c8 (optional): a later decision only on a later publish | Applied: 444 c8 |
| 9 | 438 c5 and 447 c2: kind's display words | Applied: 438 c5, 447 c2 |
| 10 | 447 c1: add the digest, drop the repeats | Applied: 447 c1 |
| 11 | 433 c12: SETTLED, "how often" from configuration | Applied: 433 c12 (and an open question on where it is declared) |
| 12 | 444 c10 and 447 c3: one layer vocabulary | Applied: 444 c10, 447 c3 |
| 13 | Question: is project part of every kind's identity? | Answered (a) by Keith. Applied: 446 c18, 444 c1 |

### delivery-cli-ux (23 items)

| # | Finding | Result |
|---|---|---|
| 14 | G1. A decision after the last publish is lost at drop | Applied: 443 c9 (the warning and the offer to publish); 435 c11 |
| 15 | G2. 442 c3 against its RELIABILITY NFR | Applied: 442 c5 (resume the same package; refuse a different one); "already published" moved to 443 c7 |
| 16 | G2's sub-question: re-loading the same package after an unpublished drop | Not settled. As drafted it is allowed, because nothing records a drop. **Q3** |
| 17 | G3. Where is the TUI | Answered by Keith (Q1). Applied: 442 c1, c2 |
| 18 | G4. Naming in later steps; MOTHMAN_ASSET mismatch | Answered by Keith (Q2). Applied: 446 c3, 442 c3, 437 c3. Whether MOTHMAN_ASSET can name a one-off at all is **Q2** |
| 19 | G5. A decider added after open fails the digest | Resolved by Keith's "copy nothing". Applied: 435 c4, 440 c4 and c13 |
| 20 | G6. `list` reads only files, yet connects | Applied: 442 c1 |
| 21 | G7. The blocklist cannot be verified | Applied: 446 c9 (allowlist) |
| 22 | C1. Drop follows reset-synthetic's flow | Applied: 442 c6 to c8. The assumed `--confirm <id>` is NOT applied, because Keith chose typed id only |
| 23 | C2. Decide uses apply_decision's order; QA summary; does could-not-check count? | Applied: 435 c10. Could-not-check counts as an outcome, PROVISIONAL, **Q4** (435 c1) |
| 24 | C3. Publish confirms and prints the address | Applied: 443 c3 |
| 25 | C4. The commit refusal gives git commands and the reason | Applied: 440 c9 |
| 26 | C5. `mothman check` must not overclaim | Applied: 446 c12, plus c11 (digest of changed folders) |
| 27 | C6. 433's pass report counts; failure causes named | Applied: 433 c8, c14 |
| 28 | C7. "One-off: <id> (extraction)"; rename app.py's wording | Applied: 442 c13, c15 |
| 29 | C8. Tier 1 in the Tools panel | Applied: 442 c14 |
| 30 | D1. Each command ends with its next step | Applied: 442 c12 |
| 31 | D2. `list` is a status board | Applied: 442 c10. The stages it can see are PROVISIONAL, **Q5** |
| 32 | D3. 363 edge cases (omit an empty kind; c5 matches) | Keith yes. Applied: amendments 363 c4, c5, c6, c11. The exact c5 text needs his yes |
| 33 | Q1 the TUI | Answered (a). See row 17 |
| 34 | Q2 naming | Answered (--id). See row 18 |
| 35 | Q3 local or pushed commit | Answered (pushed). Applied: 440 c9; 437 c1, c3 |
| 36 | Q4 people.yaml | Answered (copy nothing). See row 19 |

### delivery-architect (24 items)

| # | Finding | Result |
|---|---|---|
| 37 | A. Groups at import; asset-only wizard; one-off TUI; allowlist | Applied: 446 c8, c9; amendment 363 c2; 442 c1, c2 |
| 38 | A2. hand_filing refuses unpatterned files | Applied: 440 c2 (arrival_pattern), 442 c3 and c4, 441 c3 |
| 39 | B. `derived:` declared twice; the schedule gate owns 438 c8 and c9 | Applied: 438 c2, c8, c9; 440 c2, c3 |
| 40 | C. 433 anchor | Applied: 433 c2 |
| 41 | C. 433 first-pass cut-over criterion | NOT applied, per Keith ("No one has used GitHub"). Recorded as a decision on 433 |
| 42 | C. c12 rewrites every open ticket once | Applied: 433 ROLLOUT COST NFR |
| 43 | D. vendor/ loaded in the head | Applied: 444 c11; 443 COMPATIBILITY NFR and decision. Publishing vendor/ is REJECTED |
| 44 | D2. One-off publish does not reuse publish() whole | Applied: 443 c1, c2 |
| 45 | E. 259 hold blocks code and tests | Superseded: Keith dropped the hold entirely (Q-A2). The guard was NOT applied; recorded as REJECTED in 440 and 446 |
| 46 | F. dbt artefacts not gitignored | Applied: 440 c11; 442 c6 (drop list); 446 c11 (excluded from the digest) |
| 47 | G. 438 c4's mechanism; share_cross_table_results; is_sample/supply_state split | Applied: 438 c4, both NFRs; 434 NFR |
| 48 | H. Digest holes; load gates its folder | Applied: 446 c11; 440 c9 (untracked); 442 c3 (load gates) |
| 49 | I. dbt_shared relative paths; lock equality; dbt_utils | Applied: 440 c4, c12; 446's gate-list decision (dbt packages gate) |
| 50 | J. assets.py functions; _layout; handoff; bad name | Applied: 446 c1, c7, c16 |
| 51 | K. caches; _has_synthetic; NOT_APPLICABLE_TEXT | Applied: 446 c10 and the gate-list decision |
| 52 | L. Amend 363 c2; leave c5; 442 c1 reads assets/ names | Applied: 363 c2, 442 c1. "Leave c5" NOT applied: Keith said yes to CLI D3, which amends it |
| 53 | M. 440 c2 declares more; the Asset carries a kind | Applied: 440 c2; 446 c17; 447 c4 |
| 54 | Contradiction: 442 c3 against its RELIABILITY NFR | Applied: 442 c5 (see row 15) |
| 55 | Contradiction: 442 depends on 443 | Applied: refusal and warnings moved to 443 c7 to c9; dependency reversed |
| 56 | Build order | Applied: amendments plans_drafts, sprint 29 |
| 57 | Q-A1 cut-over | Answered: no criterion. See row 41 |
| 58 | Q-A2 259 hold | Answered: no hold. Applied throughout (see Reversal 2) |
| 59 | Q-A3 dbt_utils | Answered (local copy). Applied: 440 c12 |
| 60 | Q-A4 gate at load | Answered (yes). Applied: 442 c3; 438 c9 |

### Keith's answers (12)

Every answer is applied:

- CLI Q1: rows 17 and 33.
- CLI Q2: rows 18 and 34. The residual point is Q2 below.
- CLI Q3: row 35.
- CLI Q4 / copy nothing: Reversal 1.
- Never GitHub: 446 c19, 435 c8, 437 c4, 433 decision.
- Q-A1: row 41.
- Git push is fine: 446 c19, 440 decision.
- Q-A2: Reversal 2.
- Q-A3: row 59.
- Q-A4: row 60.
- Project: row 13.
- Drop: row 22.
- 363 edge cases: row 32.

### Totals

60 review items: 13 dashboard UX, 23 CLI UX (including G2's sub-question) and
24 architect. The architect's C is counted as three rows, and question rows are
counted alongside the findings they answer.

- **Applied: 53.** Two of these have a sub-part Keith rejected, and that sub-part
  was not applied:
  - row 22, the `--confirm <id>` flag form
  - row 52, "leave 363 c5"
- **Applied with a PROVISIONAL part: 4.** These are rows 18, 23, 31 and 32, which
  wait on Q2, Q4 and Q5, plus Keith's yes to the exact 363 c5 text.
- **Not applied, by Keith's answer: 2.** These are row 41 (the 433 cut-over
  criterion) and row 45 (the 259 guard).
- **Not settled: 1.** This is row 16, which is Q3.

53 + 4 + 2 + 1 = 60. Unaccounted: **0**.

Two further items are the scoper's own consequences of "copy nothing", and are
not review findings:

- 446 c20, gating the template.
- 444 c8 / 440 c9, the second commit and the clean template. This is PROVISIONAL
  on Q1.

## Questions for Keith

Set 1, at most 4 questions, ready to relay:

1. **Which commit does a one-off's page record?** With "copy nothing", the
   checks run at load and the page is built at publish. Both read the template
   live, and the template can change in between. So the build commit alone may
   not be the version that checked the data.
   - (a) Load records the commit it ran at, and the page shows both "checked at"
     and "built at". Load also refuses an uncommitted or unpushed template, as it
     does for the folder.
   - (b) The build commit only, accepting that a template edit between load and
     publish goes unrecorded.
   - **Recommended: (a).** It is what makes "the page's commit records which
     version ran" true. Drafted that way, marked PROVISIONAL: 444 c8, 440 c9.
2. **Can MOTHMAN_ASSET name a one-off at all, now that steps take `--id`?**
   - (a) Yes, but only as the same one-off as `--id`. The approved 363 words stay
     as they are: "Set it to one of: daily, quarterly - or one of 37 extractions
     (mothman one-off list)".
   - (b) No. MOTHMAN_ASSET is for enduring assets only, and any value set beside
     `--id` is refused. The one-off half of 363 c4, c5 and c6 is reworded to
     "... Set it to one of: daily, quarterly. For one of 37 extractions, use
     mothman one-off."
   - **Recommended: (b).** The approved words would send a person to set a
     variable that no longer selects anything by itself. The draft follows (a)
     until he answers.
3. **Can the same package be re-loaded after an unpublished drop?**
   - (a) Yes. The same package with nothing published simply runs again, which is
     how it is drafted. Nothing records that a drop happened, so this needs no
     new state.
   - (b) No. A drop is final, which needs a lasting record of the drop (a
     committed marker, which is state in the repository).
   - **Recommended: (a).**
4. **Can a one-off be decided when a table could not be loaded or checked?**
   - (a) Yes. Could-not-load and could-not-check count as outcomes. The
     confirmation names those datasets, and withholding is the expected answer.
     This is how it is drafted.
   - (b) No. Decide is not offered until every dataset has a real verdict, so a
     table that will not load blocks the decision until it is fixed or re-sent as
     a new one-off.
   - **Recommended: (a).**

Set 2:

5. **What should `mothman one-off list` show per one-off?**
   - (a) Only what it can see without opening each one-off's database: opened,
     committed, pushed, or loaded, plus age and next step. Checked, decided and
     published show on that one-off's own TUI view. This is how it is drafted.
   - (b) Everything, including checked, decided and published. That means
     opening every one-off database and reading the publishing destination for
     each row.
   - **Recommended: (a).** It stays cheap at 30-40 one-offs and keeps list's
     single administrative connection.
6. **REQ-PIPE-446 now has 20 criteria.** His rule is small, self-contained
   requirements.
   - (a) Re-sign it as one requirement now.
   - (b) Split the `mothman check` criteria (c10-c14, c20) into a requirement of
     their own before re-signing.
   - **Recommended: (a) for this re-sign.** It was signed as one requirement, and
     a split now renumbers every cross-reference in the batch. Revisit when it is
     built.
