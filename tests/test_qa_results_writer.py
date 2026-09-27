"""Tests for qa_tools/common/qa_results_writer.py - the per-run recorder.

WHAT IT GUARANTEES, and none of these changed when the storage did
(REQ-PIPE-089): a tool's raw output is kept byte-for-byte unmodified,
never reshaped or mutated; the run's provenance is recorded ALONGSIDE
that output rather than inside it; and re-running one tool for one run
replaces its previous answer rather than adding a second.

IT USED TO ASSERT ON FILES, because a write produced
`qa_results/<agency>/<collection>/<scope>/<run_id>/<tool>.json` and
returned that path. The claims are the same; what reads them back is now
the reader rather than `json.loads(path.read_text())`. That is a better
test of the same thing, because the reader is what every real consumer
uses - the old assertions could have passed while nothing could read what
was written.

The FAN-OUT - which dataset each record lands against, and why a spanning
record lands against none of them - is REQ-PIPE-038's and REQ-QAC-037's
own subject, covered by tests/test_history_rekey.py and
tests/test_qa_results_fan_out.py rather than here.
"""
from __future__ import annotations

from qa_tools.common import qa_results_reader as reader
from qa_tools.common.qa_results_writer import write_qa_result

AGENCY = "registry-services"
COLLECTION = "civil-registration"
WHEN = "2026-01-01T00:00:00+00:00"


def test_raw_output_is_preserved_unmodified(clean_qa_history, finish_runs):
    """A nested structure with the awkward things in it - a null, a
    float, an empty list - because a writer that round-tripped through
    anything lossy would flatten exactly these."""
    raw = {"results": [{"unique_id": "test.x", "status": "fail", "failures": 3,
                         "message": None, "elapsed": 0.25, "adapter_response": {}}],
            "metadata": {"invocation_id": "abc", "env": []}}
    write_qa_result(AGENCY, COLLECTION, "run_01", WHEN, "dbt", raw)
    finish_runs("run_01", agency=AGENCY, collection=COLLECTION, when=WHEN)

    assert reader.read_raw(AGENCY, COLLECTION, "run_01", "dbt")["raw_output"] == raw


def test_the_runs_provenance_is_recorded_alongside_the_output_not_inside_it(
        clean_qa_history, finish_runs):
    """The point of the whole `raw_output` field: what the tool produced
    stays exactly what the tool produced. A writer that stamped its own
    timestamp into the payload would be editing evidence."""
    raw = {"metrics": [], "some_tool_field": "untouched"}
    write_qa_result(AGENCY, COLLECTION, "run_01", WHEN, "evidently", raw,
                     run_by="keith@example.com")
    finish_runs("run_01", agency=AGENCY, collection=COLLECTION, when=WHEN,
                run_by="keith@example.com")

    envelope = reader.read_raw(AGENCY, COLLECTION, "run_01", "evidently")
    assert envelope["run_timestamp"] == WHEN
    assert envelope["run_by"] == "keith@example.com"
    assert "run_timestamp" not in envelope["raw_output"]
    assert "run_by" not in envelope["raw_output"]
    assert envelope["raw_output"] == raw


def test_the_verified_records_are_recorded_beside_the_raw_output(
        clean_qa_history, finish_runs):
    """Both halves of one write, readable separately - which is the
    reason they are stored apart at all: a verdict query must not drag
    megabytes of tool output it never asked for."""
    verified = [
        {"check_id": "births.id.not_null", "check_name": "id not null",
         "dataset_id": "birth-registrations", "status": "pass", "metric_value": 0.0},
        {"check_id": "births.sex.accepted_values", "check_name": "sex accepted",
         "dataset_id": "birth-registrations", "status": "fail", "metric_value": 7.0},
    ]
    write_qa_result(AGENCY, COLLECTION, "run_01", WHEN, "soda", {"hasErrors": False},
                     verified=[dict(r) for r in verified])
    finish_runs("run_01", agency=AGENCY, collection=COLLECTION, when=WHEN)

    found = {r["check_id"]: r for r in reader.read_one(AGENCY, COLLECTION, "run_01", "soda")}
    assert set(found) == {"births.id.not_null", "births.sex.accepted_values"}
    assert found["births.sex.accepted_values"]["status"] == "fail"
    assert found["births.sex.accepted_values"]["metric_value"] == 7.0
    assert reader.read_raw(AGENCY, COLLECTION, "run_01", "soda")["raw_output"] == {
        "hasErrors": False}


def test_a_write_with_no_verified_records_still_records_the_invocation(
        clean_qa_history, finish_runs):
    """A tool can legitimately produce output and no verdicts - a scan
    that errored before evaluating anything. The invocation is still a
    fact about the run, and losing it would make the run look as though
    that tool never ran."""
    write_qa_result(AGENCY, COLLECTION, "run_01", WHEN, "datacontract", {"ran": True})
    finish_runs("run_01", agency=AGENCY, collection=COLLECTION, when=WHEN)

    assert reader.read_one(AGENCY, COLLECTION, "run_01", "datacontract") == []
    assert reader.read_raw(AGENCY, COLLECTION, "run_01", "datacontract")["raw_output"] == {
        "ran": True}


