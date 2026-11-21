# One-offs v5: post-sign-off reviews, 2026-11-21

Keith signed v5 the same day, before every reviewer had seen it. He then asked
for the reviews to run and for any changes to come back to him. Everything here
is a PROPOSAL to re-sign. Nothing has been applied to requirements.yaml.

## delivery-dashboard-ux (v5 delta)

- **A. A table that never arrived reads as grey "No data".**
  - REQ-DASH-436 c2 forbids "anything marked missing", while REQ-QAC-441 c3 makes a declared table that did not arrive a failing result.
  - Proposal: 436 c2 shows such a dataset as Fail, never No data.
  - REQ-TEST-437 c1/c2 gain a fixture with a table that is declared but absent.
- **B. REQ-PIPE-438 c7 contradicts c6.**
  - Once c6 removes the marker from `never` rows, no tooltip is left there.
  - Proposal: show `unagreedMarker()` only for `not-yet-agreed`, and remove its `never` wording.
- **C. 'Not yet checked' clashes with the check-level `notchecked`, which reads "Not checked".**
  - Proposal: a separate dataset-level status in STATUS_WORDS and status-cases.json, in the dashed, muted style, kept out of the rollup.
  - Add 436 to REQ-PIPE-438's item-74 parity NFR.
- **D. Routes for the removed tools still resolve.**
  - Affected: #/plans, #/demo, #/scenarios, #/feedback, ?panel= and cmp=.
  - Proposal: 436 c6 drops each of them, with a notice, and opens the nearest view.
- **E. The title loses per-view names.**
  - Proposal: 444 c1 makes the site name '<id> · <project> · QA report', used as each view's title suffix. The kind is shown in display words, never as the folder name.
- **Smaller points:**
  - 444 c3: scope the banned words to the decision line.
  - 444 c4: label it 'QA result' everywhere.
  - 444 c8 (optional): a later decision appears only on a later publish.
  - 438 c5 and 447 c2: use the kind's display words.
  - 447 c1: add the recipe digest, and drop the repeated id and project.
  - 433 c12: mark it SETTLED, and take "how often" from declared configuration.
  - 444 c10 and 447 c3: one vocabulary for layers.
- **Question:** is "project" part of every kind's identity?
  - (a) Yes. Every kind declares one, and REQ-PIPE-446 checks it.
  - (b) No. It is shown only where the kind declares one.

## delivery-cli-ux (`mothman one-off`)

- **G1. A decision recorded after the last publish is lost at drop without a warning.**
  - Proposal: 442 c6 warns when the page is stale, and offers to publish first.
  - 435 gains an "the page still shows the earlier state" line.
- **G2. 442 c3 contradicts the RELIABILITY NFR, so a crashed load can never resume.**
  - Proposal: refuse only a different package's digest or an already published page; resume the same package.
  - Architect question: re-loading the same package after an unpublished drop.
- **G3. No criterion says where the TUI is.** Bare `mothman` refuses without an asset, and claim_for_connection is per process. (Q1)
- **G4. No rule for naming the one-off in later steps, or for a MOTHMAN_ASSET that names something else.** (Q2) Whichever way it goes, refuse when MOTHMAN_ASSET disagrees.
- **G5. A decider added after open fails the digest check**, because people.yaml is a generated copy. (Q4)
- **G6. 442 c1 says `list` reads only files, but c8 has it connect.** Open also reads the package and assets/. Reworded c1 proposed.
- **G7. 446 c9's blocklist cannot be verified.** Proposal: an allowlist (`one-off`, `check`, `--help`).
- **C1. Drop follows reset-synthetic's flow.**
  - Counts per item, then the typed id, then "Deleted …".
  - A partial failure can be re-run.
  - No flag stands in for the typed id, and drop is refused with no terminal. (Assumed; Keith may want `--confirm <id>`.)
- **C2. Decide reuses `apply_decision`'s order:** actor, refusals, reason, confirm, with flag forms.
  - Show the QA summary and the decision in force before confirming.
  - Say whether could-not-load or could-not-check counts as an outcome.
- **C3. Publish confirms** (address, decision, unchecked datasets, `--yes`) and prints the address.
- **C4. The commit-before-load refusal gives the git commands and the reason.** (Q3)
- **C5. `mothman check` must not overclaim.**
  - The result line counts folders gated in full and folders gated by digest.
  - Nothing is shown when there are no one-offs.
  - A digest failure is named.
  - Non-applicable gates go on one line rather than a row each.
