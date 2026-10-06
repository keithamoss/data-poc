"""One delivery, kept three ways, records the same history (REQ-PIPE-086
criterion 11).

THE THREE ROUTES. The pipeline's batch (`orchestrate_bdm.run_pipeline`),
the terminal keeping it (`cli.bdm.run_check(..., keep=True)`), and the
Lambda route (`s3_arrival.handle_event`, REQ-PIPE-152) - each into an
empty database of its own, over the same real generated file. Every
route now calls the same per-arrival function (criterion 1), so this
holds by construction; this test is what would notice the construction
coming apart.

WHAT IS COMPARED: the filings, the decision log and the check verdicts -
every column except the instants they were written at, the surrogate ids
(see tests/equiv_support.py) and, for the Lambda route only, the
delivery's NAME. An S3 object is recorded as a delivery named from its
bucket, key and LastModified (REQ-PIPE-152) rather than the directory the
generator wrote, which is a transport fact and not one the criterion is
about. The identity that ran each route lives only on `qa.run`, which is
not compared.

ONE BIRTH REGISTRATIONS DELIVERY, deliberately: the cheapest real chain
that files, fills an open slot, runs all four tools and gates. Each
further arrival is another full chain per route, and the routes share
every step after recording, so length adds minutes without adding a way
for them to differ.
"""
from __future__ import annotations

import json
import os
import shutil
from datetime import datetime
from pathlib import Path
from unittest.mock import MagicMock

import psycopg
import pytest

import equiv_support
from conftest import mark_test_database

ADMIN_DSN_ENV = "MOTHMAN_TEST_DSN"
RUN_ID = "run_001"
COMPARED = ("qa.filing", "qa.decision", "qa.check_result")


@pytest.fixture(scope="module")
def corpus(tmp_path_factory):
    """The real Birth Registrations generator's output, cut to its first
    delivery."""
    import generator_isolation
    from generator import generate_runs

    root = tmp_path_factory.mktemp("kept_routes")
    undo = generator_isolation.redirect(generate_runs, root)
    try:
        generate_runs.main()
    finally:
        undo()
    book = json.loads((root / "generator_bookkeeping.json").read_text())
    [first] = [e["delivery"] for e in book["birth-registrations"] if e["run_id"] == RUN_ID]
    for tree in ("deliveries", "receipts"):
        for d in (root / tree).iterdir():
            if d.name != first:
                shutil.rmtree(d)
    return root, first


def _fresh_database(name: str) -> str:
    admin = os.environ[ADMIN_DSN_ENV]
    with psycopg.connect(admin, autocommit=True) as conn:
        conn.execute(f'DROP DATABASE IF EXISTS "{name}" WITH (FORCE)')
        conn.execute(f'CREATE DATABASE "{name}"')
        mark_test_database(conn, name)
    info = psycopg.conninfo.conninfo_to_dict(admin)
    info["dbname"] = name
    return psycopg.conninfo.make_conninfo(**info)


def _drop_database(name: str) -> None:
    with psycopg.connect(os.environ[ADMIN_DSN_ENV], autocommit=True) as conn:
        conn.execute(f'DROP DATABASE IF EXISTS "{name}" WITH (FORCE)')


def _route(tree: Path, db_name: str, run) -> dict:
    """`run()` against a new database with every on-disk path under `tree`."""
    from qa_tools.common import supply_db

    mp = pytest.MonkeyPatch()
    original = equiv_support.apply_redirects(tree)
    dsn = _fresh_database(db_name)
    scratch = None
    try:
        mp.setenv("MOTHMAN_SUPPLY_DSN", dsn)
        scratch = supply_db.scratch_dir()
        mp.delenv("GITHUB_REPOSITORY", raising=False)
        # NO SCRIPTED DECISIONS: they replay the synthetic scenarios over the
        # whole corpus, and would refuse a one-delivery history for missing
        # the rest. Not what any route is being compared on.
        from qa_tools.common import scripted_decisions
        mp.setattr(scripted_decisions, "SCRIPT_PATH", tree / "no_scripted_decisions.yaml")
        with supply_db.connect(label="test-kept-routes") as conn:
            from qa_tools.common import qa_store
            qa_store.ensure_schema(conn)
        run()
        return equiv_support.snapshot(dsn)
    finally:
        mp.undo()
        equiv_support.restore(original)
        if scratch is not None:
            shutil.rmtree(scratch, ignore_errors=True)
        _drop_database(db_name)


