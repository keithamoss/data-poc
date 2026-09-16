"""
Tool-generic datacontract-cli helpers, shared by
qa_tools/bdm/run_datacontract_bdm.py and
qa_tools/cp/run_datacontract_cp.py. Constructing an in-memory
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

ENGINE_TAG = "datacontract-cli 1.2.0"

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

    dc = DataContract(data_contract_str=yaml.dump(d), server="local_test", include_failed_samples=True)
    return dc.test()


# datacontract-cli's own SAMPLEABLE_METRICS (missing_count/invalid_count/
# duplicate_count) - the metric types include_failed_samples above
# actually populates c.failedSamples for. type: sql (custom_sql) rules
# aren't included - see plans/qa-pipeline.md #15 for why that's a real,
# separate gap rather than an oversight here. duplicate_count is included
# but, unlike the other two, its own samples are shaped {field: value,
# duplicate_count: N} - the offending VALUE, not the identifier - so
# failing_sample_keys() below correctly returns [] for it (same class of
# gap as dbt's own `unique` test - see run_dbt_bdm.py's
# failing_sample_keys_via_values, not replicated here since it needs
# a fresh read of the source CSV this module doesn't otherwise hold).
# Soda and dbt each already cover the equivalent duplicate/unique check
# with real samples, so this is a narrow, single-tool gap, not a blind
# spot on the check itself.
SAMPLEABLE_METRICS = {"missing_count", "invalid_count", "duplicate_count"}


def check_id_from_quality_definition(quality_definition: str | None) -> str | None:
    """Pulls `check_id` out of a real datacontract-cli check's own
    `qualityDefinition` - a YAML string dump of the original ODCS
    quality rule, customProperties included, confirmed for real
    (2026-09-16) against a real `DataContract.test()` run, not assumed.
    Same `customProperties: [{property, value}, ...]` shape
    check_lifecycle.py's own `_custom_properties_to_dict()` already
    parses from the contract file directly - not reused here since that
    function takes an already-parsed dict, not a raw YAML string, and
    pulling in check_lifecycle.py from this tool-plumbing module would
    be a backwards dependency (check_lifecycle validates check
    definitions; this module runs the real tool). None for a
    schema-derived check (field_is_present/field_required/field_unique)
    - those aren't declared under `quality:` at all, so they have no
    qualityDefinition and are already filtered out by each caller's own
    `_QUALITY_CHECK_TYPES` guard before this ever gets called on one."""
    if not quality_definition:
        return None
    doc = yaml.safe_load(quality_definition) or {}
    for prop in doc.get("customProperties") or []:
        if prop.get("property") == "check_id":
            return prop.get("value")
    return None


def failing_sample_keys(check, pk_column: str) -> list[str]:
    """Pulls just pk_column's value out of check.failedSamples -
    datacontract-cli's own _samples_for() already restricts each sample
    dict to {identifier column(s), the failing field}, so this never
    touches full row content; pk_column narrows further to exactly one
    column, matching every other tool's samples. Empty when the tool
    didn't capture any (metric not sampleable, or a passing check)."""
    samples = getattr(check, "failedSamples", None) or []
    return [str(s[pk_column]) for s in samples if pk_column in s]
