"""The decision log as a table, and a decision as one transaction
(REQ-PIPE-091, carrying REQ-PIPE-074's content).

WHY EVERY TEST USES ITS OWN DATASET ID. The log is append-only and the
database enforces it, so there is no cleaning up after a test - which is
the mechanism working, not an inconvenience. A unique dataset id per test
gives isolation without asking for an exemption from the guarantee under
test.
"""
from __future__ import annotations

import uuid

import psycopg
import pytest

from qa_tools.common import decision_log as dl
from qa_tools.common import qa_store, supply_db

AGENCY = "child-protection-family-support"
COLLECTION = "child-protection"
WHEN = "2026-09-27T10:00:00+08:00"
LATER = "2026-09-27T14:00:00+08:00"


@pytest.fixture
def conn(supply_dsn):
    with supply_db.connect(label="test-decision-log") as c:
        qa_store.ensure_schema(c)
        yield c


@pytest.fixture
def dataset():
    """A dataset id nothing else in the suite has decided anything about."""
    return f"cp-{uuid.uuid4().hex[:12]}"


def a_decision(dataset, **over) -> dl.Decision:
    fields = dict(
        agency_id=AGENCY, collection_id=COLLECTION, dataset_id=dataset,
        action=dl.PROMOTE, supply="cp_clients__20260927100000000000",
        actor="keith@example.gov.au", actor_kind=dl.PERSON,
        effective_at=WHEN, to_slot="2026-Q3")
    fields.update(over)
    return dl.Decision(**fields)


class TestItLivesInTheMetadataSchema:
    """Criterion 1."""

    def test_the_table_is_in_the_metadata_schema(self, conn):
        found = conn.execute(
            "SELECT 1 FROM information_schema.tables "
            "WHERE table_schema = ? AND table_name = 'decision'",
            [qa_store.SCHEMA]).fetchall()
        assert found, f"no decision table in the {qa_store.SCHEMA} schema"

    def test_it_does_not_hang_off_a_qa_run(self, conn, dataset):
        """Deliberately no foreign key to `qa.run`. A decision is a person
        acting on what a run found, not part of the run - and every other
        table here cascades from it, so `DELETE FROM run` would take the
        decisions with it. Regenerating QA history is a routine thing to
        do; losing the decision log is not."""
        with dl.apply_decision(conn, a_decision(dataset)):
            pass
        conn.execute(f'DELETE FROM "{qa_store.SCHEMA}".run WHERE run_key = ?', ["nope"])
        # The real assertion is structural: nothing references run.
        refs = conn.execute(
            "SELECT 1 FROM information_schema.table_constraints tc "
            "JOIN information_schema.constraint_column_usage ccu "
            "  ON ccu.constraint_name = tc.constraint_name "
            "WHERE tc.table_schema = ? AND tc.table_name = 'decision' "
            "AND tc.constraint_type = 'FOREIGN KEY' AND ccu.table_name = 'run'",
            [qa_store.SCHEMA]).fetchall()
        assert not refs, "the decision log cascades from qa.run"
        assert len(dl.decisions_for(conn, dataset)) == 1


class TestADecisionAndItsEffectAreOneTransaction:
    """Criterion 2, which is the whole reason this is a table.

    A committed log and a warehouse change cannot be made atomic by any
    mechanism, so the record could say a supply was promoted when the
    promotion had failed. In one database it is one transaction.
    """

    def test_the_effect_runs_inside_the_transaction(self, conn, dataset):
        marker = f"probe_{uuid.uuid4().hex[:8]}"
        with dl.apply_decision(conn, a_decision(dataset)) as entry_id:
            assert entry_id > 0
            conn.execute(f'CREATE TABLE "{qa_store.SCHEMA}".{marker} (x int)')
        assert len(dl.decisions_for(conn, dataset)) == 1
        conn.execute(f'DROP TABLE "{qa_store.SCHEMA}".{marker}')

    def test_a_failed_effect_takes_THE_ENTRY_with_it(self, conn, dataset):
        """The half that matters. Without one transaction this leaves a log
        entry saying a promotion happened that did not - which is worse
        than no log, because somebody would believe it."""
        with pytest.raises(RuntimeError, match="the promotion blew up"):
            with dl.apply_decision(conn, a_decision(dataset)):
                raise RuntimeError("the promotion blew up")

        assert dl.decisions_for(conn, dataset) == [], \
            "the entry survived an effect that failed"

    def test_the_entry_is_not_visible_to_another_connection_until_it_commits(
            self, conn, dataset, supply_dsn):
        """"Neither can be observed without the other", literally: a second
        connection sees nothing mid-transaction."""
        with supply_db.connect(label="test-decision-log-observer") as observer:
            with dl.apply_decision(conn, a_decision(dataset)):
                assert dl.decisions_for(observer, dataset) == []
            assert len(dl.decisions_for(observer, dataset)) == 1


