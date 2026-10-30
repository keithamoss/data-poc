"""What calendar corrections did, embedded for the dashboard (REQ-DASH-172):
the original verdict, the correction and its approver; a kept supply; a
correction awaiting the asset manager; each applied correction once."""
from __future__ import annotations

import pytest

import test_correction_apply as T
from pipeline import corrections
from qa_tools.common import correction_apply, correction_trial

# The confirmation tests' own fixtures, bound by name so pytest finds them.
conn = T.conn
manager = T.manager


@pytest.fixture
def by_supply(monkeypatch):
    """No runs are recorded here, so a supply's run is itself."""
    from pipeline import slot_timeline

    monkeypatch.setattr(slot_timeline, "_run_for", lambda conn, ds, supply: supply)


def _declared(monkeypatch, docs):
    monkeypatch.setattr(correction_trial, "working", lambda: docs)


def test_a_re_judged_supply_carries_original_correction_and_approver(
        conn, manager, by_supply, monkeypatch):
    docs = T._corrected(T._grace)
    _declared(monkeypatch, docs)
    correction_apply.confirm(conn, "CAB-1", actor=manager, effective_at=T.AT, docs=docs)
    got = corrections.for_dataset(T.DATASET, conn)
    [entry] = got["rejudged"][T.SUPPLY]
    assert (entry["original"], entry["new"], entry["reference"]) == ("on_time", "late", "CAB-1")
    assert entry["approver"] and entry["appliedAt"]


def test_a_kept_supply_carries_its_correction_and_reason(conn, manager, by_supply,
                                                         monkeypatch):
    docs = T._corrected(T._move_q3)
    _declared(monkeypatch, docs)
    correction_apply.confirm(conn, "CAB-1", actor=manager, keep={(T.DATASET, T.SUPPLY)},
                             keep_reason="genuinely Q3", effective_at=T.AT, docs=docs)
    # The decision log is shared and append-only, so another test's keep of
    # the same supply may be listed too - this one is the CAB-1 entry.
    [kept] = [k for k in corrections.for_dataset(T.DATASET, conn)["kept"][T.SUPPLY]
              if k["reason"] == "genuinely Q3"]
    assert (kept["reference"], kept["period"]) == ("CAB-1", "2023-Q4")


def test_a_pending_correction_is_awaiting_on_the_datasets_it_affects(conn, by_supply,
                                                                     monkeypatch):
    docs = T._corrected(T._grace)
    _declared(monkeypatch, docs)
    got = corrections.for_dataset(T.DATASET, conn)
    assert [a["reference"] for a in got["awaiting"]] == ["CAB-1"]
    assert corrections.for_dataset("birth-registrations", conn)["awaiting"] == []


def test_each_applied_correction_is_one_activity_entry(conn, manager, by_supply,
                                                       monkeypatch):
    docs = T._corrected(T._move_q3)
    _declared(monkeypatch, docs)
    correction_apply.confirm(conn, "CAB-1", actor=manager, effective_at=T.AT, docs=docs)
    [entry] = corrections.applied_feed(conn)
    assert entry["kind"] == "correction" and entry["reference"] == "CAB-1"
    assert entry["moved"] == 1 and entry["published_at"]