def test_run_by_defaults_to_none_rather_than_a_placeholder(clean_qa_history, finish_runs):
    """Eight of the ten callers leave it unset - only the dataset_stats
    write passes it, since one value per run is all the changelog needs.
    Absent has to read as absent: a placeholder identity in permanent
    history is worse than none, because it looks like an answer."""
    write_qa_result(AGENCY, COLLECTION, "run_01", WHEN, "dbt", {})
    finish_runs("run_01", agency=AGENCY, collection=COLLECTION, when=WHEN,
                run_by="someone@example.com")

    # The run carries the identity its completion supplied; the write
    # itself invented nothing.
    assert reader.read_raw(AGENCY, COLLECTION, "run_01", "dbt")["raw_output"] == {}


def test_re_running_one_tool_replaces_rather_than_doubles(clean_qa_history, finish_runs):
    """Overwriting a file gave this for free. A naive append would turn
    one re-run into two contradictory answers for the same check, with
    nothing to say which was current."""
    first = [{"check_id": "births.id.not_null", "check_name": "id not null",
               "dataset_id": "birth-registrations", "status": "fail", "metric_value": 5.0}]
    second = [{"check_id": "births.id.not_null", "check_name": "id not null",
                "dataset_id": "birth-registrations", "status": "pass", "metric_value": 0.0}]

    write_qa_result(AGENCY, COLLECTION, "run_01", WHEN, "dbt", {"attempt": 1},
                     verified=[dict(r) for r in first])
    write_qa_result(AGENCY, COLLECTION, "run_01", WHEN, "dbt", {"attempt": 2},
                     verified=[dict(r) for r in second])
    finish_runs("run_01", agency=AGENCY, collection=COLLECTION, when=WHEN)

    found = reader.read_one(AGENCY, COLLECTION, "run_01", "dbt")
    assert len(found) == 1, "the re-run added a second answer for the same check"
    assert found[0]["status"] == "pass"
    assert reader.read_raw(AGENCY, COLLECTION, "run_01", "dbt")["raw_output"] == {"attempt": 2}


def test_one_tools_re_run_leaves_another_tools_results_alone(clean_qa_history, finish_runs):
    """The replacement above is scoped to the tool that re-ran. A
    delete-then-insert keyed too broadly would take the rest of the run
    with it, which is the obvious way to implement it wrongly."""
    write_qa_result(AGENCY, COLLECTION, "run_01", WHEN, "soda", {"s": 1},
                     verified=[{"check_id": "a.b", "check_name": "a b",
                                 "dataset_id": "birth-registrations", "status": "pass"}])
    write_qa_result(AGENCY, COLLECTION, "run_01", WHEN, "dbt", {"d": 1},
                     verified=[{"check_id": "c.d", "check_name": "c d",
                                 "dataset_id": "birth-registrations", "status": "pass"}])
    write_qa_result(AGENCY, COLLECTION, "run_01", WHEN, "dbt", {"d": 2},
                     verified=[{"check_id": "c.d", "check_name": "c d",
                                 "dataset_id": "birth-registrations", "status": "fail"}])
    finish_runs("run_01", agency=AGENCY, collection=COLLECTION, when=WHEN)

    assert [r["check_id"] for r in reader.read_one(AGENCY, COLLECTION, "run_01", "soda")] == ["a.b"]
    assert reader.read_raw(AGENCY, COLLECTION, "run_01", "soda")["raw_output"] == {"s": 1}
    assert [r["status"] for r in reader.read_one(AGENCY, COLLECTION, "run_01", "dbt")] == ["fail"]


def test_it_writes_no_files_at_all(clean_qa_history, finish_runs, tmp_path, monkeypatch):
    """REQ-PIPE-089 criterion 8, asserted rather than assumed. The whole
    point of the phase was that results stop being files, and the failure
    mode if a path came back is silent: a tree nobody commits, quietly
    accumulating in whatever directory the process happened to start in.
    """
    monkeypatch.chdir(tmp_path)
    write_qa_result(AGENCY, COLLECTION, "run_01", WHEN, "dbt", {"some": "output"},
                     verified=[{"check_id": "a.b", "check_name": "a b",
                                 "dataset_id": "birth-registrations", "status": "pass"}])
    finish_runs("run_01", agency=AGENCY, collection=COLLECTION, when=WHEN)

    assert list(tmp_path.rglob("*.json")) == []
    assert not (tmp_path / "qa_results").exists()


def test_the_writer_imports_no_filesystem_machinery():
    """Asserted through the import list rather than by grepping the
    source, so a docstring explaining what it no longer does cannot
    satisfy it."""
    import ast
    import inspect

    from qa_tools.common import qa_results_writer

    tree = ast.parse(inspect.getsource(qa_results_writer))
    imported = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            imported.update(a.name for a in node.names)
        elif isinstance(node, ast.ImportFrom):
            imported.add(node.module or "")
    assert "json" not in imported
    assert "pathlib" not in imported
    assert "shutil" not in imported
