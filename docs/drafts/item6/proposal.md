# Item 6 and the Emergency Department dataset: the proposal

For Keith, morning of 2026-10-16. Scoped overnight under his mandate
("research, form your own view, scoper a couple of rounds, then the architect
and the UX reviewers ... come back with a fully scoped, fully architected and
fully reviewed proposal"). **Nothing is signed and nothing is built.** UPDATE 2026-10-16: all twelve signed by Keith that morning (REQ-TEST-252 added, REQ-TEST-239 cut to the lean harness, REQ-DASH-244 reading the contracts) and moved into requirements.yaml; this page is the history of how they were reached.

How it was made: research (`groundwork.md`) -> the main session's position ->
delivery-scoper rounds 1 and 2 -> delivery-architect, delivery-cli-ux and
delivery-dashboard-ux in parallel -> scoper round 3/4 -> an architect
verification pass -> scoper round 5 -> the Emergency Department drafts
re-drafted on top, last (Keith's ask). Every call made along the way is in
`position.md` (calls 1-30) and in each requirement's `decisions:`.

## What it is, in one paragraph

Adding a collection today means copying ~2,200 lines of per-collection code,
and a third collection would be silently skipped or treated as Child
Protection in ~45 places. The research measured that only ~16% of Birth
Registrations' code and ~7% of Child Protection's is genuinely specific, almost
all of it in the generator. So: one shared module per QA tool, built from Child
Protection's (N-table) code; a registry of collections derived from
`contract/data-asset.yaml`; one small adapter module per collection for what
genuinely differs, plus a generator provider; each collection's dbt files in
its own folder. Every refactor step is proved byte-identical by a capture-and-
compare harness that runs each commit's own code in a git worktree. Then
Emergency Department is configuration, an adapter, a provider and its check
files - and Child Protection shrinks once its scenarios move.

## The requirements

`requirements.yaml` - eleven, in build order:

| Id | What |
|---|---|
| REQ-TEST-239 | The equivalence harness: `mothman debug equivalence capture --ref <sha>` / `compare` across seven named surfaces |
| REQ-PIPE-240 | The collection registry, its gate (incl. a literal gate with a shrinking allowlist), and the dispatch sites that survive the series |
| REQ-QAC-241 | Check sources from the registry; Evidently checks to YAML; dbt files per collection folder |
| REQ-QAC-242 | One shared module per tool plus staging; differences behind named legacy flags on either adapter |
| REQ-PIPE-243 | Shared orchestrator, dataset stats and results; `qa_tools/bdm/` and `qa_tools/cp/` deleted |
| REQ-GEN-246 | Shared generator driver; one provider per collection (lands straight after 243) |
| REQ-DASH-244 | One dashboard-data builder, one `COLLECTION_DATA` const; two visible changes (below) |
| REQ-TEST-245 | A CLI group factory; `--help` stays byte-identical and imports no tool library |
| REQ-TEST-249 | Proof: a fake collection goes from generation to the rendered page touching only its own files |
| REQ-QAC-247 | (after ED) Retire every behavioural legacy flag, one change each, verdict changes reported |
| REQ-PIPE-248 | (after ED) Unify every collection on the N-table recorded shapes; Birth Registrations regenerated |

`docs/drafts/emergency-department/requirements-draft.yaml` - ten, on top:
REQ-QAC-231 (config and ~13 checks), REQ-GEN-232 (provider), REQ-PIPE-233
(what item 6 does not cover), REQ-DASH-234 (third agency), REQ-GEN-235 (TS-9,
65, 66, 67 move), REQ-GEN-236 (TS-3a/3b), REQ-GEN-251 (an ED participation gap
for TS-61), REQ-GEN-237 (TS-57 to TS-61 on ED, the empty-elsewhere rule),
REQ-GEN-238 (Child Protection shrink), REQ-PIPE-250 (the 12-minute bootstrap).

Order: 239 -> 240 -> 241 -> 242 -> 243 -> 246 -> 244/245 -> 249, then ED
231 -> 232 -> 251 -> 233 -> 234 -> 235/236/237 -> 238 -> 250. 247 and 248
any time after 244. Cost: about 4-5 hours of chained captures for item 6.

## Significant calls I made, for you to sense-check

1. **Byte-identical first, behaviour later.** Differences between the two
   copies (e.g. Birth Registrations' Soda `[scope]` check-name suffix, Child
   Protection's empty dimensions on 88 Soda checks) are preserved behind named
   flags during the refactor and retired afterwards, each as its own approved
   change. (position 2, 25)
2. **The recorded shapes unify on Child Protection's N-table forms**, and
   Birth Registrations' synthetic history is regenerated when they do. (3)
3. **Evidently check definitions move out of Python into YAML** under
   `contract/`. Ids and prose unchanged. (5)
4. **A generator provider is its own module** (`generator/collections/<id>.py`),
   separate from the QA adapter, so a real deployment's adapter carries no
   generator code. The "small adapter" budget (~150 lines, reported not
   enforced) measures the QA adapter only. (round 2, call 4)
5. **AWS (CDK stack, ingest Lambdas) is out of scope**, logged as follow-up. (9)
6. **Proof strategy: chained captures by commit in a git worktree**, ~4-5 h
   rather than ~10 h with module patching. (24)
7. **A missing collection fails the whole dashboard build** (a zero-run one
   renders the existing "nothing supplied" notice; `mothman check` catches an
   unwired one first). (14, 15)
8. **Two visible dashboard changes**: a dataset's "View on GitHub" opens its
   ODCS contract at that dataset, and the agency-level pill is removed. (16, 17)
9. **The CLI keeps one command group per collection**; making it work at ~30
   collections is separate, later work (running-thoughts #101). (22)
10. **Your hard 12 minutes** is read as three consecutive from-empty bootstraps
    each under 12 minutes on this sandbox, plus a budget line the bootstrap
    prints - not an enforced CI gate. (ED REQ-PIPE-250)

## Questions only you can answer

1. **REQ-PIPE-170 criterion 31** (built): "both collections" becomes "every
   collection the data asset declares" - exact text in REQ-PIPE-240's decisions.
2. **What "~30" counts**: thirty collections each with its own command group,
   or a handful of collections holding ~30 datasets? Nothing waits on it.
3. **Row-level failing values on Emergency Department**: should its checks on
   postcode, sex, age group and arrival time record failing rows, or counts
   only? (A real-data privacy question; harmless on synthetic data.)
4. **Sign-off of Emergency Department's proposed 13 checks** (REQ-QAC-231).
