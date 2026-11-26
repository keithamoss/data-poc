# REQ-PIPE-403 criterion 1 - the baseline, measured 2026-11-16 (Perth)

The register refuses `evidence:` on a requirement that is not built, so this waits
here. Move it into REQ-PIPE-403's evidence, verbatim, in the change that builds it.

```yaml
    evidence:
      - >
        CRITERION 1, THE BASELINE (2026-11-16 Perth, overnight run 13). From
        empty on this sandbox, `mothman env reset-synthetic` then `mothman
        pipeline bootstrap`, quarterly then daily, no test, agent or other
        mothman process running (counted at each start). QUARTERLY: commit
        f8fe5c1a, 21:14:03-21:54:48 UTC, load 0.88/1.85/2.50 at the start and
        1.39/1.22/1.26 at the end. The bootstrap's own lines: "Took Child
        Protection and Emergency Department and Linkage Products 2293s, in total
        2429s", "OVER BUDGET ... 2437s ... 1717s over". DAILY: a container
        restart killed the first daily run part-way, so it was re-run alone on
        commit 3626a72f (the same code as f8fe5c1a plus a morning-report edit),
        22:01:38-22:07:38 UTC, load 0.89/1.28/1.29 at the start and
        1.39/1.30/1.28 at the end: "Took Birth Registrations 309s, in total
        357s", "Within budget ... 357s".
      - >
        WHAT THIS BASELINE IS NOT. It was taken AFTER REQ-PIPE-431 and
        REQ-PIPE-432 (speed batch A) and after REQ-PIPE-380/382/383 and
        REQ-GEN-381 (#134 steps 2-3) had merged, so it is not a "before" for
        those, which were measured per run instead (REQ-PIPE-432's evidence). It
        IS before REQ-PIPE-397's first change, which is what this criterion
        asks. The per-stage split the criterion names (generation, target
        trials, each stream's replay, confirmations) and the replay's profile
        shares are NOT here. The bootstrap buffers its output, so the log's
        timestamps are not stage times, and py-spy is not installed. Only the
        two totals above are measured. Logs:
        scratchpad/b403/{quarterly,daily}.log (session-local). CRITERION 1
        STAYS UNMET until the stage split is measured (PROVISIONAL, overnight
        2026-11-16).
```

## The after-measurement (2026-11-16 Perth, morning, with Keith around)

Same method as the baseline: from empty, `mothman env reset-synthetic` then
`mothman pipeline bootstrap`, quarterly then daily, no test, agent or other
mothman process running (counted at each start: 0). Commit 6433e8a8: speed
batch B (REQ-PIPE-397/400/430, REQ-GEN-398/399), the timing batch, REQ-GEN-392,
TS-113 and the rolling-anchor batch (critic-fixed) on top of the baseline's code.
Logs: scratchpad/a403/{quarterly,daily}.log (session-local).

- QUARTERLY: 07:58:39-08:19:42 UTC, load 0.57/1.35/1.67 at the start and
  1.20/1.21/1.36 at the end. "Took generation 1m 04s, Child Protection and
  Emergency Department and Linkage Products 20m, in total 21m." "OVER BUDGET:
  this bootstrap took 1262s ... 542s over." Against the baseline's 2437s: 1175s
  less, 48% faster.
- DAILY: 08:19:45-08:25:08 UTC, load 1.20/1.21/1.36 at the start and
  1.23/1.27/1.35 at the end. "Took generation 44s, Birth Registrations 4m 36s,
  in total 5m 20s." "Within budget ... 321s." Against the baseline's 357s: 36s
  less, 10% faster.
- Both runs logged 74 datacontract-cli "relation ... does not exist" warnings
  on Child Protection's cross-table checks, the same count as the baseline
  log. Not new.
- The quarterly asset is still 542s over REQ-PIPE-250's 720s budget.
- An earlier attempt at 07:57 was refused by the reset's identity guard before
  doing anything: the container's environment carried stale MOTHMAN_ASSET and
  MOTHMAN_SUPPLY_DSN values (`data-asset-1`, `.../supply`). Both were unset for
  the measured runs.
