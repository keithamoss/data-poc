"""Where each supply was filed, recorded once (REQ-PIPE-062), in the
database (REQ-PIPE-104).

The assignment RULE is tested in tests/test_assignment.py, against real
sequences. This covers the record: written once, never re-derived, and
kept strictly apart from whether a slot is FILLED.

THE `filings` FIXTURE IS NOW A CLEAN TABLE rather than a temporary
directory. Every assertion below is the same assertion; what changed is
that isolation comes from this worker's own database instead of from a
path nobody outside the test knew about - which is stronger, because a
test cannot reach the real filings at all rather than being pointed away
from them.
"""
from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone

import pytest

from qa_tools.common import assignment, filing

PERTH = timezone(timedelta(hours=8))


@pytest.fixture
def filings(supply_dsn):
    """An empty filing table for one test.

    Per-test isolation used to come free from `tmp_path`, because each
    test wrote its own little tree. It is a table now and a worker's
    database outlives any one test, so a test reusing a supply id - and
    `cp-clients@2026` is reused all through this module - would otherwise
    see whatever an earlier test filed under it.
    """
    from qa_tools.common import qa_store, supply_db

    with supply_db.connect(label="test-clean-filings") as conn:
        qa_store.ensure_schema(conn)
        conn.execute(f'TRUNCATE "{qa_store.SCHEMA}".filing')
        yield conn


def _assignment(supply_id="cp-clients@2026", slot="2026-Q1",
                 branch=assignment.ON_TIME, dataset_id="cp-clients"):
    return assignment.Assignment(
        dataset_id=dataset_id, supply_id=supply_id, slot=slot, branch=branch,
        considered=(slot,) if slot else ())


class TestWrittenOnceAndNeverReDerived:
    """Criterion 10."""

    def test_a_second_run_leaves_an_existing_filing_alone(self, filings):
        assert filing.record(_assignment()) is True
        before = filing.filing_for("cp-clients", "cp-clients@2026")

        # A later run would derive a DIFFERENT answer, because the slot
        # state has moved on. It must not write.
        again = filing.record(
            _assignment(slot="2026-Q4", branch=assignment.RESUPPLY))
        assert again is False
        assert filing.filing_for("cp-clients", "cp-clients@2026") == before, (
            "re-deriving silently undoes a human's re-file and makes history move "
            "under a reader")

    def test_the_stored_filing_keeps_the_branch_it_was_decided_by(self, filings):
        filing.record(_assignment(branch=assignment.OLDEST_CLAIMABLE))
        stored = filing.filing_for("cp-clients", "cp-clients@2026")
        assert stored["branch"] == assignment.OLDEST_CLAIMABLE
        assert stored["considered"] == ["2026-Q1"], (
            "recomputing this later is NOT equivalent - the slot state it was decided "
            "against has moved on")

    def test_an_unfiled_supply_reads_as_none_rather_than_erroring(self, filings):
        assert filing.filing_for("cp-clients", "never-seen") is None


class TestFiledIsNotFilled:
    """The distinction that keeps the forward cascade out.

    The rejected 14:00 supply in this requirement's own worked example
    IS filed against Monday. If that counted as filling Monday, the
    16:00 resupply would be pushed to Tuesday and every supply after it
    would be off by one, permanently.
    """

    def test_filing_a_supply_does_not_fill_its_slot(self, filings):
        filing.record(_assignment(slot="2026-Q1"))
        assert filing.filings_of("cp-clients")[0]["slot"] == "2026-Q1"
        assert filing.filled_slots("cp-clients") == frozenset(), (
            "only a PROMOTION fills a slot - an arrival does not, a staged supply does "
            "not, and a rejected one certainly does not")

    def test_the_cascade_that_would_follow_if_it_did(self, filings):
        """Run as the real sequence, so the consequence is visible
        rather than argued."""
        from qa_tools.common.schedule import Period
        from qa_tools.common.slots import Slot

        def slot(day):
            due = datetime(2026, 6, day, 12, tzinfo=PERTH)
            return Slot(dataset_id="d", period=Period(name=f"{day:02d}", date=due.date()),
                         due_at=due, grace=timedelta(hours=1),
                         claim_opens_at=due - timedelta(hours=6))

        slots = [slot(d) for d in range(1, 4)]
        at = datetime(2026, 6, 1, 20, tzinfo=PERTH)

        # What the real rule does, with nothing promoted.
        real = assignment.assign("d", "s3", at, slots, filing.filled_slots("d"))
        assert real.slot == "01"

        # What it would do if a FILING counted as a fill.
        wrong = assignment.assign("d", "s3", at, slots, frozenset({"01"}))
        assert wrong.slot == "01" and wrong.branch == assignment.RESUPPLY


