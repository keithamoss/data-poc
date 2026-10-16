"""
Birth Registrations' own place in the hierarchy, resolved rather than
restated (REQ-QAC-039).

WHAT THIS REPLACES. Until 2026-09-23 each of the six BDM modules
declared its own copy: all four real-tool scripts carried
`AGENCY_ID`/`COLLECTION_ID`/`DATASET_ID` as literals, while
`orchestrate_bdm.py` and `build_results_from_history.py` carried only
agency and dataset - which is why BDM named its collection four times
and still never passed it to `write_qa_result()`, so the collection
vanished at the storage layer. A duplication problem as much as an
omission.

This is the direct counterpart of `qa_tools/cp/cp_common.py`, and
deliberately the same shape: one literal saying WHICH dataset these
scripts are for, everything else looked up from
`contract/data-asset.yaml` through `qa_tools/common/hierarchy.py`.
"""
from __future__ import annotations

from qa_tools.common import hierarchy

# The one thing these scripts genuinely declare: which dataset they are
# for. Everything below is looked up from it.
DATASET_ID = "birth-registrations"

DATASET = hierarchy.dataset(DATASET_ID)

AGENCY_ID = DATASET.agency_id
AGENCY_NAME = DATASET.agency_name
COLLECTION_ID = DATASET.collection_id
COLLECTION_NAME = DATASET.collection_name
DATASET_NAME = DATASET.dataset_name
TABLE = DATASET.table
