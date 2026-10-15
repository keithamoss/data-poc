"""Every Child Protection load route attributes a folder's files by arrival
pattern, and a contested table is never checked (REQ-PIPE-202 criteria 8 and
13)."""
from __future__ import annotations

import click
import pytest

import cli.cp as cp
import qa_tools.cp.build_cp_warehouses as build_cp_warehouses

SIX = {"cp_clients.csv", "cp_notifications.csv", "cp_investigations.csv",
       "cp_placements.csv", "cp_carers.csv", "cp_case_workers.csv"}


def _folder(tmp_path, names):
    for name in names:
        (tmp_path / name).write_text("a\n1\n")
    return str(tmp_path)


@pytest.fixture
def loaded(monkeypatch):
    calls = []
    monkeypatch.setattr(build_cp_warehouses, "add_table_to_run",
                        lambda run_id, table, path, **kw: calls.append((table, path)))
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
        monkeypatch.setattr(build_cp_warehouses, "stage_arrival", staged.append)
        for keep in (True, False):
            with pytest.raises(click.ClickException) as got:
                cp.run_check("cp_run_002", "pytest", keep=keep)
            said = got.value.message
            assert "cp_clients.csv" in said and "cp_clients_part2.csv" in said
        assert staged == []
