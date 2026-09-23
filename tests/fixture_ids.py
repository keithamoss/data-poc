"""The run_ids tests/conftest.py's fixture deliveries are RECOGNISED as.

Why these are not the fixture's own names (REQ-GEN-043). A delivery's
files are named by the supplier and its directory name means nothing, so
a run_id cannot be read off either. It is assigned by
qa_tools.common.arrivals from RECEIPT ORDER within the collection - the
first Birth Registrations delivery we received is run_001. That is a
real observable, and it is what every downstream artefact is keyed on:
the per-run DuckDB file, the qa_results/ directory, the dashboard.

So a test that drives the pipeline for "the clean fixture run" has to
ask for it by the id recognition gave it, not by the filename the
fixture happened to write. These are that id, in one place rather than
copied into a dozen test modules - and
tests/test_fixture_ids.py holds them to what the real recogniser
actually assigns, so a change in how ids are derived fails there with a
clear message instead of surfacing as a dozen "database does not exist"
errors.
"""

BDM_REF_RUN_ID = "run_001"
BDM_DIRTY_RUN_ID = "run_002"

CP_REF_RUN_ID = "cp_run_001"
CP_DIRTY_RUN_ID = "cp_run_002"
