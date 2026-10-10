"""The step that follows a QA run (REQ-PIPE-075 criteria 1, 2, 11-13).

promotion.after_run() is the one place the isolated pieces - the gate,
the move, the entry - are assembled into the act the pipeline performs.
Everything below it is unit-tested elsewhere; what these tests pin is
the ASSEMBLY, which is where the interesting mistakes live:

  - a status taken from a subset of the contributing checks (criterion
    2), which is how a supply promotes itself past a red cross-table
    check filed under a sibling dataset;
  - a refusal and a failure reported as the same thing, which is how an
    operator learns to ignore both;
  - one odd dataset taking the other twenty-nine down (criterion 11).
"""
from __future__ import annotations

import uuid

import pytest

from qa_tools.common import decision_log as dl
from qa_tools.common import promotion, qa_store, supply_db

AGENCY = "child-protection-family-support"
COLLECTION = "child-protection"
WHEN = "2026-09-28T10:00:00+08:00"


@pytest.fixture
def conn(supply_dsn):
    with supply_db.connect(label="test-promotion-step") as c:
        qa_store.ensure_schema(c)
        yield c


@pytest.fixture
def period():
    return f"2099-S{uuid.uuid4().hex[:6]}"


def _dataset() -> str:
    return f"cp-{uuid.uuid4().hex[:12]}"


def _staged(conn, logical: str) -> str:
    physical = f"{logical}__a{uuid.uuid4().hex[:8]}"
    conn.execute(f'CREATE SCHEMA IF NOT EXISTS "{supply_db.STAGING_SCHEMA}"')
    conn.execute(f'CREATE TABLE "{supply_db.STAGING_SCHEMA}"."{physical}" (id integer)')
    return physical


def _supply(conn, dataset_id, period, **over):
    logical = dataset_id.replace("-", "_")
    item = {"dataset_id": dataset_id, "supply": f"{dataset_id}-supply",
            "period": period, "physical_tables": [_staged(conn, logical)]}
    item.update(over)
    return item


def _result(dataset_id, status, check_id=None):
    return {"dataset_id": dataset_id, "status": status,
            "check_id": check_id or f"{dataset_id}.rowcount_dbt"}


def _run(conn, supplies, results, reads=None):
    return promotion.after_run(
        conn, agency_id=AGENCY, collection_id=COLLECTION,
        supplies=supplies, results=results, reads=reads or {},
        actor="pipeline", actor_kind=dl.RULE, effective_at=WHEN)


class TestAGreenSupplyPromotesItself:
    """Criterion 1."""

    def test_it_is_promoted_and_the_log_says_so(self, conn, period):
        ds = _dataset()
        out = _run(conn, [_supply(conn, ds, period)], [_result(ds, "pass")])
        assert out.promoted == (ds,)
        assert out.refused == {} and out.failed == {}
        assert dl.promoted_into(conn, ds, period) == f"{ds}-supply"

    def test_the_entry_carries_a_reason_a_reader_can_act_on(self, conn, period):
        ds = _dataset()
        _run(conn, [_supply(conn, ds, period)], [_result(ds, "pass")])
        rows = conn.execute(
            f"SELECT reason FROM {dl.TABLE} WHERE dataset_id = ?", [ds]).fetchall()
        assert rows and rows[0][0] == promotion.AUTOMATIC_REASON


class TestAPromotionPastAGapRedNamesIt:
    """Keith, 2026-10-06 (post-build-review #124 D3): a gap red warns rather
    than blocks, and the kept-run report then said every check passed or
    warned under a table showing two reds. The reason now names them."""

    def test_the_reason_names_each_gap_red(self, conn, period):
        ds = _dataset()
        gap = {**_result(ds, "fail", f"{ds}.volume_evidently"), "reference_gap": True,
               "measured_status": "pass"}
        out = _run(conn, [_supply(conn, ds, period)], [_result(ds, "pass"), gap])
        assert out.promoted == (ds,)
        [(reason,)] = conn.execute(
            f"SELECT reason FROM {dl.TABLE} WHERE dataset_id = ?", [ds]).fetchall()
        assert "volume_evidently" in reason
        assert "apart from 1 recorded red" in reason

    def test_with_none_the_reason_is_unchanged(self, conn, period):
        ds = _dataset()
        _run(conn, [_supply(conn, ds, period)], [_result(ds, "pass")])
        [(reason,)] = conn.execute(
            f"SELECT reason FROM {dl.TABLE} WHERE dataset_id = ?", [ds]).fetchall()
        assert reason == promotion.AUTOMATIC_REASON


