"""The run_ids tests/conftest.py's fixture deliveries are RECOGNISED as.

Why these are not the fixture's own names (REQ-GEN-043). A delivery's
files are named by the supplier and its directory name means nothing, so
a run_id cannot be read off either. It is assigned by
qa_tools.common.arrivals from what arrived and when - one run per file,
named for the staged table it checks. That is what every downstream
artefact is keyed on: the run's view schema, its recorded results, the
dashboard.

So a test that drives the pipeline for "the clean fixture run" has to
ask for it by the id recognition gave it, not by the filename the
fixture happened to write. These are that id, in one place rather than
copied into a dozen test modules - and
tests/test_fixture_ids.py holds them to what the real recogniser
actually assigns, so a change in how ids are derived fails there with a
clear message instead of surfacing as a dozen "database does not exist"
errors.
"""

# ONE FILE IS ONE ARRIVAL, AND A RUN ID IS ITS STAGED TABLE'S SPELLING
# (REQ-PIPE-105, 2026-10-02). These were `run_001`/`cp_run_001`, which
# were positional - forbidden by REQ-PIPE-057 criterion 18.
#
# Birth Registrations maps one to one: each fixture delivery is one file.
BDM_REF_RUN_ID = "birth_registrations__202601010600000000"
BDM_DIRTY_RUN_ID = "birth_registrations__202601020600000000"

# CHILD PROTECTION DOES NOT. Each fixture delivery is six files, so six
# arrivals and six runs. A run sees its siblings through the period
# overlay (criterion 5), filled in as each file of a delivery is filed -
# so the run that sees THE WHOLE DELIVERY is its last-filed file, and a
# same-instant delivery is filed in dataset-id order, which puts
# cp-placements last. That is what "the clean reference run" means now:
# a run that can read all six clean tables. CP_REF_RUN_IDS is the set,
# for a test that means every run of the delivery.
CP_REF_RUN_ID = "cp_placements__202601010600000000"
CP_DIRTY_RUN_ID = "cp_placements__202604010600000000"

_CP_TABLES = ("cp_carers", "cp_case_workers", "cp_clients",
              "cp_investigations", "cp_notifications", "cp_placements")
CP_REF_RUN_IDS = tuple(f"{t}__202601010600000000" for t in _CP_TABLES)
CP_DIRTY_RUN_IDS = tuple(f"{t}__202604010600000000" for t in _CP_TABLES)

# THE RUN FOR ONE TABLE, where a check is about one table. Evidently's
# PSI check is about cp_notifications and is evaluated only in that
# table's own run (run_evidently_cp._psi_applies), so a test of it means
# the notifications run of each delivery rather than the run that sees
# the whole delivery.
CP_REF_NOTIFICATIONS_RUN_ID = "cp_notifications__202601010600000000"
CP_DIRTY_NOTIFICATIONS_RUN_ID = "cp_notifications__202604010600000000"