class TestCriticFindingsOn172:
    """delivery-critic on REQ-DASH-172 (post-build-review #149). Each failed
    before its fix."""

    def test_2_a_supply_kept_held_is_listed_though_it_has_no_run(self, conn, manager,
                                                                monkeypatch):
        from qa_tools.common import assignment

        import filing_support
        filing_support.file(assignment.Assignment(
            dataset_id=T.DATASET, supply_id="cp-clients@kh00000001", slot=None,
            branch=assignment.HELD, considered=(), received_at=T.RECEIVED))
        docs = T._corrected(T._move_q3)
        _declared(monkeypatch, docs)
        correction_apply.confirm(conn, "CAB-1", actor=manager,
                                 keep={(T.DATASET, "cp-clients@kh00000001")},
                                 keep_reason="not sure what it is", effective_at=T.AT,
                                 docs=docs)
        got = corrections.for_dataset(T.DATASET, conn)
        [held] = [k for k in got["keptHeld"] if k["supply"] == "cp-clients@kh00000001"]
        assert (held["supply"], held["reference"], held["reason"]) == (
            "cp-clients@kh00000001", "CAB-1", "not sure what it is")

    @pytest.mark.parametrize("reference", ["CHG:42", "CAB 7"])
    def test_4_a_kept_supply_names_its_reference_exactly(self, conn, manager, by_supply,
                                                          monkeypatch, reference):
        docs = T._corrected(T._move_q3, reference=reference)
        _declared(monkeypatch, docs)
        correction_apply.confirm(conn, reference, actor=manager, keep={(T.DATASET, T.SUPPLY)},
                                 keep_reason="genuinely Q3", effective_at=T.AT, docs=docs)
        found = corrections.for_dataset(T.DATASET, conn)["kept"][T.SUPPLY]
        assert [(k["reference"], k["reason"]) for k in found
                if k["reference"] == reference] == [(reference, "genuinely Q3")]

    def test_6_awaiting_that_cannot_be_worked_out_is_said(self, conn, by_supply,
                                                         monkeypatch, capsys):
        def down(*a, **k):
            raise RuntimeError("db down")
        monkeypatch.setattr(correction_apply, "pending", down)
        got = corrections.for_dataset(T.DATASET, conn)
        assert got["awaiting"] == [] and got["awaitingUnknown"] is True
        assert "db down" in capsys.readouterr().out

    def test_7_a_correction_is_never_capped_out_of_the_activity_panel(self, monkeypatch):
        from dashboard import embed_dashboard_data as embed

        many = [{"agency": "a", "dataset": "d", "run_timestamp": f"2026-09-{d:02d}T00:00:00",
                 "run_by": "x", "published_at": f"2026-09-{d:02d}T00:00:00+08:00"}
                for d in range(1, 29)] * 2
        monkeypatch.setattr(embed, "build_changelog", lambda agency, dataset: many)
        monkeypatch.setattr(corrections, "applied_feed", lambda: [
            {"kind": "correction", "reference": "CAB-OLD", "published_at":
             "2020-01-01T00:00:00+08:00"}])
        feed = embed._build_changelog_feed()
        assert [e for e in feed if e.get("kind") == "correction"]

    def test_3_the_pending_item_links_the_datasets_it_names(self, conn, monkeypatch):
        from qa_tools.common import outstanding

        docs = T._corrected(T._grace)
        _declared(monkeypatch, docs)
        [item] = outstanding._from_pending_corrections(conn)
        record = item.as_record()
        assert [a["datasetId"] for a in record["affects"]] == [T.DATASET]
        assert record["affects"][0]["agencyId"] and record["affects"][0]["collectionId"]
        assert "verdict, and the moves" in record["detail"], \
            "the datasets are named by link, not listed as bare ids in the text"


def test_r_a_moved_supply_carries_the_same_note(conn, manager, by_supply, monkeypatch):
    """Keith, 2026-10-11 (morning-report (r)): a supply a correction MOVED
    shows its verdict at the time and where it was moved, as one re-judged in
    place does - and counts in the past-date note."""
    docs = T._corrected(T._move_q3)
    _declared(monkeypatch, docs)
    correction_apply.confirm(conn, "CAB-1", actor=manager, effective_at=T.AT, docs=docs)
    got = corrections.for_dataset(T.DATASET, conn)
    [entry] = [e for e in got["rejudged"].get(T.SUPPLY, []) if e.get("movedTo")]
    assert (entry["movedFrom"], entry["movedTo"], entry["reference"]) == \
        ("2023-Q4", "2023-Q3", "CAB-1")
    assert entry["original"] and entry["approver"] and entry["appliedAt"]


def test_152_3_a_move_carried_out_from_parked_carries_the_moved_note(
        conn, manager, by_supply, monkeypatch):
    """delivery-critic on the parked moves (#152, finding 3)."""
    T._file("p3", "2023-Q4", T.RECEIVED + T.timedelta(minutes=21))
    T._park(conn, "p3", "2023-Q4", "2023-Q3", reference="CAB-1")
    correction_apply.drain_parked(conn, docs=T._docs(), say=lambda _m: None)
    got = corrections.for_dataset(T.DATASET, conn, declared={})
    [entry] = [e for e in got["rejudged"].get("p3", []) if e.get("movedTo")]
    assert (entry["movedFrom"], entry["movedTo"], entry["reference"]) == \
        ("2023-Q4", "2023-Q3", "CAB-1")


def test_152_6_a_keep_while_parked_names_its_correction_exactly(
        conn, manager, by_supply, monkeypatch):
    """Finding 6: a reference holding a space was lost to the prose regex."""
    T._file("p6", "2023-Q4", T.RECEIVED + T.timedelta(minutes=22))
    T._park(conn, "p6", "2023-Q4", "2023-Q3", reference="CHG 12")
    correction_apply.keep_parked(conn, "CHG 12", T.DATASET, "p6", actor=manager,
                                 reason="it stays", effective_at=T.AT)
    [kept] = corrections.for_dataset(T.DATASET, conn, declared={})["kept"]["p6"]
    assert (kept["reference"], kept["reason"]) == ("CHG 12", "it stays")