def _batch():
    from qa_tools.bdm import orchestrate_bdm
    orchestrate_bdm.run_pipeline(sequential=True)


def _terminal():
    """`mothman bdm qa --run-id <id> --commit`'s body, for the one arrival
    recognition finds."""
    from cli import bdm
    from qa_tools.common import arrivals
    [arrival] = arrivals.arrivals_for("civil-registration", "run_")
    bdm.run_check(arrival.run_id, "person@example.com", keep=True)


def _lambda(root: Path, delivery_name: str):
    """The S3 route: the delivery's one file served as an object whose
    LastModified is the delivery's own receipt instant, so the supply it
    records is the same supply."""
    def run():
        from qa_tools.common import s3_arrival
        [csv] = list((root / "deliveries" / delivery_name).glob("*.csv"))
        receipt = json.loads(
            (root / "receipts" / delivery_name / f"{csv.name}.json").read_text())
        landed = datetime.fromisoformat(receipt["received_at"])
        client = MagicMock()
        client.head_object.return_value = {"LastModified": landed}
        client.download_file.side_effect = lambda b, k, p: shutil.copy(csv, p)
        key = f"bdm/{delivery_name}/{csv.name}"
        s3_arrival.handle_event(
            {"Records": [{"s3": {"bucket": {"name": "raw"}, "object": {"key": key}}}]},
            client, prefix="bdm/")
    return run


def _project(snap: dict, drop: set[str]) -> dict:
    out = {}
    for table in COMPARED:
        names, rows = snap[table]
        keep = [i for i, n in enumerate(names) if n not in drop]
        projected = {}
        for row, count in rows.items():
            key = tuple(row[i] for i in keep)
            projected[key] = projected.get(key, 0) + count
        out[table] = (tuple(names[i] for i in keep), projected)
    return out


def _diff(a: dict, b: dict) -> list[str]:
    from collections import Counter
    return equiv_support.differences(
        {k: (c, Counter(r)) for k, (c, r) in a.items()},
        {k: (c, Counter(r)) for k, (c, r) in b.items()})


@pytest.fixture(scope="module")
def routes(corpus, worker_id, tmp_path_factory):
    root, delivery_name = corpus
    empty = tmp_path_factory.mktemp("kept_routes_empty")
    for tree in ("deliveries", "receipts"):
        (empty / tree).mkdir()
    return {
        "batch": _route(root, f"kept_batch_{worker_id}", _batch),
        "terminal": _route(root, f"kept_terminal_{worker_id}", _terminal),
        # NOTHING ON DISK: the Lambda route's only arrival is the object.
        "lambda": _route(empty, f"kept_lambda_{worker_id}", _lambda(root, delivery_name)),
    }


class TestOneDeliveryKeptThreeWays:

    def test_there_is_something_to_compare(self, routes):
        batch = routes["batch"]
        assert sum(batch["qa.filing"][1].values()) == 1
        assert sum(batch["qa.decision"][1].values()) >= 1
        assert sum(batch["qa.check_result"][1].values()) > 10

    def test_the_terminal_records_what_the_batch_records(self, routes):
        assert _diff(_project(routes["batch"], set()),
                     _project(routes["terminal"], set())) == []

    def test_the_lambda_route_records_what_the_batch_records(self, routes):
        assert _diff(_project(routes["batch"], {"delivery"}),
                     _project(routes["lambda"], {"delivery"})) == []
