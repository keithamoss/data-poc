"""
Tool-generic Soda Core helpers, shared by qa_tools/bdm/run_soda_bdm.py
and qa_tools/cp/run_soda_cp.py. The actual check-to-dashboard-field
mapping (dimension/label per check, custom-name handling) is genuinely
different per dataset and stays in each dataset's own file - see
plans/qa-pipeline.md #84.
"""
from __future__ import annotations

from soda.sampler.sampler import Sampler
from soda.sampler.sample_ref import SampleRef

ENGINE_TAG = "Soda Core 3.5"

# Matches datacontract-cli's own hardcoded _FAILED_SAMPLE_LIMIT (see
# datacontract_common.py) - one consistent cap across every tool's
# failing-row samples, not a per-tool guess. See plans/qa-pipeline.md #15.
FAILING_SAMPLE_LIMIT = 5


class CaptureSampler(Sampler):
    """Soda's own DefaultSampler computes failing-row samples then
    explicitly discards them ("Samples are not sent to Soda Cloud") -
    this captures them instead, keyed by check name, so
    evaluate_soda_bdm/evaluate_soda_cp can pull out just the identifier
    column after scan.execute() (never full row content - see
    plans/qa-pipeline.md #15's "flag it, not full row content" line).

    Triggered two ways: automatically for "failed rows" checks (Soda
    always samples those - confirmed empirically, not just documented),
    and opt-in via `samples limit:` in the checks YAML for ordinary
    metric checks (missing_count/invalid_percent/etc.) - one sampler
    instance handles both uniformly, replacing DefaultSampler either way.
    """

    def __init__(self):
        self.captured: dict[str, list[dict]] = {}

    def store_sample(self, sample_context) -> SampleRef:
        columns = [c.name for c in sample_context.sample.get_schema().columns]
        rows = sample_context.sample.get_rows()
        self.captured[sample_context.check_name] = [dict(zip(columns, row)) for row in rows[:FAILING_SAMPLE_LIMIT]]
        return SampleRef(
            name=sample_context.sample_name,
            schema=sample_context.sample.get_schema(),
            total_row_count=len(rows),
            stored_row_count=0,
            type=SampleRef.TYPE_NOT_PERSISTED,
            message="Captured in-process for the QA dashboard - never sent anywhere external.",
        )


def failing_sample_keys(captured: dict[str, list[dict]], check_name: str, pk_column: str) -> list[str]:
    """Pulls just pk_column's value out of whatever CaptureSampler captured
    for this check - a metric check's sample carries every table column
    (Soda doesn't pre-restrict the way datacontract-cli does), a "failed
    rows" check's sample usually already carries only the identifier
    column its own fail query selected. Either way, only pk_column's
    value ever leaves this function - never other row content."""
    rows = captured.get(check_name, [])
    return [str(row[pk_column]) for row in rows if row.get(pk_column) is not None]


def check_id_from_resource_attributes(check: dict) -> str | None:
    """Pulls `check_id` out of a real Soda scan result's own
    `resourceAttributes` - a list of `{name, value}` pairs Soda copies
    straight from the check's `attributes:` block in the checks YAML
    (confirmed against a real scan, 2026-09-16, not assumed) - one check
    result only ever carries its own attributes, so unlike dbt's schema.
    yml-wide lookup (see check_lifecycle.dbt_check_id_lookup()'s own
    docstring on the collision bug that needed guarding against), there's
    no cross-check ambiguity to resolve here."""
    for attr in check.get("resourceAttributes") or []:
        if attr.get("name") == "check_id":
            return attr.get("value")
    return None


def threshold(spec: dict | None) -> float | None:
    if not spec:
        return None
    for key in ("greaterThan", "greaterThanOrEqual"):
        if key in spec:
            return spec[key]
    # a lower-bound-only spec (row_count's warn/fail also carry a lessThan
    # side) - "upper bound wins for a single scalar" convention, same one
    # the now-removed equivalent engine's _numeric_threshold() used.
    return next(iter(spec.values()), None)