class TestItIsJudgedAgainstTheLogInsideTheTransaction:
    """Criteria 3 and 4, and REQ-PIPE-074 criteria 6 and 7."""

    def test_a_routine_promotion_needs_no_reason(self, conn, dataset):
        """REQ-PIPE-074 criterion 7, and it keeps the rest honest: demand a
        reason for everything and every reason becomes "ok"."""
        with dl.apply_decision(conn, a_decision(dataset)) as entry_id:
            assert entry_id
        assert dl.decisions_for(conn, dataset)[0]["reason"] is None

    def test_a_rejection_without_a_reason_is_refused(self, conn, dataset):
        with pytest.raises(dl.DecisionRefused, match="needs a reason"):
            with dl.apply_decision(conn, a_decision(
                    dataset, action=dl.REJECT, to_slot=None, from_slot="2026-Q3")):
                pass
        assert dl.decisions_for(conn, dataset) == []

    def test_promoting_a_red_supply_without_a_reason_is_refused(self, conn, dataset):
        with pytest.raises(dl.DecisionRefused, match="came back red"):
            with dl.apply_decision(conn, a_decision(dataset, supply_is_red=True)):
                pass

    def test_promoting_a_red_supply_WITH_a_reason_is_recorded(self, conn, dataset):
        with dl.apply_decision(conn, a_decision(
                dataset, supply_is_red=True,
                reason="the failing check is a known upstream artefact")):
            pass
        assert "known upstream artefact" in dl.decisions_for(conn, dataset)[0]["reason"]

    def test_superseding_a_promoted_supply_without_a_reason_is_refused(
            self, conn, dataset):
        """THE ONE THAT NEEDS THE LOG. Whether this is a supersession is a
        fact about other rows, so it cannot be judged from the decision
        alone - which is why the judgement is inside the transaction."""
        with dl.apply_decision(conn, a_decision(dataset)):
            pass
        with pytest.raises(dl.DecisionRefused, match="superseding"):
            with dl.apply_decision(conn, a_decision(
                    dataset, supply="cp_clients__20260927140000000000",
                    effective_at=LATER)):
                pass

    def test_re_promoting_THE_SAME_supply_is_not_a_supersession(self, conn, dataset):
        """It supersedes nothing - it is the same supply. Treating it as one
        would demand a reason for an idempotent re-run."""
        d = a_decision(dataset)
        with dl.apply_decision(conn, d):
            pass
        with dl.apply_decision(conn, a_decision(dataset, effective_at=LATER)):
            pass
        assert len(dl.decisions_for(conn, dataset)) == 2

    def test_a_supply_promoted_then_demoted_no_longer_blocks_the_slot(
            self, conn, dataset):
        with dl.apply_decision(conn, a_decision(dataset)):
            pass
        with dl.apply_decision(conn, a_decision(
                dataset, action=dl.DEMOTE, to_slot=None, from_slot="2026-Q3",
                effective_at=LATER, reason="withdrawn by the supplier")):
            pass
        # The slot is empty again, so the next promotion is routine.
        with dl.apply_decision(conn, a_decision(
                dataset, supply="cp_clients__20260928090000000000",
                effective_at="2026-09-28T09:00:00+08:00")):
            pass
        assert len(dl.decisions_for(conn, dataset)) == 3

    def test_a_decision_takes_a_lock_on_every_slot_it_names(self, conn, dataset):
        """Criterion 4, asserted by watching the real lock. A second
        connection cannot get the same advisory lock while the first holds
        it, which is what "not judged against the same state" means."""
        with supply_db.connect(label="test-decision-log-contender") as other:
            with dl.apply_decision(conn, a_decision(dataset)):
                held = other.execute(
                    "SELECT pg_try_advisory_xact_lock(hashtext(?))",
                    [f"{dataset}/2026-Q3"]).fetchall()[0][0]
                assert held is False, "a second decision on the same slot was not blocked"

    def test_a_refile_locks_both_slots_in_a_fixed_order(self, conn, dataset):
        """Sorted, so two concurrent re-files in opposite directions cannot
        deadlock. Asserted on the effect: both slots are held."""
        with supply_db.connect(label="test-decision-log-contender") as other:
            with dl.apply_decision(conn, a_decision(
                    dataset, action=dl.REFILE, from_slot="2026-Q2", to_slot="2026-Q3",
                    reason="it was for the previous quarter")):
                for slot in ("2026-Q2", "2026-Q3"):
                    held = other.execute(
                        "SELECT pg_try_advisory_xact_lock(hashtext(?))",
                        [f"{dataset}/{slot}"]).fetchall()[0][0]
                    assert held is False, f"{slot} was not locked"