class TestTheStatusComesFromEveryContributingCheck:
    """Criterion 2, and the failure it exists to stop: a referential
    check between placements and carers is filed under whichever it
    happened to be declared on, and gates BOTH."""

    def test_a_red_cross_table_check_filed_elsewhere_still_refuses(self, conn, period):
        ds = _dataset()
        sibling_check = "cp-placements.referential_dbt"
        item = _supply(conn, ds, period)
        out = _run(conn, [item],
                   [_result(ds, "pass"),
                    {"dataset_id": "cp-placements", "status": "fail",
                     "check_id": sibling_check}],
                   reads={sibling_check: [ds, "cp_placements"]})
        assert out.promoted == ()
        assert "red" in out.refused[ds]

    def test_a_check_declaring_nothing_of_ours_does_not_gate_us(self, conn, period):
        ds = _dataset()
        out = _run(conn, [_supply(conn, ds, period)],
                   [_result(ds, "pass"),
                    {"dataset_id": "cp-placements", "status": "fail",
                     "check_id": "cp-placements.unique_dbt"}],
                   reads={"cp-placements.unique_dbt": ["cp_placements"]})
        assert out.promoted == (ds,)


class TestNothingAskedIsNotGreen:
    """Criterion 12, arriving through the assembly rather than the gate:
    a run that recorded no result for a dataset gives status_of() None,
    which is exactly the check-free case."""

    def test_a_supply_no_check_touched_is_refused(self, conn, period):
        ds = _dataset()
        out = _run(conn, [_supply(conn, ds, period)], [_result(_dataset(), "pass")])
        assert out.promoted == ()
        assert "ACTIVE checks" in out.refused[ds]


class TestARefusalIsNotAFailure:
    """Both stop a promotion and they mean opposite things: a refusal is
    the gate working and the supply waits for a person; a failure is
    something broken and the supply waits for a retry."""

    def test_a_held_supply_is_refused_not_failed(self, conn, period):
        ds = _dataset()
        out = _run(conn, [_supply(conn, ds, period, held=True)], [_result(ds, "pass")])
        assert out.failed == {}
        assert "no slot" in out.refused[ds]

    def test_a_supply_nothing_could_file_is_refused_on_the_same_terms(self, conn):
        ds = _dataset()
        out = _run(conn, [_supply(conn, ds, None)], [_result(ds, "pass")])
        assert out.failed == {}
        assert "no slot" in out.refused[ds]

    def test_a_contested_supply_is_refused(self, conn, period):
        ds = _dataset()
        out = _run(conn, [_supply(conn, ds, period, contested=True)],
                   [_result(ds, "pass")])
        assert "which one is the supply" in out.refused[ds]

    def test_a_missing_table_is_a_FAILURE_and_names_the_dataset(self, conn, period):
        ds = _dataset()
        item = _supply(conn, ds, period)
        item["physical_tables"] = ["a_table_nothing_staged"]
        out = _run(conn, [item], [_result(ds, "pass")])
        assert out.promoted == ()
        assert out.refused == {}
        assert ds in out.failed


class TestOneOddDatasetDoesNotTakeTheRestDown:
    """Criterion 11. At ~30 datasets a step that abandons twenty-nine
    promotions because the thirtieth was odd is a step somebody turns
    off."""

    def test_the_others_are_still_promoted(self, conn, period):
        good_a, bad, good_b = _dataset(), _dataset(), _dataset()
        items = [_supply(conn, good_a, period), _supply(conn, bad, period),
                 _supply(conn, good_b, period)]
        items[1]["physical_tables"] = ["a_table_nothing_staged"]
        out = _run(conn, items,
                   [_result(good_a, "pass"), _result(bad, "pass"),
                    _result(good_b, "pass")])
        assert sorted(out.promoted) == sorted([good_a, good_b])
        assert list(out.failed) == [bad]


class TestRunningTheStepTwiceIsSafe:
    """Criterion 13's retryability, at the assembly level - the whole
    point of the step being separable from the run."""

    def test_the_second_pass_promotes_nothing_new(self, conn, period):
        ds = _dataset()
        items = [_supply(conn, ds, period)]
        first = _run(conn, items, [_result(ds, "pass")])
        second = _run(conn, items, [_result(ds, "pass")])
        assert first.promoted == (ds,)
        assert second.promoted == ()
        assert second.failed == {}

    def test_and_writes_exactly_one_entry(self, conn, period):
        ds = _dataset()
        items = [_supply(conn, ds, period)]
        _run(conn, items, [_result(ds, "pass")])
        _run(conn, items, [_result(ds, "pass")])
        rows = conn.execute(
            f"SELECT COUNT(*) FROM {dl.TABLE} WHERE dataset_id = ?", [ds]).fetchone()
        assert rows[0] == 1


class TestAFilledSlotStopsTheSecondSupply:
    """Criterion 4, through the assembly: the slot set is read from the
    decision log, so the supply promoted a moment ago is what refuses
    the next one."""

    def test_the_later_supply_is_refused_naming_the_filled_slot(self, conn, period):
        ds = _dataset()
        _run(conn, [_supply(conn, ds, period)], [_result(ds, "pass")])
        second = _supply(conn, ds, period, supply=f"{ds}-resupply")
        out = _run(conn, [second], [_result(ds, "pass")])
        assert out.promoted == ()
        assert "already filled" in out.refused[ds]
