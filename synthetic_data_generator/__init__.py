"""A separate, population-scale (millions), cross-agency-identity-linked
synthetic data generator - not currently wired into the QA pipeline (see
plans/wider.md). A real package for the same reason generator/ is - see
that package's own __init__.py docstring. Shares generator/dirty.py,
generator/names_au.py, and generator/presentation.py with generator/
(imported from there, not duplicated - see plans/qa-pipeline.md #17's
dual-dirty.py bug for why keeping two copies in sync by hand is a real
risk, not just untidy)."""