class TestNothingCanChangeAnEntry:
    """Criterion 5, and REQ-PIPE-074 criterion 8.

    THE DATABASE ENFORCES IT, which is the criterion's own words. A
    trigger rather than only a grant: a grant is bypassed by the table's
    owner, which is the role every developer connects as - so grants
    alone would make the guarantee true of the dashboard's reader and
    false of whoever could actually do the damage.
    """

    @pytest.fixture(autouse=True)
    def _an_entry(self, conn, dataset):
        with dl.apply_decision(conn, a_decision(dataset)):
            pass

    def test_an_update_is_refused_by_the_database(self, conn, dataset):
        with pytest.raises(psycopg.Error, match="append-only"):
            conn.execute(f'UPDATE "{qa_store.SCHEMA}".decision SET reason = ? '
                          "WHERE dataset_id = ?", ["rewritten", dataset])
        assert dl.decisions_for(conn, dataset)[0]["reason"] is None

    def test_a_delete_is_refused_by_the_database(self, conn, dataset):
        with pytest.raises(psycopg.Error, match="append-only"):
            conn.execute(f'DELETE FROM "{qa_store.SCHEMA}".decision '
                          "WHERE dataset_id = ?", [dataset])
        assert len(dl.decisions_for(conn, dataset)) == 1

    def test_a_truncate_is_refused_by_the_database(self, conn, dataset):
        """The one that matters most, being the fastest way to lose the
        whole log - and this schema's own fixtures truncate qa.run
        routinely."""
        with pytest.raises(psycopg.Error, match="append-only"):
            conn.execute(f'TRUNCATE "{qa_store.SCHEMA}".decision')
        assert len(dl.decisions_for(conn, dataset)) == 1

    def test_the_refusal_names_what_to_do_instead(self, conn, dataset):
        with pytest.raises(psycopg.Error, match="new entry"):
            conn.execute(f'DELETE FROM "{qa_store.SCHEMA}".decision '
                          "WHERE dataset_id = ?", [dataset])


