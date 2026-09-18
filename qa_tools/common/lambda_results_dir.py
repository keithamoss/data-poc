"""
A real, necessary Lambda-only fix, found while writing the AWS event-
driven MVP's Lambda handlers (plans/running-thoughts.md #5 Thread B /
docs/aws-event-driven-mvp-design.md): every qa_tools/{bdm,cp}/run_*.py
module (plus orchestrate_bdm.py's/orchestrate_cp.py's own dataset_stats
write) imports qa_tools.common.qa_results_writer.write_qa_result with NO
results_dir override, so it defaults to that module's own QA_RESULTS_DIR
constant - this repo's real, committed qa_results/ directory. That
default is a real, unwritable path inside a real Lambda's deployment
package (Lambda's filesystem is read-only outside /tmp) - every one of
those writes would fail in production with no local fix at the call
site, since results_dir is a default PARAMETER value (bound once, at
each module's own import time - the exact same class of bug run_single()
itself hit with build_one()'s out_dir default, see orchestrate_bdm.py's
own comment on that).

patch_write_qa_result_for_lambda() rebinds each of those modules' own
`write_qa_result` name (not qa_results_writer.py's default - that would
need changing the function's own bound default, not just monkeypatching
a module attribute) to a version that always writes under qa_results_root
instead - the same "override a module's own imported name" seam every
existing test already uses (monkeypatch.setattr(run_dbt_bdm,
"write_qa_result", ...)), just applied for real, at Lambda runtime,
instead of as a no-op test stub.
"""
from __future__ import annotations
import functools
from pathlib import Path

from qa_tools.common.qa_results_writer import write_qa_result as _real_write_qa_result

BDM_MODULES = ["qa_tools.bdm.orchestrate_bdm", "qa_tools.bdm.run_dbt_bdm", "qa_tools.bdm.run_soda_bdm",
               "qa_tools.bdm.run_datacontract_bdm", "qa_tools.bdm.run_evidently_bdm"]
CP_MODULES = ["qa_tools.cp.orchestrate_cp", "qa_tools.cp.run_dbt_cp", "qa_tools.cp.run_soda_cp",
              "qa_tools.cp.run_datacontract_cp", "qa_tools.cp.run_evidently_cp"]


def patch_write_qa_result_for_lambda(module_names: list[str], qa_results_root: str) -> None:
    """Real, permanent (not pytest-monkeypatch-reverted - a Lambda
    invocation has no test teardown) module-attribute rebind. Safe to
    call more than once per module (idempotent - always rebinds to a
    fresh partial against the given root)."""
    import importlib

    patched = functools.partial(_real_write_qa_result, results_dir=Path(qa_results_root))
    for module_name in module_names:
        module = importlib.import_module(module_name)
        module.write_qa_result = patched
