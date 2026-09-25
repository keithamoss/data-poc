"""mothman supply - the command group REQ-PIPE-057 criterion 17 asks
for, and the behaviour underneath it.

These drive the real commands rather than the functions they call: the
criterion is about what a person can reach, and a test of the library
would pass with the group unregistered.
"""
from __future__ import annotations

from datetime import datetime, timezone

import pytest
from click.testing import CliRunner

from cli.app import cli
from cli.supply import supply_group
from qa_tools.common import delivery

WHEN = datetime(2026, 8, 25, 6, 0, tzinfo=timezone.utc)


@pytest.fixture
def dirs(tmp_path, monkeypatch):
    deliveries, receipts = tmp_path / "deliveries", tmp_path / "receipts"
    deliveries.mkdir(); receipts.mkdir()
    monkeypatch.setattr(delivery, "DELIVERIES_DIR", deliveries)
    monkeypatch.setattr(delivery, "RECEIPTS_DIR", receipts)
    return deliveries, receipts


def _drop(dirs, name, files, when=WHEN, receipt=True):
    deliveries, receipts = dirs
    folder = deliveries / name
    folder.mkdir()
    for filename, body in files.items():
        (folder / filename).write_text(body)
    if receipt:
        delivery.write_receipt(name, when, receipts) if hasattr(delivery, "write_receipt") \
            else (receipts / f"{name}.json").write_text(
                '{"received_at": "%s"}' % when.isoformat())
    return folder


def _run(args):
    return CliRunner().invoke(supply_group, args)


class TestItIsAGroupOfItsOwn:
    def test_supply_is_registered_on_the_real_cli(self):
        """Criterion 17, and it names the group: not folded into
        `pipeline`, whose own docstring calls it not human-facing."""
        result = CliRunner().invoke(cli, ["--help"])
        assert "supply" in result.output

    def test_it_is_not_under_debug_or_pipeline(self):
        for group in ("debug", "pipeline"):
            result = CliRunner().invoke(cli, [group, "--help"])
            assert "deliveries" not in result.output, group


class TestWhatArrived:
    def test_a_recognised_delivery_is_listed_with_what_it_was_placed_as(self, dirs):
        _drop(dirs, "monday", {"cp_clients.csv": "a\n1\n"})
        result = _run(["deliveries"])
        assert result.exit_code == 0, result.output
        assert "monday" in result.output
        assert "child-protection" in result.output

    def test_nothing_present_is_said_in_words_rather_than_an_empty_table(self, dirs):
        """Criterion 16, and a freshly-cloned machine has no data/ at
        all - absence is a state to handle, not a precondition."""
        result = _run(["deliveries"])
        assert result.exit_code == 0
        assert "No deliveries are present" in result.output

    def test_an_unrecognised_artefact_is_flagged_without_failing(self, dirs):
        """Criterion 10: warning, not fatal, and never fatal for the
        delivery it came in."""
        _drop(dirs, "monday", {"cp_clients.csv": "a\n1\n", "covering note.pdf": "%PDF"})
        result = _run(["deliveries"])
        assert result.exit_code == 0
        assert "unrecognised" in result.output

    def test_a_delivery_nothing_can_place_is_reported_not_failed(self, dirs):
        """Criterion 13."""
        _drop(dirs, "mystery", {"notes.pdf": "%PDF"})
        result = _run(["unplaceable"])
        assert result.exit_code == 0
        assert "mystery" in result.output


class TestInFlight:
    def test_a_delivery_with_no_receipt_is_reported_and_not_processed(self, dirs):
        """Criteria 4 and 5. It used to take every other delivery down
        with it, because reading a receipt raised."""
        _drop(dirs, "arrived", {"cp_clients.csv": "a\n1\n"})
        _drop(dirs, "uploading", {"cp_carers.csv": "a\n1\n"}, receipt=False)
        result = _run(["deliveries"])
        assert result.exit_code == 0, result.output
        assert "in flight" in result.output
        assert "uploading" in result.output
        # And the healthy one still processed.
        assert "arrived" in result.output

    def test_it_names_the_files_present_rather_than_counting_them(self, dirs):
        """A count answers "is anything in flight"; the question worth
        asking is "is anything STUCK", and a file list going 2, 4, 6
        across runs reads as an upload progressing."""
        _drop(dirs, "uploading", {"cp_carers.csv": "a\n", "cp_clients.csv": "a\n"},
              receipt=False)
        result = _run(["deliveries"])
        assert "cp_carers.csv" in result.output and "cp_clients.csv" in result.output


class TestANameIsValidatedBeforeAnythingIsOpened:
    def test_a_traversal_attempt_is_refused(self, dirs):
        """A delivery name is supplier-controlled input that becomes a
        path. read_delivery() never validated one, safe only because
        the name always came from iterdir(); taking it as an argument
        closes that loop."""
        result = _run(["deliveries", "--name", "../../etc"])
        assert result.exit_code != 0

    def test_a_name_that_is_simply_absent_says_so(self, dirs):
        _drop(dirs, "monday", {"cp_clients.csv": "a\n1\n"})
        result = _run(["deliveries", "--name", "tuesday"])
        assert result.exit_code != 0
        assert "no delivery named" in result.output


class TestWhichFilenamesEachDatasetClaims:
    def test_it_shows_the_real_declared_patterns(self):
        result = _run(["datasets"])
        assert result.exit_code == 0
        assert "birth-registrations" in result.output
        assert "cp_clients" in result.output
