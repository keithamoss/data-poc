"""Every Child Protection load route attributes a folder's files by arrival
pattern, and a contested table is never checked (REQ-PIPE-202 criteria 8 and
13)."""
from __future__ import annotations

import click
import pytest

import cli.cp as cp
from qa_tools.tools import stage

SIX = {"cp_clients.csv", "cp_notifications.csv", "cp_investigations.csv",
       "cp_placements.csv", "cp_carers.csv", "cp_case_workers.csv"}


def _folder(tmp_path, names):
    for name in names:
        (tmp_path / name).write_text("a\n1\n")
    return str(tmp_path)


@pytest.fixture
def loaded(monkeypatch):
    calls = []
    monkeypatch.setattr(stage, "stage_table",
                        lambda collection_id, run_id, table, path, **kw: calls.append((table, path)))
    return calls


class TestAFolderIsAttributedByPattern:

    def test_a_suffixed_client_register_is_loaded_as_cp_clients(self, tmp_path, loaded):
        names = (SIX - {"cp_clients.csv"}) | {"cp_clients_resend.csv"}
        cp._load_delivery_from_folder(_folder(tmp_path, names), "trial_x")
        tables = dict(loaded)
        assert tables["cp_clients"].endswith("cp_clients_resend.csv")
        assert set(tables) == set(cp.TABLES)

    def test_two_client_register_files_are_refused_and_neither_checked(self, tmp_path, loaded):
        folder = _folder(tmp_path, SIX | {"cp_clients_part2.csv"})
        with pytest.raises(click.ClickException) as got:
            cp._load_delivery_from_folder(folder, "trial_x")
        said = got.value.message
        assert "Client Register" in said or "cp-clients" in said
        assert "cp_clients.csv" in said and "cp_clients_part2.csv" in said
        assert "choose-file" in said or "Filing decisions" in said
        assert loaded == []

    def test_a_missing_table_is_refused_naming_it(self, tmp_path, loaded):
        folder = _folder(tmp_path, SIX - {"cp_carers.csv"})
        with pytest.raises(click.ClickException) as got:
            cp._load_delivery_from_folder(folder, "trial_x")
        assert "cp_carers" in got.value.message or "Carers" in got.value.message
        assert loaded == []

    def test_a_covering_note_is_not_a_table(self, tmp_path, loaded):
        cp._load_delivery_from_folder(_folder(tmp_path, SIX | {"README.txt"}), "trial_x")
        assert len(loaded) == len(cp.TABLES)


class TestThePickerMarksAPair:
    """Criterion 13."""

    def test_listed_marked(self):
        entries = [{"run_id": "cp_run_001", "received_at": "2025-02-01T01:00:00+00:00",
                    "delivery": "d1", "contested": {}},
                   {"run_id": "cp_run_002", "received_at": "2025-05-01T01:00:00+00:00",
                    "delivery": "d2",
                    "contested": {"cp-clients": ["cp_clients.csv", "cp_clients_part2.csv"]}}]
        choices = cp.picker_choices(entries)
        assert "two files for one table" not in choices[0]
        assert choices[1].endswith("two files for one table")
        assert cp.run_id_from_choice(choices[1]) == "cp_run_002"

    def test_picked_it_is_refused_naming_both_files(self, monkeypatch):
        monkeypatch.setattr(cp, "load_manifest", lambda: [
            {"run_id": "cp_run_002", "received_at": "2025-05-01T01:00:00+00:00",
             "delivery": "d2",
             "contested": {"cp-clients": ["cp_clients.csv", "cp_clients_part2.csv"]}}])
        staged = []
        monkeypatch.setattr(stage, "stage_arrival", lambda collection_id, arrival: staged.append(arrival))
        for keep in (True, False):
            with pytest.raises(click.ClickException) as got:
                cp.run_check("cp_run_002", "pytest", keep=keep)
            said = got.value.message
            assert "cp_clients.csv" in said and "cp_clients_part2.csv" in said
        assert staged == []