class TestAnUnattributedDecisionIsRefused:
    """Criterion 6, and REQ-PIPE-074 criterion 5.

    NO DEFAULT, NO PLACEHOLDER, NO 'unknown' - the same rule CLAUDE.md
    records for get_run_by(), for the same reason: a log whose actor
    column can say "unknown" is a log that answers "who decided this"
    with "nobody knows", which is not an answer.
    """

    @pytest.mark.parametrize("actor", ["", "   ", None])
    def test_a_decision_with_no_actor_is_refused(self, conn, dataset, actor):
        with pytest.raises(dl.DecisionRefused, match="needs an actor"):
            with dl.apply_decision(conn, a_decision(dataset, actor=actor)):
                pass
        assert dl.decisions_for(conn, dataset) == []

    def test_the_refusal_says_there_is_no_default(self, conn, dataset):
        with pytest.raises(dl.DecisionRefused, match="no default"):
            with dl.apply_decision(conn, a_decision(dataset, actor="")):
                pass

    def test_the_column_refuses_an_empty_actor_too(self, conn, dataset):
        """Belt and braces, and the braces are the point: the Python check
        gives an operator a readable message, and the column makes the
        guarantee hold for code that never imports this module."""
        with pytest.raises(psycopg.Error):
            conn.execute(
                f'INSERT INTO "{qa_store.SCHEMA}".decision '
                "(agency_id, collection_id, dataset_id, action, supply, to_slot, "
                "actor, actor_kind, effective_at) "
                "VALUES (?, ?, ?, 'promote', 's', '2026-Q3', '', 'person', ?)",
                [AGENCY, COLLECTION, dataset, WHEN])

    def test_an_unknown_actor_kind_is_refused(self, conn, dataset):
        with pytest.raises(dl.DecisionRefused, match="not an actor kind"):
            with dl.apply_decision(conn, a_decision(dataset, actor_kind="maybe")):
                pass


class TestEveryFactIsRecorded:
    """Criterion 7, against REQ-PIPE-074 criterion 2's own list."""

    def test_an_entry_carries_every_required_fact(self, conn, dataset):
        with dl.apply_decision(conn, a_decision(
                dataset, action=dl.REFILE, from_slot="2026-Q2", to_slot="2026-Q3",
                reason="it was for the previous quarter")):
            pass
        entry = dl.decisions_for(conn, dataset)[0]
        assert entry["actor"] == "keith@example.gov.au"
        assert entry["actor_kind"] == dl.PERSON
        assert entry["action"] == dl.REFILE
        assert entry["supply"].startswith("cp_clients__")
        assert entry["from_slot"] == "2026-Q2"
        assert entry["to_slot"] == "2026-Q3"
        assert entry["reason"]
        assert entry["effective_at"] is not None
        assert entry["recorded_at"] is not None

    def test_the_two_instants_are_different_facts(self, conn, dataset):
        """`effective_at` is when the warehouse changed; `recorded_at` is
        when this row was written. A decision taken earlier and recorded
        after the fact is exactly the case an audit asks about."""
        with dl.apply_decision(conn, a_decision(
                dataset, effective_at="2026-01-01T09:00:00+08:00")):
            pass
        entry = dl.decisions_for(conn, dataset)[0]
        assert entry["effective_at"].year == 2026
        assert entry["effective_at"] < entry["recorded_at"]

    def test_a_rule_is_distinguished_from_a_person(self, conn, dataset):
        """REQ-PIPE-074 criteria 3 and 4. "Promoted by auto-promotion" and
        "promoted by Keith" are different facts, and an audit that cannot
        separate them cannot answer the only question it exists for."""
        entry_id = dl.record_automatic(conn, a_decision(
            dataset, actor="auto-promotion", actor_kind=dl.RULE))
        assert entry_id
        entry = dl.decisions_for(conn, dataset)[0]
        assert entry["actor_kind"] == dl.RULE
        assert entry["actor"] == "auto-promotion"

    def test_record_automatic_refuses_a_persons_decision(self, conn, dataset):
        with pytest.raises(dl.DecisionRefused, match="a RULE made"):
            dl.record_automatic(conn, a_decision(dataset))

    def test_a_refile_is_ONE_entry(self, conn, dataset):
        """REQ-PIPE-074 criterion 9. As a demote-then-promote pair it would
        be two decisions with two reasons and an instant between them
        where the period held nothing - and a reader could not tell that
        pair from somebody changing their mind twice."""
        with dl.apply_decision(conn, a_decision(
                dataset, action=dl.REFILE, from_slot="2026-Q2", to_slot="2026-Q3",
                reason="it was for the previous quarter")):
            pass
        assert len(dl.decisions_for(conn, dataset)) == 1

    def test_a_refile_must_name_both_slots(self, conn, dataset):
        with pytest.raises(dl.DecisionRefused, match="names both slots"):
            with dl.apply_decision(conn, a_decision(
                    dataset, action=dl.REFILE, from_slot=None, to_slot="2026-Q3",
                    reason="somewhere")):
                pass


