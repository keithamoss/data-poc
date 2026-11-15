"""The scenarios package (REQ-GEN-386 criterion 4; the name SETTLED by Keith
2026-11-02): what both the generator and the bootstrap read of a synthetic
history's design, and nothing the real pipeline reads. It imports only
asset_model/, the generator and the bootstrap may import it, and a real
deployment leaves it out.

PROVISIONAL, step 3 of #134 (2026-11-15): it holds one module so far -
promotion_lag, the seeded promotion lag the bootstrap's replay clock applies
and the Linkage Products provider predicts with (REQ-PIPE-382 criterion 3, OQ1
SETTLED by Keith 2026-11-14 as (a): in scenarios/). The register parser, the
placements reader, the map vocabulary and the scripted_decisions.yaml reader
follow with REQ-GEN-386's own build.
"""
