"""The scenarios package (REQ-GEN-386 criterion 4; the name SETTLED by Keith
2026-11-02): what both the generator and the bootstrap read of a synthetic
history's design, and nothing the real pipeline reads. It imports only
asset_model/, the generator and the bootstrap may import it, and a real
deployment leaves it out.

- register.py - the test scenario register in plans/supply-model.md, parsed;
- placements.py - where the generator recorded each scenario landing;
- vocabulary.py - what a scenario's link lands on, by name;
- scripted_decisions.py - the selected asset's scripted_decisions.yaml read,
  with when each decision is due (checking one against the pipeline's own
  rules is the bootstrap's, bootstrap/scripted_decision_checks.py);
- promotion_lag.py - the seeded promotion lag the bootstrap's replay clock
  applies and the Linkage Products provider predicts with (REQ-PIPE-382
  criterion 3).

The scenario map's writer is the generator's (generator/scenario_map_writer.py)
and its reader the pipeline's (qa_tools/common/scenario_map.py).
"""