class TestADatasetsFilingsAreItsOwn:
    def test_they_are_read_by_dataset_and_never_pick_up_anothers(self, filings):
        filing.record(_assignment(dataset_id="cp-clients", supply_id="cp-clients@1"))
        filing.record(_assignment(dataset_id="cp-carers", supply_id="cp-carers@1"))
        assert len(filing.filings_of("cp-clients")) == 1
        assert len(filing.filings_of("cp-carers")) == 1
        assert filing.filings_of("cp-placements") == []

    def test_a_supply_id_with_odd_characters_survives_intact(self, filings):
        """IT USED TO BE SANITISED, because it became a file path - `@`
        and `#` were replaced to make a usable filename, and the real id
        survived only inside the document. A column takes it as written,
        so there is no second spelling to keep in step."""
        assert filing.record(_assignment(supply_id="cp-clients@2026#2")) is True
        stored = filing.filing_for("cp-clients", "cp-clients@2026#2")
        assert stored is not None
        assert stored["supply_id"] == "cp-clients@2026#2"


class TestFilingRealArrivals:
    """The entry point the orchestrators call, against real arrivals.

    IT BUILDS ITS OWN DELIVERIES rather than reading data/deliveries/,
    and that is not a stylistic preference - it is the difference
    between green and red. data/ is GITIGNORED, so a freshly-cloned CI
    runner has none at all: the first version of these tests read the
    real tree, passed here, and failed on the runner for four
    consecutive pushes with "expected one filing per CP dataset, got
    0". CLAUDE.md records this exact trap, and it was walked into
    anyway.
    """

    @staticmethod
    def _delivery(tmp_path, name, files, when, sequence):
        deliveries, receipts = tmp_path / "deliveries", tmp_path / "receipts"
        folder = deliveries / name
        folder.mkdir(parents=True, exist_ok=True)
        receipts.mkdir(parents=True, exist_ok=True)
        for filename in files:
            (folder / filename).write_text("a\n1\n")
        (receipts / f"{name}.json").write_text(json.dumps(
            {"delivery": name, "received_at": when, "sequence": sequence}))
        return deliveries, receipts

    def _arrivals(self, tmp_path, collection="child-protection", prefix="cp_run_"):
        from qa_tools.common import arrivals

        deliveries, receipts = self._delivery(
            tmp_path, "monday",
            ["cp_clients.csv", "cp_carers.csv", "cp_placements.csv",
             "cp_notifications.csv", "cp_investigations.csv", "cp_case_workers.csv"],
            "2026-02-01T09:00:00+08:00", 1)
        return arrivals.arrivals_for(collection, prefix, deliveries, receipts)

    def test_every_dataset_in_a_delivery_is_filed_separately(self, filings, tmp_path):
        found = self._arrivals(tmp_path)
        assert found, "the fixture must actually produce an arrival, or this proves nothing"
        written = filing.file_arrivals(found)
        assert len(written) == 6, f"expected one filing per CP dataset, got {len(written)}"
        assert len({a.dataset_id for a in written}) == 6
        assert len({a.supply_id for a in written}) == 6, "each dataset needs its own id"

    def test_a_second_pass_files_nothing(self, filings, tmp_path):
        found = self._arrivals(tmp_path)
        assert filing.file_arrivals(found)
        assert filing.file_arrivals(found) == [], (
            "criterion 10 - a supply already filed is left alone on every later run")

    def test_a_red_supply_is_filed_on_the_same_terms(self, filings, tmp_path):
        """Criterion 11. A supply never promoted still carries where it
        was filed - "arrived three weeks late AND was bad" is what
        belongs on the record."""
        from datetime import timedelta

        from qa_tools.common import arrivals
        from qa_tools.common import schedule as schedule_mod

        # THE DATE COMES FROM THE CALENDAR, not from this file. It used
        # to be a hardcoded 2026-02-01, which fell outside the daily
        # calendar the day that calendar was corrected to start when the
        # feed does - and the failure read as "a supply cannot be filed"
        # when the truth was that the fixture described a delivery
        # arriving before Birth Registrations existed. The rule was
        # right; the scenario had rotted.
        day = schedule_mod.calendar("daily").current.effective_from + timedelta(days=3)
        deliveries, receipts = self._delivery(
            tmp_path, "bdm-drop", [f"birth_registrations_{day.isoformat()}.csv"],
            f"{day.isoformat()}T09:00:00+08:00", 1)
        found = arrivals.arrivals_for("civil-registration", "run_", deliveries, receipts)
        assert found, "the fixture must actually produce an arrival"
        written = filing.file_arrivals(found)
        assert written and all(a.slot is not None for a in written), (
            "a supply must be filed before it is checked")


