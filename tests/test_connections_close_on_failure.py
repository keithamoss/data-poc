"""A failing QA step must not leak its database connection.

WHY THIS IS WORTH A TEST RATHER THAN A CODE READ. All four of these
call sites always DID close - on the last line of the happy path. That
reads as correct and is correct whenever nothing goes wrong, which is
why it survived review: the leak only happens on the exception path,
which is the path nobody watches and the path most likely to be taken
when something is already wrong.

It is the same shape as the Soda leak found the same day
(tests/test_soda_leaves_no_connection.py): a connection left open sits
`idle in transaction` holding ACCESS SHARE on whatever it read, and the
orchestrator's own DROP SCHEMA then queues behind it until it times
out. So a run that failed for one reason would go on to fail the tidy-up
for a second, unrelated-looking one.

These assert the OUTCOME - no backend survives a raising call - rather
than looking for the word `finally`, so a later refactor to `with` or
anything else still passes.
"""
from __future__ import annotations

import pytest

from qa_tools.common import supply_db


class TestAConnectionIsReleasedWhenTheBodyRaises:
    """Exercised through supply_db.connect itself rather than through a
    whole QA run: what is under test is the release, and standing up a
    real failing dbt run to prove it would test everything except.

    ASKS THE CONNECTION, NOT pg_stat_activity. An earlier version
    counted backends and was flaky for a reason worth recording, since
    it is a trap this suite has now hit twice: a count is a fact about
    the whole database at one instant, so it moves when anything else
    connects, and it cannot tell WHICH connection it is describing.
    `conn.raw.closed` is the same claim about the one object under test.
    """

    def test_the_context_manager_releases_on_an_exception(self, supply_dsn):
        conn = None
        with pytest.raises(RuntimeError):
            with supply_db.connect(label="mothman:probe") as opened:
                conn = opened
                raise RuntimeError("the QA step blew up")
        assert conn is not None and conn.raw.closed

    def test_a_try_finally_releases_on_an_exception(self, supply_dsn):
        """The shape the four QA modules now use."""
        conn = supply_db.connect(label="mothman:probe")
        with pytest.raises(RuntimeError):
            try:
                raise RuntimeError("the QA step blew up")
            finally:
                conn.close()
        assert conn.raw.closed

    def test_the_old_shape_is_what_leaked(self, supply_dsn):
        """Pins the bug itself, so the tests above are demonstrably
        measuring something. Closing on the last line of the happy path
        leaks whenever the path is not happy."""
        conn = supply_db.connect(label="mothman:probe")
        with pytest.raises(RuntimeError):
            raise RuntimeError("the QA step blew up")
            conn.close()  # noqa: F841 - unreachable on purpose, that IS the bug
        assert not conn.raw.closed, \
            "expected the unguarded shape to leak - if it no longer does, " \
            "these tests are no longer measuring anything"
        conn.close()


class TestEveryLongLivedConnectSiteIsGuarded:
    """A structural check over the real modules, so a NEW call site
    added later cannot quietly reintroduce the shape. Deliberately
    narrow: it only looks at modules that hold a connection across a
    long body, which is where the leak has consequences."""

    MODULES = [
        "qa_tools/bdm/run_soda_bdm.py",
        "qa_tools/cp/run_soda_cp.py",
        "qa_tools/bdm/run_dbt_bdm.py",
        "qa_tools/cp/run_dbt_cp.py",
    ]

    @pytest.mark.parametrize("module", MODULES)
    def test_its_close_is_inside_a_finally(self, module):
        import ast
        from pathlib import Path

        root = Path(__file__).resolve().parent.parent
        tree = ast.parse((root / module).read_text())

        closes = [n for n in ast.walk(tree)
                  if isinstance(n, ast.Call)
                  and isinstance(n.func, ast.Attribute) and n.func.attr == "close"
                  and isinstance(n.func.value, ast.Name) and n.func.value.id == "conn"]
        assert closes, f"{module} no longer closes `conn` at all"

        guarded = set()
        for node in ast.walk(tree):
            if isinstance(node, ast.Try):
                for stmt in node.finalbody:
                    for inner in ast.walk(stmt):
                        if inner in closes:
                            guarded.add(id(inner))
        unguarded = [c for c in closes if id(c) not in guarded]
        assert not unguarded, (
            f"{module}: conn.close() at line(s) "
            f"{[c.lineno for c in unguarded]} is not in a finally - it will be "
            f"skipped whenever the body raises, leaking a backend that holds "
            f"ACCESS SHARE and blocks the orchestrator's own DROP SCHEMA")