class TestNoDatabaseMeansNoDecision:
    """Criterion 8, and the NFR behind it: availability is deliberately
    traded away here (Keith, 2026-09-26). A filing decision acts on the
    warehouse, so one recorded while the warehouse was unreachable is a
    decision about nothing.
    """

    def test_an_unreachable_database_refuses_the_decision_and_names_the_host(self):
        with pytest.raises(supply_db.SupplyDbError, match="cannot reach"):
            supply_db.connect(
                dsn="postgresql://user:password@127.0.0.1:1/nothing-here",
                label="test-unreachable")

    def test_it_queues_nothing_locally(self, tmp_path, monkeypatch):
        """The part that is about this module rather than about connecting:
        no spool file, no retry directory, nothing to apply later. Asserted
        by watching the whole filesystem under a redirected home and cwd."""
        import os

        monkeypatch.chdir(tmp_path)
        monkeypatch.setenv("HOME", str(tmp_path))
        before = {p for p in tmp_path.rglob("*")}
        with pytest.raises(supply_db.SupplyDbError):
            with supply_db.connect(
                    dsn="postgresql://user:password@127.0.0.1:1/nothing-here",
                    label="test-unreachable") as c:
                with dl.apply_decision(c, a_decision("cp-anything")):
                    pass
        assert {p for p in tmp_path.rglob("*")} == before, \
            f"a refused decision left something behind: {os.listdir(tmp_path)}"

    def test_the_module_has_no_spool_path_at_all(self):
        """Structural, because the absence is the requirement. A queue would
        arrive as a path constant or an open() - and the reason to assert it
        is that adding one later would look like a helpful robustness fix."""
        import inspect

        source = inspect.getsource(dl)
        assert "open(" not in source
        assert "Path(" not in source


