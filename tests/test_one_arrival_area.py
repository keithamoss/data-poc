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


# ---- Birth Registrations has the same double-write (Keith, 2026-09-27) ----
#
# BDM's STAGING never kept a second copy - that part was CP-only - but
# its generator did exactly what CP's did: a flat `data/raw/<run_id>.csv`
# per run AND a real delivery. The difference that matters is that
# `data/raw/` looked at first as though it kept a live role CP's tree
# did not - the drop directory for a file handed to
# `mothman bdm qa --file`. It did not, and the next section records
# why. So the flat GENERATED copies go and so does the directory.


def test_the_bdm_generator_writes_a_delivery_and_nothing_beside_it():
    source = (ROOT / "generator" / "generate_runs.py").read_text()
    tree = ast.parse(source)
    skip = _docstrings(tree)
    writes = [n for n in ast.walk(tree)
               if isinstance(n, ast.Attribute) and n.attr == "to_csv"]
    # to_csv(index=False) with a PATH argument is a write to disk;
    # to_csv() with no path returns a string, which is how the delivery
    # payload is built and is not a second copy.
    to_disk = []
    for call in ast.walk(tree):
        if (isinstance(call, ast.Call) and isinstance(call.func, ast.Attribute)
                and call.func.attr == "to_csv" and call.args):
            to_disk.append(call.lineno)
    assert writes, "no to_csv at all - has this generator been rewritten?"
    assert not to_disk, (
        f"generate_runs.py still writes a CSV straight to a path (line(s) {to_disk}) - "
        f"the delivery is the arrival, and a flat copy beside it is the "
        f"duplication REQ-PIPE-102 removed for Child Protection")
    assert "write_delivery" in source, \
        "the generator must still write a real delivery - that is the arrival"
    # DELIBERATELY NOT "no .csv literal anywhere". An earlier version
    # of this asserted that and failed on the `.csv` the DELIVERY's own
    # filename is built from - a true statement about the source that
    # said nothing about the duplication. What matters is whether a
    # frame is written to a path, which the check above measures
    # directly.
    del skip


def test_the_bdm_loader_has_no_raw_directory_at_all():
    """THIS TEST USED TO ASSERT THE OPPOSITE, and recording that is the
    point of the docstring.

    The first pass at REQ-PIPE-102 kept data/raw/ "because it is where
    a file handed to `mothman bdm qa --local-file` lands, and where
    run_single() normalises an arrived file to so the tools can
    resolve a relative name against it" - which described the code
    accurately and got the REASON backwards. The directory existed to
    serve relative-name resolution, relative-name resolution existed
    to serve a CSV fallback, and the fallback existed for "a supply
    checked without being staged", which run_single() never produces
    because it stages before any tool runs. Keith pushed back ("I'd
    rather it not" stay); the chain collapsed from the far end.
    """
    from qa_tools.bdm import build_per_run_warehouses

    assert not hasattr(build_per_run_warehouses, "RAW_DIR"), \
        "the loader still names a raw directory"


# ---- data/raw/ goes too (Keith, 2026-09-27: "I'd rather it not" stay) ----
#
# The earlier version of this requirement kept data/raw/ on the grounds
# that it was the drop directory for a hand-supplied file. That was
# true of the code as it
# stood and wrong about why. The directory existed to let Evidently
# resolve a CSV by RELATIVE name; run_single() copied every arriving
# file into it for that reason, and run_check_local_file() copied the
# reference in for the same one. The fallback those served claimed to
# be for "a supply checked without being staged", and run_single()
# stages - it has to, because the other three tools read the warehouse.
# The only genuinely unstaged thing was the REFERENCE, which CP already
# stages and BDM did not.


def test_no_module_still_names_a_raw_directory_in_code():
    """The same AST check as cp_raw, for data/raw/. Prose recording the
    history is exempt; a string the code evaluates is not."""
    offenders = []
    for path in SEARCHED:
        tree = ast.parse(path.read_text())
        skip = _docstrings(tree)
        for node in ast.walk(tree):
            # BOTH SPELLINGS. A literal "data/raw", and the
            # os.path.join(ROOT, "data", "raw") form this repo
            # actually uses - an earlier version of this test checked
            # only the first and passed against code that still built
            # the path from fragments.
            if (isinstance(node, ast.Constant) and isinstance(node.value, str)
                    and id(node) not in skip
                    and node.value.rstrip("/").endswith("data/raw")):
                offenders.append(f"{path.relative_to(ROOT)}:{node.lineno}: {node.value!r}")
            if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute) \
                    and node.func.attr == "join":
                parts = [a.value for a in node.args
                          if isinstance(a, ast.Constant) and isinstance(a.value, str)]
                if parts[-2:] == ["data", "raw"]:
                    offenders.append(f"{path.relative_to(ROOT)}:{node.lineno}: join(... 'data', 'raw')")
    assert not offenders, "data/raw is retired; this code still names it:\n" + "\n".join(offenders)


def test_nothing_resolves_a_csv_against_a_raw_directory():
    """`_resolve_csv` was the reason the directory existed at all."""
    from qa_tools.bdm import run_datacontract_bdm, run_evidently_bdm

    for module in (run_datacontract_bdm, run_evidently_bdm):
        assert not hasattr(module, "_resolve_csv"), \
            f"{module.__name__} still resolves a bare filename against a raw directory"
        assert not hasattr(module, "RAW_DIR"), \
            f"{module.__name__}.RAW_DIR is retired but still exported"


def test_the_bdm_drift_check_does_not_fall_back_to_a_file():
    """The BDM counterpart of the CP check above."""
    source = (ROOT / "qa_tools" / "bdm" / "run_evidently_bdm.py").read_text()
    for node in ast.walk(ast.parse(source)):
        if isinstance(node, ast.ExceptHandler):
            assert "csv" not in ast.dump(node).lower(), (
                "run_evidently_bdm still reads a CSV from an exception handler")


def test_staging_a_single_arrival_does_not_copy_it_first(tmp_path, supply_dsn, monkeypatch):
    """run_single() copied every arriving file into data/raw/ before
    staging it. The file it was handed is where it is."""
    import inspect

    from qa_tools.bdm import orchestrate_bdm

    source = inspect.getsource(orchestrate_bdm.run_single)
    # THE CODE, NOT THE COMMENTARY. An earlier version of this matched
    # the whole source and tripped on the docstring explaining what
    # RAW_DIR used to be for - prose this repo keeps on purpose.
    code = "\n".join(line for line in source.splitlines()
                      if not line.lstrip().startswith("#"))
    code = code.split('"""')[0] + "".join(code.split('"""')[2:])
    assert "RAW_DIR" not in code, \
        "run_single still copies the arriving file into a raw directory"
    assert "dest_path" not in code, \
        "run_single still stages a copy rather than the file it was given"
