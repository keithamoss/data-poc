"""A contested pair, staged and filed as an arrival leaves it - shared by
the settlement's tests (REQ-PIPE-193)."""
from __future__ import annotations

from datetime import date, datetime, timedelta

from qa_tools.common import asset_time, filing, qa_store, settlement, supply_db, supply_files
from qa_tools.common import filing_decisions as fd

DS = "birth-registrations"
TABLE = "birth_registrations"


def free_day(conn, start: date, span: int = 300) -> date:
    """A random day in [start, start+span) where neither it nor the next
    day holds a pair already - a test database keeps every pair the earlier
    tests left, and a re-file into a period holding an open one is refused
    (post-build-review #170). SETTLED pairs count too (#172): a settled
    pair's supplies on the same day can be another test's latest arrival."""
    import random

    from qa_tools.common import dataset_blockers

    taken = set()
    for blocker in dataset_blockers.contests(conn):
        if blocker.dataset_id == DS:
            found = supply_files.resolve(conn, DS, blocker.supply)
            if found is not None and found.period:
                taken.add(found.period)
    for _ in range(200):
        day = start + timedelta(days=random.randrange(span))
        if not {day.isoformat(), (day + timedelta(days=1)).isoformat(),
                (day + timedelta(days=2)).isoformat()} & taken:
            return day
    raise AssertionError("no free day for a pair - the test database is full of them")


def _at(on: date, hhmm: str) -> datetime:
    return asset_time.wall_clock(on, hhmm)


class Pair:
    """One delivery carrying two files for `day`, staged and filed as `#1`
    exactly as an arrival leaves it."""

    def __init__(self, conn, day, files):
        import random

        self.day, self.period = day, day.isoformat()
        # A JITTER OF UNDER A MINUTE, the same for both files - their order
        # and gap are the scenario; it keeps two pairs on one day on one
        # worker's database from sharing a key, a supply id or a table.
        jitter = timedelta(seconds=random.randrange(1, 59),
                           microseconds=random.randrange(1, 999_999))
        self.files = [(name, at + jitter) for name, at in files]
        files = self.files
        first = min(r for _, r in files)
        self.key = asset_time.arrival_key(first)
        self.delivery = f"pytest-choose-{self.key}"
        self.pair = f"{DS}@{self.key}#1"
        self.second = f"{DS}@{self.key}#2"
        conn.execute(f'INSERT INTO "{qa_store.SCHEMA}".delivery (name, received_at, '
                     "received_instant) VALUES (?, ?, ?)", [self.delivery, first.isoformat(), first])
        for n, (name, at) in enumerate(files):
            conn.execute(
                f'INSERT INTO "{qa_store.SCHEMA}".delivery_file (delivery, filename, '
                "dataset_id, received_at, received_instant, received_from, receipt_sequence) "
                "VALUES (?, ?, ?, ?, ?, 'our-clock', ?)",
                [self.delivery, name, DS, at.isoformat(), at, n])
        decided = filing.assignment_at(DS, self.pair, first)
        assert filing.record(decided, self.delivery, conn=conn)
        # THE PERIOD IT IS FILED TO, never the delivery's own day: a daily
        # delivery covers the day before, and a person promotes a supply only
        # into its filed period (post-build-review #173).
        if decided.slot is not None:
            self.period = decided.slot
        conn.execute(f'CREATE SCHEMA IF NOT EXISTS "{supply_db.STAGING_SCHEMA}"')
        ordered = sorted(name for name, _ in files)
        self.table = {}
        for name, _ in files:
            physical = supply_files.staged_name(TABLE, self.key, ordered, name)
            conn.execute(f'CREATE TABLE "{supply_db.STAGING_SCHEMA}"."{physical}" (n int)')
            self.table[name] = physical

    def answers(self, *pairs):
        return tuple(settlement.Answer(*p) for p in pairs)

    def settle(self, conn, actor, *answers, at=None, acknowledged="__accept__"):
        request = fd.Request(operation=fd.CHOOSE_FILE, dataset_id=DS, actor=actor,
                             reason="the supplier sent it twice", period=self.period,
                             supply=self.pair, file_outcomes=self.answers(*answers))
        when = (at or _at(self.day + timedelta(days=1), "11:00")).isoformat()
        if acknowledged == "__accept__":
            acknowledged = fd.consequences(conn, request).key or None
        request = fd.Request(**{**request.__dict__, "acknowledged": acknowledged})
        return fd.apply(request, effective_at=when, conn=conn)


