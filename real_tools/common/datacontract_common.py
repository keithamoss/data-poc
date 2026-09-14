"""
Tool-generic datacontract-cli helpers, shared by
real_tools/bdm/run_datacontract_real_bdm.py and
real_tools/cp/run_datacontract_real_cp.py. Constructing an in-memory
contract copy with a "local_test" server added and calling
DataContract.test() is identical regardless of dataset; only which
contract file and which local CSV path get used differs.
DIMENSION_BY_METRIC/LABEL_BY_METRIC happen to be identical across both
existing datasets too (the same ODCS metric names mean the same thing
everywhere) - shared for that reason, not because they're subprocess/API
plumbing like the rest of this module. See plans/wider.md #20.
"""
from __future__ import annotations
import copy

import yaml

ENGINE_TAG = "datacontract-cli 1.2.0 (real)"

DIMENSION_BY_METRIC = {
    "missing_count": "completeness",
    "invalid_count": "validity",
    "duplicate_count": "uniqueness",
    "custom_sql": "consistency",
    "row_count": "completeness",
}

# A short, human-readable phrase for what each metric actually measures -
# written here, where each check result is constructed, not guessed later
# from check_name by the dashboard-building code.
LABEL_BY_METRIC = {
    "missing_count": "Null rate",
    "invalid_count": "Invalid values",
    "duplicate_count": "Duplicate rate",
    "row_count": "Row count",
}


def run_against_local_server(contract_path: str, local_path: str):
    """Loads contract_path, adds a "local_test" local server pointed at
    local_path (a CSV file, or a datacontract-cli {model}-templated path
    for a multi-table contract), and runs DataContract.test() against it.
    The file on disk is never touched - a deep copy gets the extra
    server, not the original dict - and its own "production" server (e.g.
    S3) is untouched too. Returns the DataContract `run` result (caller
    reads run.checks)."""
    from datacontract.data_contract import DataContract

    with open(contract_path) as f:
        contract_dict = yaml.safe_load(f)

    d = copy.deepcopy(contract_dict)
    d["servers"].append({
        "server": "local_test",
        "type": "local",
        "path": local_path,
        "format": "csv",
        "delimiter": "comma",
    })

    dc = DataContract(data_contract_str=yaml.dump(d), server="local_test")
    return dc.test()