class TestWhatAPeriodResolvedTo:
    """Criterion 9, and REQ-PIPE-074 criterion 12 - both answered from
    this table alone."""

    def test_an_empty_slot_resolves_to_nothing(self, conn, dataset):
        assert dl.promoted_into(conn, dataset, "2026-Q3") is None
        assert dl.promoted_supply(conn, dataset) is None

    def test_a_promotion_fills_the_slot(self, conn, dataset):
        with dl.apply_decision(conn, a_decision(dataset)):
            pass
        assert dl.promoted_into(conn, dataset, "2026-Q3").startswith("cp_clients__")

    def test_a_demotion_empties_it_again(self, conn, dataset):
        with dl.apply_decision(conn, a_decision(dataset)):
            pass
        with dl.apply_decision(conn, a_decision(
                dataset, action=dl.DEMOTE, to_slot=None, from_slot="2026-Q3",
                effective_at=LATER, reason="withdrawn")):
            pass
        assert dl.promoted_into(conn, dataset, "2026-Q3") is None
        assert dl.promoted_supply(conn, dataset) is None

    def test_it_answers_AS_AT_A_PAST_INSTANT(self, conn, dataset):
        """The criterion's own words. What the warehouse held in the past is
        not what it holds now, and a log that can only answer "now" is a
        log that cannot answer the question it exists for."""
        with dl.apply_decision(conn, a_decision(dataset)):
            pass
        with dl.apply_decision(conn, a_decision(
                dataset, action=dl.DEMOTE, to_slot=None, from_slot="2026-Q3",
                effective_at=LATER, reason="withdrawn")):
            pass
        # Between the two: the slot was full.
        assert dl.promoted_into(conn, dataset, "2026-Q3",
                                 as_at="2026-09-27T12:00:00+08:00") is not None
        # After both: empty.
        assert dl.promoted_into(conn, dataset, "2026-Q3",
                                 as_at="2026-09-27T18:00:00+08:00") is None
        # Before either: also empty, and not "the first one we know of".
        assert dl.promoted_into(conn, dataset, "2026-Q3",
                                 as_at="2026-01-01T00:00:00+08:00") is None

    def test_as_at_reads_the_EFFECTIVE_instant_not_the_recorded_one(
            self, conn, dataset):
        """A decision taken in January and recorded today took effect in
        January. Asking what the warehouse held in February must say yes."""
        with dl.apply_decision(conn, a_decision(
                dataset, effective_at="2026-01-15T09:00:00+08:00")):
            pass
        assert dl.promoted_into(conn, dataset, "2026-Q3",
                                 as_at="2026-02-01T00:00:00+08:00") is not None

    def test_the_most_recently_promoted_supply_skips_one_since_demoted(
            self, conn, dataset):
        """`WHERE action = 'promote' ORDER BY effective_at DESC` would answer
        this wrongly: a supply promoted in March and demoted in April is not
        what is promoted now."""
        with dl.apply_decision(conn, a_decision(dataset, supply="first")):
            pass
        with dl.apply_decision(conn, a_decision(
                dataset, action=dl.DEMOTE, supply="first", to_slot=None,
                from_slot="2026-Q3", effective_at=LATER, reason="withdrawn")):
            pass
        assert dl.promoted_supply(conn, dataset) is None

    def test_a_reversal_is_a_new_entry_rather_than_an_edit(self, conn, dataset):
        """REQ-PIPE-074 criterion 8. Both entries survive, so the history
        says a supply was promoted AND later withdrawn - which is the fact,
        where an edit would leave only the second half."""
        with dl.apply_decision(conn, a_decision(dataset)):
            pass
        with dl.apply_decision(conn, a_decision(
                dataset, action=dl.DEMOTE, to_slot=None, from_slot="2026-Q3",
                effective_at=LATER, reason="withdrawn")):
            pass
        actions = [e["action"] for e in dl.decisions_for(conn, dataset)]
        assert actions == [dl.PROMOTE, dl.DEMOTE]


class TestOneDatasetsHistoryCostsNothingForAnother:
    """Criterion 11. At 30 datasets over years the difference between an
    index and a scan is the difference between a query and a wait."""

    def test_there_is_an_index_leading_on_the_dataset(self, conn):
        indexes = {row[0]: row[1] for row in conn.execute(
            "SELECT indexname, indexdef FROM pg_indexes "
            "WHERE schemaname = ? AND tablename = 'decision'",
            [qa_store.SCHEMA]).fetchall()}
        assert "decision_dataset_order" in indexes
        definition = indexes["decision_dataset_order"]
        assert "dataset_id" in definition and "effective_at" in definition

    def test_reading_one_dataset_uses_it(self, conn, dataset):
        with dl.apply_decision(conn, a_decision(dataset)):
            pass
        plan = "\n".join(str(r[0]) for r in conn.execute(
            f"EXPLAIN SELECT * FROM {dl.TABLE} WHERE dataset_id = ? "
            "ORDER BY effective_at, id", [dataset]).fetchall())
        # A small table can legitimately be scanned, so this asserts the
        # index is USABLE rather than that the planner chose it - forcing
        # the choice is what `enable_seqscan` is for.
        conn.execute("SET enable_seqscan = off")
        forced = "\n".join(str(r[0]) for r in conn.execute(
            f"EXPLAIN SELECT * FROM {dl.TABLE} WHERE dataset_id = ? "
            "ORDER BY effective_at, id", [dataset]).fetchall())
        conn.execute("SET enable_seqscan = on")
        assert "decision_dataset_order" in forced, \
            f"the index is not usable for this read.\nplan: {plan}\nforced: {forced}"

    def test_one_datasets_read_does_not_return_anothers(self, conn, dataset):
        other = f"cp-{uuid.uuid4().hex[:12]}"
        with dl.apply_decision(conn, a_decision(dataset)):
            pass
        with dl.apply_decision(conn, a_decision(other)):
            pass
        assert [e["dataset_id"] for e in dl.decisions_for(conn, dataset)] == [dataset]