class TestAFilingIsRecordedInTheDatabase:
    """REQ-PIPE-104. The point of building this before REQ-PIPE-062 turns
    recording on: otherwise flipping that switch starts committing state
    to the repository again.

    THERE WAS NOTHING TO MIGRATE, which is why it is its own requirement
    rather than part of REQ-PIPE-089 - `filings/` was code with recording
    switched off, and gitignored.
    """

    def test_the_record_lands_in_the_metadata_schema(self, filings):
        from qa_tools.common import qa_store

        filing.record(_assignment())
        rows = filings.execute(
            f'SELECT dataset_id, supply_id, slot, branch FROM "{qa_store.SCHEMA}".filing '
            "WHERE dataset_id = ?", ["cp-clients"]).fetchall()
        assert rows == [("cp-clients", "cp-clients@2026", "2026-Q1", assignment.ON_TIME)]

    def test_the_slot_and_the_branch_are_real_columns(self, filings):
        """Criterion 1 names four things to record, and the two that get
        ASKED ABOUT - which slot, and why - are columns rather than keys
        inside the document. The rest of the explanation is a document,
        the same call `dataset_stats` made: normalising it would buy a
        migration for every field REQ-PIPE-064/065 add and no query
        anybody runs."""
        from qa_tools.common import qa_store

        columns = {row[0] for row in filings.execute(
            "SELECT column_name FROM information_schema.columns "
            "WHERE table_schema = ? AND table_name = 'filing'",
            [qa_store.SCHEMA]).fetchall()}
        assert {"dataset_id", "supply_id", "slot", "branch", "record"} <= columns

    def test_a_held_supply_is_recorded_with_no_slot_rather_than_not_at_all(self, filings):
        """A held supply with no row is a supply nobody knows about, and
        the queue a person drains is built from these rows."""
        filing.record(_assignment(slot=None, branch=assignment.HELD,
                                   supply_id="cp-clients@held"))
        stored = filing.filing_for("cp-clients", "cp-clients@held")
        assert stored is not None and stored["slot"] is None

    def test_write_once_is_the_primary_key_rather_than_a_convention(self, filings):
        """Criterion 2, and the reason it is the database's job: two
        arrivals for one dataset can be processed by two workers in the
        same fan-out, and check-then-insert is a race with a nice-looking
        shape."""
        import psycopg
        from qa_tools.common import qa_store

        filing.record(_assignment())
        with pytest.raises(psycopg.errors.UniqueViolation):
            filings.execute(
                f'INSERT INTO "{qa_store.SCHEMA}".filing '
                "(dataset_id, supply_id, branch, record) VALUES (?, ?, ?, '{}')",
                ["cp-clients", "cp-clients@2026", assignment.RESUPPLY])

    def test_it_is_NOT_append_only_because_a_person_may_re_file(self, filings):
        """The contrast with `qa.decision`, which IS append-only, and the
        two tables protect different things. Write-once here means the
        RULE never re-derives a filing against a schedule that has moved
        on; a person moving a supply is REQ-PIPE-067, and the verdict has
        to follow it. An append-only trigger would make that impossible.
        """
        filing.record(_assignment())
        moved = filing.refile("cp-clients", "cp-clients@2026", "2026-Q3",
                               refiling_id="dec-1")
        assert moved is not None and moved["slot"] == "2026-Q3"
        assert filing.filing_for("cp-clients", "cp-clients@2026")["slot"] == "2026-Q3"

    def test_a_filing_is_not_a_delivery_record_or_a_qa_verdict(self, filings):
        """Criterion 3. One delivery carries several datasets and each is
        filed separately against its own dataset's schedule, so these
        cannot be one record - asserted as three distinct tables rather
        than by reading the code."""
        from qa_tools.common import qa_store

        tables = {row[0] for row in filings.execute(
            "SELECT table_name FROM information_schema.tables WHERE table_schema = ?",
            [qa_store.SCHEMA]).fetchall()}
        assert {"filing", "delivery", "check_result"} <= tables

    def test_the_dashboards_reader_can_read_filings(self, filings):
        """Criterion 4, both halves: the build CAN read them, and gets no
        access to any schema holding supply rows - which it gets by the
        publisher role being granted USAGE on `qa` and on nothing else."""
        import uuid

        from qa_tools.common import qa_store

        role = f"probe_filing_reader_{uuid.uuid4().hex[:8]}"
        qa_store.ensure_publisher_role(filings, role, password="x")
        try:
            granted = {row[0] for row in filings.execute(
                "SELECT privilege_type FROM information_schema.table_privileges "
                "WHERE table_schema = ? AND table_name = 'filing' AND grantee = ?",
                [qa_store.SCHEMA, role]).fetchall()}
            assert "SELECT" in granted
            schemas = {row[0] for row in filings.execute(
                "SELECT nspname FROM pg_namespace "
                "WHERE has_schema_privilege(?, nspname, 'USAGE') "
                # left(...) rather than NOT LIKE 'pg_%': psycopg reads a
                # bare % in the SQL as a placeholder and refuses it.
                "AND left(nspname, 3) <> 'pg_' AND nspname <> 'information_schema'",
                [role]).fetchall()}
            assert schemas <= {qa_store.SCHEMA}, (
                f"the publisher can reach schemas beyond {qa_store.SCHEMA}: "
                f"{sorted(schemas - {qa_store.SCHEMA})}")
        finally:
            filings.execute(f'REVOKE ALL ON ALL TABLES IN SCHEMA "{qa_store.SCHEMA}" '
                             f'FROM "{role}"')
            filings.execute(f'REVOKE ALL ON SCHEMA "{qa_store.SCHEMA}" FROM "{role}"')
            filings.execute(f'ALTER DEFAULT PRIVILEGES IN SCHEMA "{qa_store.SCHEMA}" '
                             f'REVOKE ALL ON TABLES FROM "{role}"')
            filings.execute(f'DROP ROLE IF EXISTS "{role}"')

    def test_the_path_cannot_quietly_come_back_into_use(self):
        """Criterion 5. Out of the repository AND out of .gitignore - the
        second half is the one that matters, because an ignored path is a
        path somebody's next experiment writes to without noticing."""
        from pathlib import Path

        root = Path(__file__).resolve().parent.parent
        assert not (root / "filings").exists(), "the filings/ tree is back"
        assert "filings/" not in (root / ".gitignore").read_text(), \
            "filings/ is still ignored, so writing to it would be silent"

    def test_no_code_path_writes_a_filing_to_disk(self):
        """Criterion 6, asserted on the module rather than by reading it.
        A path constant or an open() is how one would come back, and it
        would look like a helpful offline fallback."""
        import inspect

        source = inspect.getsource(filing)
        for forbidden in ("FILINGS_DIR", "path_for", "write_text(", "mkdir("):
            assert forbidden not in source, \
                f"{forbidden} is back in filing.py - a filing is a row, not a file"
