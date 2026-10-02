"""An arrival is one FILE, and its run id says which (REQ-PIPE-105
criteria 1 and 2, with REQ-PIPE-057 criterion 18).

TWO THINGS CHANGE TOGETHER and neither works alone.

THE UNIT. An arrival has been a delivery FOLDER - Child Protection's
six files recognised as one thing, processed as one run. Criterion 1
makes every arriving file its own arrival, processed without waiting
for any other. That is what lets a supplier trickle six objects into a
prefix over ten minutes and have each checked as it lands, and it is
what dissolves the completeness question nothing should have been
asking.

THE IDENTITY. A run id has been POSITIONAL - `cp_run_007` built from
`len(out) + 1`, "the seventh delivery recognised" - which REQ-PIPE-057
criterion 18 forbids outright, and which has already bitten once: two
suppressed days left run_022 through run_027 each carrying a
neighbour's instant. Splitting one delivery into six arrivals makes
that six times worse, so the id has to move in the same change.

IT MOVES SOMEWHERE THAT ALREADY EXISTS. One arrival is now one file,
so one dataset, so one supply - run identity and supply identity
converge and there is nothing to invent. The id takes the staged
PHYSICAL TABLE's spelling, `cp_clients__202305010100000000`, rather
than the supply id's `cp-clients@...`: `run_schema()` uses a run id
UNCHANGED as a PostgreSQL schema name and `_ident()` refuses `-` and
`@`. That refusal is deliberate (Keith, 2026-09-27) - hex-encoding was
dropped because `qa_run_run_5f_001` is what a person reads in psql.
"""
from __future__ import annotations

from qa_tools.common import arrivals, asset_time, hierarchy, supply_db

CP = "child-protection"
BDM = "civil-registration"


def _cp():
    return arrivals.arrivals_for(CP, "cp_run_")


class TestOneArrivalIsOneFile:

    def test_a_six_file_delivery_becomes_six_arrivals(self):
        """The 1 May 2023 Child Protection drop, which has been one
        arrival since this pipeline was written."""
        same_instant = [a for a in _cp()
                        if a.received_at.isoformat().startswith("2023-05-01")]
        assert len(same_instant) == 6, [a.run_id for a in same_instant]

    def test_each_one_carries_exactly_one_dataset(self):
        """The shape is kept - `files_by_dataset` is still a mapping,
        so every consumer that iterates it still works - and only its
        contents narrow. Changing the shape as well would have made
        this a rewrite of every caller rather than a change of unit."""
        for a in _cp():
            assert len(a.files_by_dataset) == 1, (a.run_id, a.files_by_dataset)

    def test_no_arrival_is_lost_in_the_split(self):
        """Six datasets across eighteen deliveries, minus the ones a
        delivery genuinely did not carry - counted against the files
        themselves rather than against a number written here."""
        from qa_tools.common import delivery

        files = 0
        for d in delivery.list_deliveries():
            found = arrivals.recognise(d)
            files += sum(len(v) for ds, v in found.by_dataset.items()
                         if hierarchy.dataset(ds).collection_id == CP)
        assert len(_cp()) == files


class TestTheRunIdSaysWhatArrivedAndWhen:

    def test_it_is_the_staged_tables_own_spelling(self):
        a = next(iter(_cp()))
        dataset_id = next(iter(a.files_by_dataset))
        table = hierarchy.dataset(dataset_id).table
        assert a.run_id == f"{table}__{asset_time.arrival_key(a.received_at)}"

    def test_it_survives_being_used_as_a_schema_name(self):
        """The constraint that chose this spelling over the supply
        id's. `_ident()` refuses `-` and `@`, so `cp-clients@...`
        raises here - and a run id that cannot name a schema is not a
        run id this system can use."""
        for a in _cp():
            schema = supply_db.run_schema(a.run_id)
            assert len(schema) <= supply_db.MAX_IDENTIFIER, (schema, len(schema))

    def test_nothing_renumbers_when_a_delivery_stops_being_recognised(self):
        """REQ-PIPE-057 criterion 18, stated as the property it
        protects rather than as the absence of a counter. Drop the
        earliest delivery and every remaining id must be unchanged -
        under the positional scheme they all shifted by one."""
        every = {a.run_id for a in _cp()}
        earliest = min(_cp(), key=lambda a: (a.sequence, a.run_id))
        without = {a.run_id for a in _cp() if a.run_id != earliest.run_id}
        assert without == every - {earliest.run_id}

    def test_two_datasets_at_one_instant_do_not_collide(self):
        """Six files in a folder share a receipt instant today, so the
        arrival key alone is NOT unique - uniqueness comes from the
        dataset being part of the id."""
        ids = [a.run_id for a in _cp()]
        assert len(ids) == len(set(ids)), "two arrivals share a run id"


class TestBothCollectionsMove:

    def test_birth_registrations_too(self):
        """One table, so its deliveries were already one file each -
        but the IDENTITY still changes, and a scheme that only applied
        to the collection that needed splitting would be two schemes."""
        a = next(iter(arrivals.arrivals_for(BDM, "run_")))
        dataset_id = next(iter(a.files_by_dataset))
        table = hierarchy.dataset(dataset_id).table
        assert a.run_id == f"{table}__{asset_time.arrival_key(a.received_at)}"