class TestAReaderWithNoWriteAccess:
    """Criterion 10. A reader can read the WHOLE history, and cannot add
    to it - which is the audit property this log exists to have."""

    def test_the_publisher_role_is_revoked_write_on_the_metadata_schema(
            self, conn):
        role = f"probe_reader_{uuid.uuid4().hex[:8]}"
        qa_store.ensure_publisher_role(conn, role, password="x")
        try:
            granted = {row[0] for row in conn.execute(
                "SELECT privilege_type FROM information_schema.table_privileges "
                "WHERE table_schema = ? AND table_name = 'decision' AND grantee = ?",
                [qa_store.SCHEMA, role]).fetchall()}
            assert "SELECT" in granted, "the reader cannot read the log at all"
            assert not granted & {"INSERT", "UPDATE", "DELETE", "TRUNCATE"}, \
                f"the reader holds write privileges: {sorted(granted)}"
        finally:
            conn.execute(f'REVOKE ALL ON ALL TABLES IN SCHEMA "{qa_store.SCHEMA}" '
                          f'FROM "{role}"')
            conn.execute(f'REVOKE ALL ON SCHEMA "{qa_store.SCHEMA}" FROM "{role}"')
            conn.execute(
                f'ALTER DEFAULT PRIVILEGES IN SCHEMA "{qa_store.SCHEMA}" '
                f'REVOKE ALL ON TABLES FROM "{role}"')
            conn.execute(f'DROP ROLE IF EXISTS "{role}"')

    def test_the_whole_log_is_readable_in_one_call(self, conn, dataset):
        with dl.apply_decision(conn, a_decision(dataset)):
            pass
        everything = dl.all_decisions(conn)
        assert any(e["dataset_id"] == dataset for e in everything)


class TestNoTestAssumesTheNewestEntryIsItsOwn:
    """The defect class that broke CI three times on 2026-09-29, made
    impossible to reintroduce quietly.

    THE SHAPE: `decisions_for(conn, dataset_id)[-1]`. It reads as "the
    decision I just recorded" and means "the newest decision anybody
    recorded for this dataset". Tests act on REAL dataset ids - the
    fixtures need a real table and agency - while minting periods of
    their own, so several modules write cp-carers entries into one
    worker's log. Whose entry is last depends on how pytest-xdist
    distributed the files, which is why the same code went green once
    and red twice before anybody looked.

    IT IS THE INDEX THAT IS WRONG, NOT THE READ. `[0]` is safe where a
    test mints a dataset id nobody else uses, and every current one
    does; `[-1]` is unsafe even then, because the rule writes
    `inherit-refused` entries of its own after a promotion. So this
    forbids the one spelling rather than policing the whole read.

    WHAT TO DO INSTEAD: select by the period or supply under test -
    tests/test_filing_decisions.py's own `_entry_for()` is the worked
    example, and it says why in its docstring.
    """

    def test_no_test_module_takes_the_last_entry_for_a_dataset(self):
        """READ WITH `ast`, NOT A REGEX. The first version was a regex
        and matched its own docstring, plus the helper written to
        replace the spelling - both of which quote it in prose to say
        not to use it. A guard that fires on its own explanation is one
        somebody deletes."""
        import ast
        from pathlib import Path

        root = Path(__file__).resolve().parent
        offenders = set()
        for path in sorted(root.glob("test_*.py")):
            for node in ast.walk(ast.parse(path.read_text())):
                if not isinstance(node, ast.Subscript):
                    continue
                call = node.value
                if not (isinstance(call, ast.Call)
                        and isinstance(call.func, ast.Attribute)
                        and call.func.attr == "decisions_for"):
                    continue
                index = node.slice
                if (isinstance(index, ast.UnaryOp)
                        and isinstance(index.op, ast.USub)
                        and getattr(index.operand, "value", None) == 1):
                    offenders.add(path.name)
        assert offenders == set(), (
            f"{sorted(offenders)} assert on the NEWEST decision-log entry for "
            f"a dataset, which is routinely another module's - see this "
            f"class's docstring. Select by the period or supply under test.")
