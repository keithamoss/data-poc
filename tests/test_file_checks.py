"""File checks are asked of each file's bytes before it is loaded, and
recorded in a scope of their own (REQ-QAC-096)."""
from __future__ import annotations

import pytest

from qa_tools.common import check_id, file_checks as fc

COLUMNS = ["id", "name", "born"]


def _write(tmp_path, data: bytes, name="supply.csv"):
    p = tmp_path / name
    p.write_bytes(data)
    return p


def _by_check(findings):
    return {f.check: f for f in findings}


class TestEachFaultIsNamed:
    """Criteria 3, 14 and 18, against the evaluator alone."""

    def test_a_clean_file_passes_everything(self, tmp_path):
        found = fc.evaluate(_write(tmp_path, b"id,name,born\n1,Ann,2020\n2,Bo,2021\n"), COLUMNS)
        assert [f.check for f in found] == list(fc.NAMES)
        assert {f.status for f in found} == {fc.PASS}
        assert fc.refusal(found) is None

    def test_not_utf8(self, tmp_path):
        f = _by_check(fc.evaluate(_write(tmp_path, b"id,name,born\n1,Ren\xe9e,2020\n"), COLUMNS))
        assert f[fc.ENCODING].status == fc.FAIL
        assert "line 2" in f[fc.ENCODING].words and "Ren" not in f[fc.ENCODING].words

    def test_wrong_delimiter(self, tmp_path):
        f = _by_check(fc.evaluate(_write(tmp_path, b"id;name;born\n1;Ann;2020\n"), COLUMNS))
        assert f[fc.DELIMITER].status == fc.FAIL
        # A header that does not split has no names to compare - never a pass.
        assert {f[c].status for c in (fc.HEADER_ROW, fc.HEADER_NAMES_UNIQUE,
                                       fc.FIELDS_PER_ROW, fc.COLUMN_ORDER)} == {fc.NODATA}

    def test_no_header_row(self, tmp_path):
        f = _by_check(fc.evaluate(_write(tmp_path, b"1,Ann,2020\n2,Bo,2021\n"), COLUMNS))
        assert f[fc.HEADER_ROW].status == fc.FAIL
        assert "Ann" not in f[fc.HEADER_ROW].words

    def test_an_empty_file(self, tmp_path):
        f = _by_check(fc.evaluate(_write(tmp_path, b""), COLUMNS))
        assert f[fc.HEADER_ROW].status == fc.FAIL

    def test_a_repeated_header_name(self, tmp_path):
        f = _by_check(fc.evaluate(_write(tmp_path, b"id,name,name\n1,Ann,Ann\n"), COLUMNS))
        assert f[fc.HEADER_NAMES_UNIQUE].status == fc.FAIL
        assert "name" in f[fc.HEADER_NAMES_UNIQUE].words

    @pytest.mark.parametrize("row", [b"1,Ann\n", b"1,Ann,2020,extra\n"])
    def test_short_and_long_rows_alike(self, tmp_path, row):
        f = _by_check(fc.evaluate(_write(tmp_path, b"id,name,born\n2,Bo,2021\n" + row), COLUMNS))
        assert f[fc.FIELDS_PER_ROW].status == fc.FAIL
        assert "line 3" in f[fc.FIELDS_PER_ROW].words
        assert "Ann" not in f[fc.FIELDS_PER_ROW].words

    def test_every_row_one_field_too_many(self, tmp_path):
        """The uniform case the loader takes without error (decision: a
        fourth loader behaviour)."""
        f = _by_check(fc.evaluate(_write(tmp_path, b"id,name,born\n1,Ann,2020,x\n2,Bo,2021,y\n"),
                                  COLUMNS))
        assert f[fc.FIELDS_PER_ROW].status == fc.FAIL
        assert f[fc.FIELDS_PER_ROW].words.startswith("2 rows")

    def test_column_order_only_warns(self, tmp_path):
        found = fc.evaluate(_write(tmp_path, b"name,id,born\nAnn,1,2020\n"), COLUMNS)
        f = _by_check(found)
        assert f[fc.COLUMN_ORDER].status == fc.WARN
        assert fc.refusal(found) is None

    def test_a_quoted_comma_and_line_break_are_one_field(self, tmp_path):
        f = _by_check(fc.evaluate(_write(tmp_path, b'id,name,born\n1,"Ann, Jr\nII",2020\n'),
                                  COLUMNS))
        assert f[fc.FIELDS_PER_ROW].status == fc.PASS

    def test_a_byte_order_mark_is_not_a_fault(self, tmp_path):
        f = _by_check(fc.evaluate(_write(tmp_path, b"\xef\xbb\xbfid,name,born\n1,Ann,2020\n"),
                                  COLUMNS))
        assert f[fc.HEADER_ROW].status == fc.PASS and f[fc.COLUMN_ORDER].status == fc.PASS


