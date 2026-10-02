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
        # A REAL RECEIPT, sequence and all (REQ-PIPE-061). Written by
        # hand rather than through write_delivery() because these tests
        # deliberately build odd deliveries that write_delivery()
        # refuses - but the record still has to be one the pipeline can
        # ORDER, or every test here fails on a receipt it invented
        # rather than on the thing it is testing.
        delivery.write_receipts(name, when, receipts, files=list(files))
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


class TestWhatWasActuallyLoaded:
    """REQ-PIPE-060 criteria 12, 16 and 18, at the surface a person
    reaches them through."""

    @pytest.fixture(autouse=True)
    def _log(self, supply_dsn):
        """An empty load log, which since REQ-PIPE-089 means emptying a
        table rather than pointing at a temporary directory."""
        from qa_tools.common import qa_store, supply_db
        with supply_db.connect(label="test-cli-supply") as conn:
            qa_store.ensure_schema(conn)
            conn.execute(f'TRUNCATE "{qa_store.SCHEMA}".load_outcome')
        return None

    def test_load_is_a_subcommand_of_the_supply_group(self):
        """Criterion 12. A test of build_all() would pass with this
        command unregistered, which is not the claim."""
        assert "load" in supply_group.commands
        assert "load" in CliRunner().invoke(cli, ["supply", "--help"]).output

    def test_a_delivery_with_nothing_loaded_shows_as_partial(self, dirs):
        _drop(dirs, "monday", {"cp_clients.csv": "a\n1\n"})
        result = _run(["deliveries"])
        assert result.exit_code == 0, result.output
        assert "0/1" in result.output, (
            "a recognised-but-unstaged delivery must not read the same as a healthy "
            "one - that is the whole of criterion 16")

    def test_a_fully_loaded_delivery_shows_as_complete(self, dirs, _log):
        from qa_tools.common import arrivals, load_log, supply_db
        _drop(dirs, "monday", {"cp_clients.csv": "a\n1\n"})
        found = arrivals.recognise(delivery.survey().received[0])
        for physical in supply_db.expected_tables(found, WHEN).values():
            load_log.record("monday", "cp-clients", physical, load_log.LOADED,
                             WHEN.isoformat())
        result = _run(["deliveries"])
        assert result.exit_code == 0, result.output
        assert "1/1" in result.output

    def test_failures_lists_the_reason_and_says_nothing_when_there_are_none(self, _log):
        from qa_tools.common import load_log

        empty = _run(["failures"])
        assert empty.exit_code == 0 and "No load is currently recorded as failed" in empty.output

        load_log.record("monday", "cp-clients", "cp_clients__2026", load_log.FAILED,
                         WHEN.isoformat(), reason="UnicodeDecodeError: byte 0x9c")
        result = _run(["failures"])
        assert result.exit_code == 0, result.output
        assert "monday" in result.output
        assert "UnicodeDecodeError" in result.output, (
            "the reason IS the record's value - a queue that only says 'one failed' is "
            "a queue nobody drains")

    def test_a_failed_load_does_not_make_the_command_exit_non_zero(self, _log):
        """A supply needing human action is an operational state, not a
        broken tool - the same line every other command in this group
        draws."""
        from qa_tools.common import load_log
        load_log.record("monday", "cp-clients", "cp_clients__2026", load_log.FAILED,
                         WHEN.isoformat(), reason="bad csv")
        assert _run(["failures"]).exit_code == 0


def _timeline(conn, tmp_path, drops):
    """A real arrival history, recognised and recorded the real way.

    TWO DELIVERY FAMILIES, matching how the real suppliers actually
    send: Birth Registrations arrives on its own, and Child Protection
    arrives as all six tables together. That second shape is what
    makes "5 other dataset(s)" the right answer for any one of them,
    and putting all seven in one delivery - which an earlier version
    of this fixture did - quietly made it six.
    """
    from qa_tools.common import arrivals, delivery as delivery_mod, delivery_log

    deliveries, receipts = tmp_path / "hist-deliveries", tmp_path / "hist-receipts"
    cp_files = ("cp_clients.csv", "cp_carers.csv", "cp_case_workers.csv",
                "cp_investigations.csv", "cp_notifications.csv", "cp_placements.csv")
    for n in range(1, drops + 1):
        day = f"2026-03-{n:02d}"
        for name, files in (
                (f"bdm-{n:02d}", {f"birth_registrations_{day}.csv": "a\n1\n"}),
                (f"cp-{n:02d}", {f: "a\n1\n" for f in cp_files})):
            delivery_mod.write_delivery(
                name, files, f"{day}T09:00:00+08:00", deliveries, receipts)
            d = delivery_mod.read_delivery(name, deliveries, receipts)
            delivery_log.record(d, arrivals.recognise(d), conn=conn)