PAIR_ENTRY = {"run_id": "cp_run_002", "received_at": "2025-05-01T01:00:00+00:00",
              "delivery": "d2",
              "contested": {"cp-clients": ["cp_clients.csv", "cp_clients_part2.csv"]}}


class TestAPickedPairIsRefusedBeforeAnyQuestion:
    """post-build-review #203 F4: criterion 13 refuses a pair's arrival WHEN
    PICKED - before 'keep or trial?' is asked about a check that cannot run."""

    @pytest.fixture
    def never_asked(self, monkeypatch):
        import cli.common as common

        monkeypatch.setattr(cp, "load_manifest", lambda: [PAIR_ENTRY])
        monkeypatch.setattr(cp, "manifest_exists", lambda: True)

        def asked(*a, **kw):
            raise AssertionError("asked keep-or-trial about an arrival it then refused")
        monkeypatch.setattr(common, "decide_record", asked)

    def test_the_run_id_flag(self, never_asked):
        from click.testing import CliRunner

        got = CliRunner().invoke(cp.cp_group, ["qa", "--run-id", "cp_run_002", "--trial"])
        assert got.exit_code != 0
        assert not isinstance(got.exception, AssertionError), got.exception
        assert "cp_clients.csv" in got.output and "cp_clients_part2.csv" in got.output

    def test_the_picker(self, never_asked, monkeypatch):
        import cli.common as common

        monkeypatch.setattr(common, "select",
                            lambda prompt, choices, **kw: choices[0])
        with pytest.raises(click.ClickException) as got:
            cp.run_qa_interactive()
        assert "cp_clients_part2.csv" in got.value.message


class TestThreeFilesAreCounted:
    """post-build-review #203 F6: three files for one table say three."""

    def test_the_count_is_the_files(self, tmp_path, loaded):
        folder = _folder(tmp_path, SIX | {"cp_clients_part2.csv", "cp_clients_part3.csv"})
        with pytest.raises(click.ClickException) as got:
            cp._load_delivery_from_folder(folder, "trial_x")
        assert "has 3 files" in got.value.message


class TestATrialOfAPairIsRefused:
    """Criterion 8 through the trial's own entry point (post-build-review #203
    F1f): a pair in the folder or in the reference folder, nothing loaded."""

    @pytest.mark.parametrize("which", ["folder", "reference"])
    def test_refused_naming_both_and_nothing_loaded(self, tmp_path, loaded, which):
        pair = _folder(tmp_path / "pair", SIX | {"cp_clients_part2.csv"}) if (
            tmp_path / "pair").mkdir() is None else None
        six = _folder(tmp_path / "six", SIX) if (tmp_path / "six").mkdir() is None else None
        folder, reference = (pair, six) if which == "folder" else (six, pair)
        with pytest.raises(click.ClickException) as got:
            cp.run_check_local_folder(folder, reference, "pytest", keep=False)
        assert "cp_clients.csv" in got.value.message
        assert "cp_clients_part2.csv" in got.value.message
        assert loaded == []


class TestTheRefusalSaysWhatToDo:
    """REQ-PIPE-202 criterion 8 as amended (Keith, 2026-10-15): a trial files
    nothing, so its refusal names what the person can do rather than a queue
    the pair never reaches; a recorded arrival is settled in Filing decisions."""

    def test_a_folder_offers_both_ways_out(self, tmp_path, loaded):
        folder = _folder(tmp_path, SIX | {"cp_clients_part2.csv"})
        with pytest.raises(click.ClickException) as got:
            cp._load_delivery_from_folder(folder, "trial_x")
        said = got.value.message
        assert "remove all but one file" in said
        assert "keep the delivery and settle the pair in Filing decisions" in said

    def test_a_recorded_arrival_is_settled_in_filing_decisions(self, tmp_path, loaded):
        folder = _folder(tmp_path, SIX | {"cp_clients_part2.csv"})
        with pytest.raises(click.ClickException) as got:
            cp._load_delivery_from_folder(folder, "cp_run_x", recorded=True)
        said = got.value.message
        assert "settle the pair in Filing decisions" in said
        assert "remove all but one file" not in said
