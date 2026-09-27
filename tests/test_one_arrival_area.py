"""A Child Protection supply lives in two places, not three (REQ-PIPE-102).

WHAT THIS REPLACED. Staging copied every delivered CP CSV into
`data/cp_raw/<run_id>/<table>.csv`, and the generator wrote each run
there as well as writing a real delivery. Both existed because
run_datacontract_cp.py and run_evidently_cp.py used to read those CSVs
off disk; REQ-QAC-088 pointed both at the warehouse and the reason went
with it. Birth Registrations never had the copy.

THE LINE THIS KEEPS. `data/deliveries/` stays - it is where a
supplier's files land, the thing the database is a copy OF. What goes
is the third copy nobody was reading.
"""
from __future__ import annotations

import ast
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent

#: Every module that could plausibly still reach for the retired tree.
SEARCHED = sorted(
    p for d in ("qa_tools", "cli", "generator", "pipeline", "dashboard")
    for p in (ROOT / d).rglob("*.py")
)


def _docstrings(tree) -> set[int]:
    """id() of every string node that is a docstring, so prose can be
    excluded from the check below."""
    out = set()
    for node in ast.walk(tree):
        if isinstance(node, (ast.Module, ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            first = node.body[0] if node.body else None
            if (isinstance(first, ast.Expr) and isinstance(first.value, ast.Constant)
                    and isinstance(first.value.value, str)):
                out.add(id(first.value))
    return out


def test_no_module_still_names_a_cp_raw_directory_IN_CODE():
    """Criterion 5, and it includes constants nothing reads.

    A constant that names a directory the code no longer writes is the
    same trap as a parameter that names a source it no longer reads -
    it looks live, and the next person wires something to it. That one
    cost this project eighty seconds a test run before it was found.

    CODE, NOT PROSE, and the distinction is deliberate. A docstring
    saying "this used to write to data/cp_raw/ and here is why it
    stopped" is exactly the kind of history this repository keeps on
    purpose - deleting it would make the next person re-derive the
    decision. Comments never reach the AST at all, and docstrings are
    excluded explicitly; what is checked is whether any string the code
    actually evaluates still names the tree.
    """
    offenders = []
    for path in SEARCHED:
        tree = ast.parse(path.read_text())
        skip = _docstrings(tree)
        for node in ast.walk(tree):
            if (isinstance(node, ast.Constant) and isinstance(node.value, str)
                    and "cp_raw" in node.value and id(node) not in skip):
                offenders.append(f"{path.relative_to(ROOT)}:{node.lineno}: {node.value!r}")
    assert not offenders, "cp_raw is retired; this code still names it:\n" + "\n".join(offenders)


def test_staging_takes_no_raw_dir_argument():
    """Criterion 1, checked structurally so a re-added parameter fails
    here rather than being noticed by its side effects."""
    from qa_tools.cp import build_cp_warehouses

    import inspect
    for name in ("add_table_to_run", "build_all"):
        params = inspect.signature(getattr(build_cp_warehouses, name)).parameters
        assert "raw_dir" not in params, \
            f"build_cp_warehouses.{name}() took raw_dir back"


def test_staging_writes_no_second_copy_of_the_file_it_was_given(tmp_path, supply_dsn):
    """Criterion 1, behaviourally. Stage a CSV from a directory of its
    own and assert nothing new appears anywhere under data/."""
    from qa_tools.cp import build_cp_warehouses

    source_dir = tmp_path / "delivery"
    source_dir.mkdir()
    csv = source_dir / "cp_case_workers.csv"
    csv.write_text("worker_id,full_name,office,_extract_timestamp\n"
                    "W1,A Worker,Perth,2026-01-01T00:00:00+00:00\n")

    data_dir = ROOT / "data"
    before = {p for p in data_dir.rglob("*")} if data_dir.exists() else set()

    build_cp_warehouses.add_table_to_run(
        "one_area_run", "cp_case_workers", str(csv), dataset_id="cp-case-workers")

    after = {p for p in data_dir.rglob("*")} if data_dir.exists() else set()
    new = {p for p in after - before if p.is_file()}
    # The loader's own scratch CSV is written and removed inside the
    # call, so anything left is a copy that outlived it.
    assert not new, f"staging left files behind under data/: {sorted(str(p) for p in new)}"


def test_the_drift_check_does_not_fall_back_to_a_file():
    """Criterion 4. A bare `except` that reads a CSV turns a database
    failure into a plausible-looking number, which is the shape this
    project argues against everywhere else."""
    source = (ROOT / "qa_tools" / "cp" / "run_evidently_cp.py").read_text()
    tree = ast.parse(source)
    for node in ast.walk(tree):
        if isinstance(node, ast.ExceptHandler):
            body = ast.dump(node)
            assert "csv" not in body.lower(), (
                "run_evidently_cp still reads a CSV from an exception handler - "
                "a warehouse failure must fail, not produce a drift number from a file")


def test_the_generator_writes_a_delivery_and_nothing_beside_it():
    """Criterion 2, checked at the source. generate_cp_runs used to
    write each run to data/cp_raw/<run_id>/ AND as a real delivery."""
    source = (ROOT / "generator" / "generate_cp_runs.py").read_text()
    tree = ast.parse(source)
    skip = _docstrings(tree)
    named = [n.value for n in ast.walk(tree)
              if isinstance(n, ast.Constant) and isinstance(n.value, str)
              and "cp_raw" in n.value and id(n) not in skip]
    assert not named, f"the generator still writes to a cp_raw path: {named}"
    assert "write_delivery" in source, \
        "the generator must still write a real delivery - that is the arrival"


@pytest.mark.parametrize("module_name", [
    "qa_tools.cp.run_datacontract_cp",
    "qa_tools.cp.run_evidently_cp",
    "qa_tools.cp.build_cp_warehouses",
    "qa_tools.cp.orchestrate_cp",
])
def test_no_module_still_exports_a_retired_constant(module_name):
    """Criterion 5 again, at import time rather than by text - a
    constant reachable as an attribute is a constant something can
    still use."""
    import importlib

    module = importlib.import_module(module_name)
    for attr in ("CP_RAW_DIR", "MANIFEST_PATH"):
        assert not hasattr(module, attr), f"{module_name}.{attr} is retired but still exported"