- **C6. The 433 pass report counts comments, decisions and refusals,** never "nothing to process"; failure causes are named.
- **C7. Small wording:**
  - The environment line reads "One-off: <id> (extraction)".
  - Rename app.py's "one-off command" wording.
- **C8.** Tier 1, in the Tools panel.
- **D1. Each command ends with its next step.**
- **D2. `list` becomes the status board:** stage, age and next step, plus an empty-state hint.
- **D3. Two REQ-PIPE-363 edge cases, which need Keith's yes:**
  - Omit a kind that has no folders.
  - c5's --help panel matches c4 and c6.
- **Questions:**
  - Q1. Where is the TUI? Recommended: (a) bare `mothman one-off`.
  - Q2. How do later steps name the one-off: MOTHMAN_ASSET only, or `--id`?
  - Q3. Is a local commit enough, or must it be on the remote?
  - Q4. A decider not in the copied people.yaml. Recommended: (a) keep people.yaml outside the digest.

## delivery-architect (v4 -> v5 delta)

14 findings. A, A2, B, C and E would stop the path working or contradict a signed criterion.

- **A. Command groups and the TUI.**
  - With a one-off selected, cli/app.py still builds the collection groups at import.
  - The bare wizard is asset-only.
  - Proposed: 446 c8 builds no group for a one-off; amend 363 c2.
  - A `mothman one-off` TUI with MOTHMAN_ASSET unset.
  - 446 c9 becomes an allowlist; `pipeline process` would otherwise reconcile tickets, breaking 435 c8.
- **A2. hand_filing refuses files that match no arrival pattern, against 441 c3.**
  - 440 c2 generates an arrival_pattern per dataset.
  - 442 c2 files one delivery per collection and records undeclared files as failing without filing them.
- **B. `derived:` is declared in two places.**
  - Move it to calendar.yaml: 440 c2/c3, 438 c2.
  - The schedule gate owns 438 c8/c9, not the loader.
- **C. REQ-GHUB-433.**
  - The listing anchor becomes the newest handled comment's creation instant.
  - The first pass must not replay history: a cut-over criterion (Q-A1).
  - At rollout, c12 rewrites every open ticket once; say so in the NFRs.
- **D. vendor/.**
  - The template loads the asciinema files in its head.
  - Build a one-off page without the Demo vendor references, or publish vendor/.
- **D2. One-off publish does not reuse publish() whole.**
  - No snapshot archive into the committed snapshots, no fingerprint compare, no publish-environment gate.
  - The pipeline is rebuild/reshape/embed/render-gate only.
- **E. The REQ-DOCS-259 hold blocks code and test as dependencies.**
  - Make it a guard on `one-off open` into the repository's own root (Q-A2).
- **F. dbt target/, logs/ and dbt_packages are not gitignored.**
  - They break 440 c9 on every resume.
  - Gitignore them, and add them to 442 c4's drop list.
- **G. 438 c4's counted-side mechanism.**
  - Record agreed, share with every participant, count only the counted participants.
  - All participants derived means in development.
  - Add share_cross_table_results to the NFR.
  - is_sample and supply_state split.
- **H. Digest holes.**
  - A changed folder is also digest-checked.
  - Untracked files are included.
  - Load gates its own folder first (Q-A4).
- **I. dbt_shared is reached by relative paths.**
  - A one-off needs four `..`.
  - packages and lock equal the assets'.
  - dbt_utils is a git fetch (Q-A3).
- **J. assets.py.**
  - selected/select/why_not_selected/adopt consult the one-off listing.
  - _layout is per kind.
  - handoff carries the one-offs root.
  - A bad one-off name fails check, never another selection.
- **K. Gates.**
  - `caches` moves to DO NOT APPLY.
  - `_has_synthetic`'s unknown-name default must not decide a one-off.
  - NOT_APPLICABLE_TEXT is per kind.
- **L. Amend 363 c2.**
  - Leave c5 deliberately.
  - 442 c1 also reads assets/ folder names.
- **M. 440 c2 declares more.**
  - Column types, identifier marks, cohort bounds and expected rows, so 447 can read them.
  - Asset carries a kind.
- **Contradictions.**
  - 442 c3 against its RELIABILITY NFR (same as CLI G2).
  - 442 depends on 443: move the "already published" refusal into 443, and drop the dependency.