class TestOneDatasetsOwnTimeline:
    """REQ-PIPE-034's own entry point - every new one gets a mothman
    subcommand in the same change."""

    def test_history_is_a_subcommand_of_the_supply_group(self):
        assert "history" in supply_group.commands
        assert "history" in CliRunner().invoke(cli, ["supply", "--help"]).output

    def test_an_unknown_dataset_fails_before_anything_is_read(self):
        result = _run(["history", "--dataset", "not-a-dataset"])
        assert result.exit_code != 0

    def test_it_says_promoted_is_not_tracked_rather_than_leaving_it_blank(
            self, clean_delivery_log, tmp_path):
        """Silence would read as "same as the latest arrival", which is
        the conflation this requirement exists to split.

        IT USED TO READ THE REAL COMMITTED TREE, asserting on its 42
        recorded arrivals. That corpus was state in the repository,
        which REQ-PIPE-089 removes, so the test lays down its own -
        the claim was never about the number.
        """
        _timeline(clean_delivery_log, tmp_path, drops=2)
        result = _run(["history", "--dataset", "birth-registrations", "--limit", "2"])
        assert result.exit_code == 0, result.output
        assert "not tracked yet" in result.output
        assert "2 arrival(s)" in result.output

    def test_it_names_the_datasets_that_shared_a_delivery(
            self, clean_delivery_log, tmp_path):
        _timeline(clean_delivery_log, tmp_path, drops=3)
        result = _run(["history", "--dataset", "cp-clients", "--limit", "3"])
        assert result.exit_code == 0, result.output
        assert "5 other dataset(s)" in result.output, (
            "a whole-collection delivery has to stay distinguishable from several "
            "coincidental arrivals")


class TestReadingTheDecisionLog:
    """`mothman supply decisions` - REQ-PIPE-091 criterion 10, as something
    a person can actually reach.

    A log nobody can read is a log nobody trusts, and criterion 10's
    read-without-write-access property is only meaningful if there is a
    read.
    """

    @pytest.fixture
    def logged(self, supply_dsn):
        """One person's decision and one rule's, in this worker's own
        database."""
        from qa_tools.common import decision_log as dl
        from qa_tools.common import qa_store, supply_db

        with supply_db.connect(label="test-cli-decisions") as conn:
            qa_store.ensure_schema(conn)
            base = dict(agency_id="child-protection-family-support",
                        collection_id="child-protection", dataset_id="cp-clients",
                        action=dl.PROMOTE, to_slot="2026-Q3")
            with dl.apply_decision(conn, dl.Decision(
                    **base, supply="cp_clients__20260801090000000000",
                    actor="keith@example.gov.au", actor_kind=dl.PERSON,
                    effective_at="2026-08-01T09:30:00+08:00")):
                pass
            dl.record_automatic(conn, dl.Decision(
                **{**base, "dataset_id": "cp-carers"},
                supply="cp_carers__20260801090000000000",
                actor="auto-promotion", actor_kind=dl.RULE,
                effective_at="2026-08-01T09:31:00+08:00"))
            yield conn

    def test_it_is_in_the_supply_group(self):
        assert "decisions" in CliRunner().invoke(cli, ["supply", "--help"]).output

    def test_an_empty_log_says_so_rather_than_printing_a_bare_table(self, supply_dsn):
        from qa_tools.common import qa_store, supply_db

        with supply_db.connect(label="test-cli-decisions-empty") as conn:
            qa_store.ensure_schema(conn)
        result = _run(["decisions", "--dataset", "cp-placements"])
        assert result.exit_code == 0, result.output
        assert "No filing decision" in result.output

    def test_it_lists_one_datasets_decisions_and_what_is_promoted(self, logged):
        result = _run(["decisions", "--dataset", "cp-clients"])
        assert result.exit_code == 0, result.output
        assert "promote" in result.output
        assert "Currently promoted" in result.output

    def test_it_distinguishes_a_rule_from_a_person(self, logged):
        """REQ-PIPE-074 criterion 4 reaching a reader. "Promoted by
        auto-promotion" and "promoted by Keith" are different facts.

        THE LIMIT IS RAISED ON PURPOSE. This command shows the newest
        `--limit` decisions, and its default is a display choice for a
        person at a terminal; the claim here is that a rule's entry
        RENDERS as a rule, not that it lands in the first twenty. Other
        test modules on this xdist worker write cp-carers decisions into
        the same database - they have to, because the command validates
        the dataset against the real hierarchy, so an invented id is
        refused - and on 2026-09-29 twenty more of them pushed this
        fixture's one row out of the window. The assertion was right and
        the window was somebody else's.
        """
        result = _run(["decisions", "--dataset", "cp-carers", "--limit", "500"])
        assert result.exit_code == 0, result.output
        assert "rule" in result.output

    def test_the_instant_is_rendered_on_the_assets_clock(self, logged):
        """REQ-DASH-071's display standard, and this is the exact shape it
        exists for: the column stores an INSTANT, so psycopg returns it in
        UTC whatever offset it was written with. Printed raw, a 9:30am
        Perth promotion reads as 1:30am.
        """
        result = _run(["decisions", "--dataset", "cp-clients"])
        assert "9:30am" in result.output, result.output
        assert "1:30am" not in result.output

    def test_an_unknown_dataset_is_refused_before_a_database_is_opened(self, logged):
        result = _run(["decisions", "--dataset", "not-a-dataset"])
        assert result.exit_code != 0
