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
