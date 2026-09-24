# Post-build review

What the post-build critic agents found when turned at work that is
already BUILT AND SHIPPED, and what was decided about each finding.

Deliberately a separate file, at Keith's own ask, 2026-09-24. The
neighbouring files hold work not yet done - designs, sprints,
requirements, sightings. This one holds judgements about code that is
already in the repo and already running, which is a different thing to
read and a different thing to act on.

## The standing rule: Keith signs off every finding before anything changes

His own words, 2026-09-24: "a finding about code that we've already
shipped does deserve my eye before we change anything... I'd like to
sign off on all of their findings."

So the sequence is fixed, and it is not the same as the pre-build one:

1. A critic reports. Its report is model output, not a verdict.
2. This session VERIFIES anything load-bearing against the real code -
   a critic's finding is a claim until it has been checked, and several
   of this project's agent findings have arrived with a wrong citation
   or a wrong premise attached to a correct conclusion.
3. The finding is written up HERE, with its evidence, what it would
   cost to fix, and a recommendation.
4. **Keith decides.** Nothing in shipped code changes before that -
   not a "trivially safe" fix, not a one-liner.
5. A finding he accepts becomes real work: a requirement if it is a
   behaviour change, a bug fix with a failing test first if it is a
   defect (`CLAUDE.md`'s standing rule), or a recorded decision to
   leave it alone.

**Why the gate is stricter here than for a new requirement.** A
pre-build finding costs a conversation to act on. A post-build finding
costs a change to something people are already relying on, and the
repository's own history is the argument: a fix written to prevent a
false green introduced one (`plans/qa-pipeline.md` item 74). Acting
fast on shipped code is how the second bug gets written.

Same conventions as every other numbered-item plans file: a closed
status (`todo` / `investigate` / `in-progress` / `parked` / `done` /
`superseded`), one or more component tags, and a date. A finding that
is verified and rejected stays here as `done` with the reasoning, so
the same finding arriving again from a later pass is recognisable
rather than re-litigated.

## 2026-09-24 - the first pass, over twelve requirements built in sprints 1-6

`plans/running-thoughts.md` #34's own subject: twelve requirements were
built across 2026-09-21..23 and **not one went through any post-build
critic**. The sprints ran build, gate, commit, next, and the post-build
half of the pipeline documented in `docs/agent-orchestration.md` was
simply never invoked while they were moving. Nothing was skipped
deliberately.

The twelve: `REQ-QAC-039`, `REQ-GEN-040`, `REQ-GEN-042`, `REQ-GEN-043`,
`REQ-QAC-047`, `REQ-PIPE-048`, `REQ-PIPE-049`, `REQ-PIPE-050`,
`REQ-PIPE-051`, `REQ-PIPE-052`, `REQ-PIPE-053`, `REQ-DASH-055`.

Four critics, one pass each over the whole set rather than twelve
passes - Keith's own call, 2026-09-23 ("happy to do one pass with that,
that's fine, rather than twelve"): `delivery-critic` on all twelve,
`delivery-cli-ux-critic` on the `mothman schedule` surfaces,
`delivery-dashboard-ux-critic` then `delivery-dashboard-visual-critic`
on the dashboard ones - in that order and never in parallel, per the
orchestration doc's own hard-won constraint.

Run against a real built dashboard: 3.8MB, real embedded data, 6,545
check results across 60 runs, both datasets.

**Findings follow as each critic lands.**