- **Build order:**
  - 434, 438, 436, 433 (any time), 446, 439, 440, 441, 442, 435, 444, 447, 443, 437.
- **Questions:**
  - Q-A1. 433's first-pass cut-over:
    - (a) Every comment before the deploy is handled without acting.
    - (b) Act on comments since ticket-sync was disabled.
  - Q-A2. The 259 hold:
    - (a) A guard criterion.
    - (b) Keep it as a dependency.
  - Q-A3. dbt_utils:
    - (a) git.
    - (b) A local copy.
  - Q-A4. Gate the folder at load:
    - (a) Yes.
    - (b) Accept the limit.

## Keith's answers to the review questions

- CLI Q1, the TUI: bare `mothman one-off` opens its own menu, needs no asset set, and works on one one-off per session (2026-11-21).
- CLI Q2, naming: an `--id` flag on load/decide/publish/drop; the TUI browses and selects one-offs from the `mothman one-off` entry point. Still refuse when MOTHMAN_ASSET names something else.
- CLI Q3, commit: the folder's commit must be PUSHED to the remote branch before load; the refusal gives the push command.
- CLI Q4 -> reframed by Keith ("not sure that's the model I want"): COPY NOTHING from the kind's template. The folder holds only what is generated from the recipe (hierarchy, calendar, contracts, recipe checks, presentation wording generated from the recipe), under the digest. The default check layer, people.yaml and the publishing destination are read live from one-offs/<kind>/_template/ at each step; the page's commit records which version ran. Supersedes 440 c3's copies, 440's "DEFAULTS ARE COPIED" decision and its MAINTAINABILITY NFR, and 441 c1's "copied into each generated folder".
- Keith 2026-11-21, in answer to the 433 first-pass question: "One offs should never use GitHub." A rule for every one-off kind: no tickets, no ticket comments, no GitHub API call of any kind (435 c8 already says decisions are terminal-only; this widens it to a stated rule for the kind-neutral layer, REQ-PIPE-446). Open: whether that also covers pushing the one-off's folder commit to the GitHub remote (CLI Q3's "must be pushed").
- Architect Q-A1 (433 first pass): Keith - "No one has used GitHub, this is still a local poc." No cut-over criterion: there is no comment history to replay. Record as a decision on 433 rather than a criterion.
- Git push under "never use GitHub": Keith - push is fine; the rule covers tickets, comments and API calls, and the folder commit is still pushed before load.
- Architect Q-A2 (the REQ-DOCS-259 hold): Keith - "Happy for it to go while the repo is public, this is a poc with fake data." REVERSES round 5's "block on going private": no hold, no guard; 259 comes out of 440's and 442's dependencies, and the PRIVACY NFRs say a real deployment's folders would need a private repository.
- Architect Q-A3 (a one-off's dbt_utils): Keith - a separate local copy, one shared copy configured per deployment and installed by its own setup step; a one-off's load makes no network fetch.
- Architect Q-A4: Keith - yes. Load gates its own folder with every gate its kind declares, refusing on a failure; a changed folder is digest-checked too, untracked files included.
- Dashboard question (project): Keith - every kind has one. REQ-PIPE-446 requires every kind to declare a project, and `mothman check` fails a one-off folder without one; 444 c1's title stays '<id> · <project> · QA report'.
- Drop: Keith - typed id only; `--yes` never skips it; refused with no terminal (NeedsATerminal's words).
- REQ-PIPE-363 edge cases: Keith - yes to both (omit a kind with no folders; --help's Collections panel matches c4/c6).

All review questions answered 2026-11-21. Next: delivery-scoper folds every finding and answer into v6 for Keith to re-sign.
- v6 Q1 (commits): Keith - both 'checked at' and 'built at'; load refuses an uncommitted or unpushed template (2026-11-21).
- v6 Q2 (MOTHMAN_ASSET): Keith - enduring assets only; beside --id it is refused; 363's one-off half reads '... Set it to one of: daily, quarterly. For one of 37 extractions, use mothman one-off.'
- v6 Q3 (re-load after unpublished drop): Keith - yes, it runs again; no drop record.
- v6 Q4 (decide with could-not-load/check): Keith - yes, they count as outcomes; the confirmation names them.
- v6 Q5 (list): Keith - cheap stages only (opened, committed, pushed, loaded, age, next step).
- v6 Q6 (446 size): Keith - split the mothman check criteria (c10-c14, c20) into a requirement of their own BEFORE re-signing.