class TestTheEvaluatorsOwnBug:
    """Criterion 13."""

    def test_it_raises_naming_the_check(self, tmp_path, monkeypatch):
        def broken(p, expected):
            raise ZeroDivisionError("ours")
        monkeypatch.setitem(fc._EVALUATORS, fc.FIELDS_PER_ROW, broken)
        with pytest.raises(fc.FileCheckCrashed, match="fields_per_row"):
            fc.evaluate(_write(tmp_path, b"id,name,born\n"), COLUMNS)


class TestIdentity:
    """Criterion 4."""

    def test_ids_are_derived_and_valid(self):
        from qa_tools.common import hierarchy

        for ds in hierarchy.all_datasets():
            for d in fc.active():
                parsed = check_id.parse(fc.check_id_for(ds, d.check))
                assert (parsed.dataset, parsed.tool) == (ds.dataset_id, "file")

    def test_it_is_not_a_data_check_tool(self):
        """Criterion 9."""
        from qa_tools.common import qa_results_reader as r

        assert "file" not in r.TOOL_ORDER
        assert "file" not in r.EXPECTED_TOOLS
        assert "file" not in r.RESULT_TOOLS


# ---- Through the real staging path (criteria 1, 7, 8, 11, 12, 15, 16, 17) ----


import dbsupport  # noqa: E402

from qa_tools.bdm import build_per_run_warehouses as bdm  # noqa: E402
from qa_tools.common import load_log, qa_store, supply_db  # noqa: E402

_RECEIPT = "2026-09-25T09:00:00+08:00"
_LATER = "2026-09-26T09:00:00+08:00"
_HEADER = "registration_number,child_family_name"


@pytest.fixture
def staging(tmp_path, monkeypatch):
    dbsupport.use_empty_supply_db(monkeypatch)
    return tmp_path


def _results(run="run_001"):
    with supply_db.connect() as conn:
        qa_store.ensure_schema(conn)
        return conn.execute(
            f'SELECT check_id, status, scope, tool, load_attempt, delivery, filename, extra '
            f'FROM "{qa_store.SCHEMA}".check_result WHERE run_key = ? ORDER BY id',
            [run]).fetchall()


def _staged():
    with supply_db.connect(read_only=True) as conn:
        return [r[0] for r in conn.execute(
            "SELECT table_name FROM information_schema.tables WHERE table_schema = ?",
            [supply_db.STAGING_SCHEMA]).fetchall() if not r[0].startswith("_")]


def _stage(path, received=_RECEIPT, run="run_001"):
    return bdm.build_one(run, str(path), "2026-09-25", received_at=received,
                          delivery_name="drop-1")


@pytest.mark.parametrize("fault, data", [
    (fc.ENCODING, f"{_HEADER}\nBR1,Ren\xe9e\n".encode("latin-1")),
    (fc.DELIMITER, b"registration_number;child_family_name\nBR1;SMITH\n"),
    (fc.HEADER_ROW, b"BR1,SMITH\nBR2,JONES\n"),
    (fc.HEADER_NAMES_UNIQUE, b"registration_number,registration_number\nBR1,BR1\n"),
    # Criterion 17's own named case: short rows load today as empty values.
    (fc.FIELDS_PER_ROW, f"{_HEADER}\nBR1,SMITH\nBR2\n".encode()),
])
def test_each_failure_refuses_the_file_and_is_recorded(staging, fault, data):
    path = staging / "supply.csv"
    path.write_bytes(data)
    assert _stage(path) is None
    assert _staged() == [], "a refused file leaves no table (criterion 11)"
    rows = _results()
    failed = [r for r in rows if r[1] == fc.FAIL]
    assert failed and failed[0][0].endswith(f".{fault}_file")
    assert {r[2] for r in rows} == {qa_store.FILE_SCOPE} and {r[3] for r in rows} == {"file"}
    (record,) = load_log.failures()
    assert f"file check {fault}" in record.reason and "supply.csv" in record.reason
    # Against the delivery, the file and the attempt (criteria 7, 8).
    assert {(r[5], r[6]) for r in rows} == {("drop-1", "supply.csv")}
    assert len({r[4] for r in rows}) == 1 and rows[0][4] is not None
    for r in rows:
        assert "SMITH" not in r[7]["finding"] and "Ren" not in r[7]["finding"]


