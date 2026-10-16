"""REQ-PIPE-075 criterion 13 - promotion FOLLOWS the QA run.

"...as a step that follows the QA run rather than as part of it, such
that a promotion that fails can be retried without re-running QA."

Two claims, and they need different tests. The SEPARATION is structural:
the orchestrators' own run function must not promote, so a promotion
failure cannot cost a QA run. The RETRYABILITY is behavioural: running
the step twice over an unchanged world promotes once and then does
nothing, which is what makes "just run it again" a safe instruction
rather than a way to double-write history.
"""
from __future__ import annotations

import ast
import inspect
import uuid
from pathlib import Path

import pytest

from qa_tools.common import decision_log as dl
from qa_tools.common import period_schema, promotion, qa_store, supply_db

AGENCY = "child-protection-family-support"
COLLECTION = "child-protection"
WHEN = "2026-09-28T10:00:00+08:00"


@pytest.fixture
def conn(supply_dsn):
    with supply_db.connect(label="test-promote-after-run") as c:
        qa_store.ensure_schema(c)
        yield c


def a_staged_table(conn, logical: str) -> str:
    physical = f"{logical}__a{uuid.uuid4().hex[:8]}"
    conn.execute(f'CREATE SCHEMA IF NOT EXISTS "{supply_db.STAGING_SCHEMA}"')
    conn.execute(f'CREATE TABLE "{supply_db.STAGING_SCHEMA}"."{physical}" (id integer)')
    return physical


class TestTheRunItselfDoesNotPromote:
    """The separation, asserted on the AST rather than on source text -
    a comment mentioning promotion is not a call to it, and this file's
    sibling learned that the hard way."""

    @pytest.mark.parametrize("module,func", [
        ("qa_tools.cp.orchestrate_cp", "_run_one_inner"),
        ("qa_tools.bdm.orchestrate_bdm", "_run_one_inner"),
    ])
    def test_the_run_function_calls_no_promotion(self, module, func):
        # The whole MODULE is parsed and the function found in the tree,
        # rather than dedenting inspect.getsource() - a function body
        # taken out of its file does not reliably parse on its own.
        mod = __import__(module, fromlist=[func])
        tree = ast.parse(Path(inspect.getfile(mod)).read_text())
        target_node = next(
            (n for n in ast.walk(tree)
             if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef)) and n.name == func),
            None)
        assert target_node is not None, f"{module}.{func} could not be found"
        called = set()
        for node in ast.walk(target_node):
            if isinstance(node, ast.Call):
                target, parts = node.func, []
                while isinstance(target, ast.Attribute):
                    parts.append(target.attr)
                    target = target.value
                if isinstance(target, ast.Name):
                    parts.append(target.id)
                called.add(".".join(reversed(parts)))
        promoting = {c for c in called if "promote" in c}
        assert not promoting, (
            f"{module}.{func} promotes ({promoting}); a promotion failure would "
            "then cost the QA run it was part of")


class TestRunningItTwiceIsSafe:
    """The retryability."""

    def test_the_second_pass_promotes_nothing_new(self, conn):
        dataset = f"cp-{uuid.uuid4().hex[:12]}"
        period = f"2099-P{uuid.uuid4().hex[:6]}"
        table = a_staged_table(conn, "clients")
        work = [dict(dataset_id=dataset, supply=table, physical_tables=[table])]

        first, failed_first = promotion.promote_each(
            conn, work, agency_id=AGENCY, collection_id=COLLECTION, period=period,
            actor="promotion-gate", actor_kind=dl.RULE, effective_at=WHEN)
        second, failed_second = promotion.promote_each(
            conn, work, agency_id=AGENCY, collection_id=COLLECTION, period=period,
            actor="promotion-gate", actor_kind=dl.RULE, effective_at=WHEN)

        assert first == [dataset]
        assert second == [], "a retry must not promote what is already promoted"
        assert not failed_first and not failed_second
        assert len(dl.decisions_for(conn, dataset)) == 1, \
            "a retry that writes a second entry turns 'just run it again' into a hazard"

    def test_and_the_tables_are_not_moved_twice(self, conn):
        dataset = f"cp-{uuid.uuid4().hex[:12]}"
        period = f"2099-P{uuid.uuid4().hex[:6]}"
        table = a_staged_table(conn, "clients")
        work = [dict(dataset_id=dataset, supply=table, physical_tables=[table])]
        for _ in range(2):
            promotion.promote_each(
                conn, work, agency_id=AGENCY, collection_id=COLLECTION, period=period,
                actor="promotion-gate", actor_kind=dl.RULE, effective_at=WHEN)
        rows = conn.execute(
            "SELECT count(*) FROM information_schema.tables WHERE table_schema = ? "
            "AND table_name <> '_manifest'",
            [period_schema.period_schema(period)]).fetchall()
        assert rows[0][0] == 1
