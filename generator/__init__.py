"""Birth-registrations-only synthetic data generation - see CLAUDE.md's
layout table. A real package (not a flat script directory) so its modules
import unambiguously as `generator.<module>` from anywhere else in this
repo - no sys.path manipulation needed. Run its entry-point scripts as
`python3 -m generator.<module>` (this makes the repo root importable,
which flat `python3 generator/<module>.py` execution does not)."""