def test_a_column_order_warning_loads_as_usual(staging):
    """Criteria 12 and 18."""
    path = staging / "supply.csv"
    path.write_text("child_family_name,registration_number\nSMITH,BR1\n")
    assert _stage(path) is not None
    statuses = {r[0].rsplit(".", 1)[-1]: r[1] for r in _results()}
    assert statuses["column_order_file"] == fc.WARN
    assert not load_log.failures()


def test_a_clean_file_records_six_passes_against_its_load(staging):
    path = staging / "supply.csv"
    path.write_text(f"{_HEADER}\nBR1,SMITH\n")
    assert _stage(path) is not None
    rows = _results()
    assert len(rows) == len(fc.NAMES) and {r[1] for r in rows} == {fc.PASS}
    (loaded,) = [r for r in load_log.records() if r.loaded]
    assert loaded.loaded


def test_a_reprocessed_file_keeps_both_attempts(staging):
    """Criterion 16: fixed and reprocessed under the same arrival, the
    second attempt's results sit beside the first's."""
    path = staging / "supply.csv"
    path.write_text(f"{_HEADER}\nBR1\n")
    assert _stage(path) is None
    path.write_text(f"{_HEADER}\nBR1,SMITH\n")
    assert _stage(path) is not None
    rows = _results()
    attempts = sorted({r[4] for r in rows})
    assert len(attempts) == 2 and len(rows) == 2 * len(fc.NAMES)
    first = [r for r in rows if r[4] == attempts[0]]
    assert any(r[1] == fc.FAIL for r in first)


def test_re_staging_an_unchanged_file_records_nothing_new(staging):
    """No new load attempt, so no new results - the repetition
    load_log.record_load() exists to stop."""
    path = staging / "supply.csv"
    path.write_text(f"{_HEADER}\nBR1,SMITH\n")
    _stage(path)
    _stage(path)
    assert len(_results()) == len(fc.NAMES)


def test_an_evaluator_bug_fails_the_load_and_records_nothing(staging, monkeypatch):
    """Criterion 13, through the loader: it propagates rather than being
    absorbed by the loader's own catch-all."""
    def broken(p, expected):
        raise ZeroDivisionError("ours")
    monkeypatch.setitem(fc._EVALUATORS, fc.ENCODING, broken)
    path = staging / "supply.csv"
    path.write_text(f"{_HEADER}\nBR1,SMITH\n")
    with pytest.raises(fc.FileCheckCrashed):
        _stage(path)
    assert _results() == [] and load_log.records() == []


def test_child_protection_is_screened_too(staging):
    """Criterion 15, the other collection's loader."""
    from qa_tools.cp import build_cp_warehouses as cp

    path = staging / "cp_carers.csv"
    path.write_text("carer_id,given_name\nC1\n")
    assert cp.add_table_to_run("run_001", "cp_carers", str(path), received_at=_RECEIPT,
                               dataset_id="cp-carers", delivery_name="drop-1") is None
    assert any(r[1] == fc.FAIL and r[0].endswith(".fields_per_row_file")
               for r in _results())


def test_a_load_with_no_dataset_id_is_recorded_under_the_real_dataset(staging):
    """Found with the file checks (2026-10-05): build_cp_warehouses fell
    back to the TABLE name when a caller (the `mothman cp qa` path) gave
    it no dataset id, so its load record was filed under 'cp_carers' - a
    dataset that does not exist, which a failed-load blocker keyed on
    'cp-carers' never sees."""
    from qa_tools.cp import build_cp_warehouses as cp

    path = staging / "cp_carers.csv"
    path.write_text("carer_id,given_name\nC1,Ann\n")
    cp.add_table_to_run("run_001", "cp_carers", str(path), received_at=_RECEIPT,
                        delivery_name="drop-1")
    assert {r.dataset_id for r in load_log.records()} == {"cp-carers"}


class TestNeverInAStatus:
    """Criteria 9 and 10, at the one status function every gate and the
    dashboard's promoted-health read (promotion.status_of). Found before
    the first commit: supply_status.latest_results reads every scope, so a
    column-order WARNING would have turned a green supply amber and changed
    what the amber setting does with it."""

    _DS = "data-asset-1.registry-services.civil-registration.birth-registrations"

    def _record(self, tail, status):
        return {"dataset_id": "birth-registrations", "check_id": f"{self._DS}.{tail}",
                "status": status}

    def test_a_file_warning_does_not_change_a_green_supply(self):
        from qa_tools.common import promotion

        results = [self._record("row_count_dbt", "pass"),
                   self._record("column_order_file", "warn")]
        assert promotion.status_of("birth-registrations", results, reads={}) == "green"

    def test_file_checks_alone_are_no_active_checks(self):
        from qa_tools.common import promotion

        results = [self._record("encoding_file", "pass")]
        assert promotion.status_of("birth-registrations", results, reads={}) is None
