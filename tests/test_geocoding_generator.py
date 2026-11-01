"""REQ-GEN-295: the Linkage Products provider's geocoding stream, driven
through the provider's own plan and slot hooks - what the driver writes - and
asserted on the rows each geocoding file is built with.

Planned once for the module: the plan runs every source collection's provider
in memory. The byte-identity of every linkage delivery, receipt and
bookkeeping entry, and of every other collection's, was shown by generating
the whole history before and after the restructure (this requirement's
evidence); REQ-TEST-239's compare of a bootstrap is the end-of-run proof."""
from __future__ import annotations

import re
from datetime import time, timedelta

import pandas as pd
import pytest

from generator.collections import linkage_products as lp
from qa_tools.common import asset_time

pytestmark = pytest.mark.filterwarnings("ignore::UserWarning")

GEO = ("geo-cp-clients", "geo-ed-presentations")


@pytest.fixture(scope="module")
def plan():
    return lp.PROVIDER.plan()


def _geo_jobs(plan):
    return [j for j in plan.jobs if j.stream == lp.GEO_STREAM]


def _files(plan, job):
    found = plan.state["geocoding"][job.slot_id]
    return {} if found is None else found[1]


class TestTheStreams:
    def test_two_streams_each_its_own_datasets(self):
        streams = lp.PROVIDER.streams()
        assert [(s.name, s.dataset_ids) for s in streams] == [
            (lp.LINKAGE_STREAM, ("linkage-keys",)), (lp.GEO_STREAM, GEO)]
        assert lp.PROVIDER.target_datasets == ("linkage-keys", *GEO)
        assert lp.PROVIDER.target_trial is False

    def test_the_geocoding_seeds_lie_in_their_own_range(self):
        lp.PROVIDER.check_seeds()
        geo = [(label, a, b) for label, a, b in lp.PROVIDER.seed_schedule()
               if label.startswith("geo_slot_") or "geocoding" in label]
        assert geo and all(71_000 <= a and b < 72_000 for _l, a, b in geo)
        assert (71_000, 72_000) in lp.PROVIDER.seed_ranges

    def test_every_linkage_job_first_in_todays_order(self, plan):
        streams = [j.stream for j in plan.jobs]
        first_geo = streams.index(lp.GEO_STREAM)
        assert set(streams[:first_geo]) == {lp.LINKAGE_STREAM}
        assert set(streams[first_geo:]) == {lp.GEO_STREAM}
        linkage = plan.jobs[:first_geo]
        assert [j.slot_id for j in linkage] == [f"lp_slot_{i:02d}"
                                                for i in range(1, len(linkage) + 1)]
        assert [j.seed for j in linkage] == [70_000 + i for i in range(1, len(linkage) + 1)]

    def test_entries_are_numbered_within_their_stream(self, plan):
        job = next(j for j in _geo_jobs(plan) if _files(plan, j))
        [entry] = lp.PROVIDER.entries(plan, job, lp.PROVIDER.slot(plan, job), 0)
        assert entry["run_id"].endswith(f"{lp.GEO_STREAM}_001") and entry["run_index"] == 1
        assert set(entry["planned"]) <= set(GEO)
        from qa_tools.common import hierarchy

        assert set(entry["row_counts"]) == {hierarchy.dataset(d).table for d in entry["planned"]}


class TestWhenAndFromWhat:
    def test_one_delivery_of_its_own_on_the_round_after_the_linkage_release(self, plan):
        linkage = {j.period.name: plan.state["arrivals"][j.slot_id][0][0]
                   for j in plan.jobs if j.stream == lp.LINKAGE_STREAM
                   and plan.state["arrivals"][j.slot_id]}
        seen = 0
        for job in _geo_jobs(plan):
            found = plan.state["geocoding"][job.slot_id]
            if found is None:
                continue
            at = found[0]
            local = asset_time.localise(at)
            assert asset_time.local_date(at) == job.period.round_date
            assert time(18, 5) <= local.time() <= time(18, 55), at
            if job.period.name in linkage:
                assert linkage[job.period.name] < at
            seen += 1
        assert seen > 40

    def test_each_file_reads_its_sources_last_supply_received_before_it(self, plan):
        job = next(j for j in _geo_jobs(plan) if "geo_ed_presentations" in _files(plan, j))
        at, files = plan.state["geocoding"][job.slot_id]
        before = [s for s in plan.state["sources"]["ed-presentations"]
                  if s.period == job.period.name
                  and asset_time.parse_instant(s.received_at, "ed") < at]
        ids = set(before[-1].rows["presentation_id"].astype(str))
        assert set(files["geo_ed_presentations"][1]["id_1"]) == ids

    def test_every_quarter_a_source_holds_and_none_after_the_anchor(self, plan):
        from generator.anchor_date import get_anchor_date

        for d, src, _cols in lp.geocoded():
            table = d.replace("-", "_")
            have = {s.period for s in plan.state["sources"][src]}
            written = {j.period.name for j in _geo_jobs(plan) if table in _files(plan, j)}
            assert written == have & {p.name for p in lp.PROVIDER.generated_periods_for(d)}
        assert all(j.period.round_date <= get_anchor_date() for j in _geo_jobs(plan))

    def test_no_client_register_geocode_where_child_protection_is_suppressed(self, plan):
        written = {j.period.name for j in _geo_jobs(plan) if "geo_cp_clients" in _files(plan, j)}
        assert not written & {"2015-Q2", "2015-Q3", "2015-Q4"}
        from qa_tools.common import scripted_decisions

        marks = {s.period for s in scripted_decisions.load()
                 if s.dataset_id == "geo-cp-clients" and s.operation == "mark-not-supplied"}
        assert marks == {"2015-Q2", "2015-Q3", "2015-Q4"}

    def test_the_ed_gap_quarter_has_no_ed_geocode(self, plan):
        written = {j.period.name for j in _geo_jobs(plan)
                   if "geo_ed_presentations" in _files(plan, j)}
        assert "2015-Q4" not in written and "2015-Q3" in written

    def test_both_geocoding_datasets_ride_the_correction(self):
        from generator import scenario_injection

        assert set(GEO) <= set(scenario_injection.CORRECTION_RIDERS["REQ-GEN-205"])


class TestTheRows:
    def test_one_row_per_distinct_record_and_year_in_force(self, plan):
        for job in _geo_jobs(plan):
            for _t, (d, rows, _v) in _files(plan, job).items():
                years = lp.members_in_force(d, job.period)
                assert set(rows["census_year"]) <= set(years)
                per = rows.groupby("id_1")["census_year"].apply(sorted)
                assert all(list(v) == sorted(years) for v in per), (d, job.period.name)

    def test_the_years_widen_with_the_set(self, plan):
        def years(name):
            job = next(j for j in _geo_jobs(plan) if j.period.name == name)
            return sorted(set(_files(plan, job)["geo_ed_presentations"][1]["census_year"]))
        assert years("2017-Q2") == [2011]
        assert years("2017-Q3") == [2011, 2016]
        assert years("2022-Q3") == [2011, 2016, 2021]

    def test_codes_in_their_formats_and_empty_when_not_geocoded(self, plan):
        job = next(j for j in _geo_jobs(plan) if "geo_cp_clients" in _files(plan, j))
        rows = _files(plan, job)["geo_cp_clients"][1]
        placed = rows[rows["match_level"] != "not geocoded"]
        assert placed["sa2_code"].map(lambda c: bool(re.fullmatch(r"5\d{8}", c))).all()
        assert placed["lga_code"].map(lambda c: bool(re.fullmatch(r"5\d{4}", c))).all()
        unplaced = rows[rows["match_level"] == "not geocoded"]
        assert (unplaced["sa2_code"] == "").all() and (unplaced["lga_code"] == "").all()
        assert set(rows["match_level"]) <= {"suburb", "postcode", "not geocoded"}

    def test_a_record_carries_the_same_codes_every_quarter(self, plan):
        # CLIENT RECORDS PERSIST from quarter to quarter; a presentation is new
        # every quarter, so only the Client Register's records repeat.
        jobs = [j for j in _geo_jobs(plan) if "geo_cp_clients" in _files(plan, j)]
        a, b = (_files(plan, j)["geo_cp_clients"][1] for j in jobs[-2:])
        both = a.merge(b, on=["id_1", "census_year"], suffixes=("_a", "_b"))
        placed = both[(both.match_level_a != "not geocoded") & (both.match_level_b != "not geocoded")]
        assert len(placed) and (placed.sa2_code_a == placed.sa2_code_b).all()

    def test_no_identifier_column_beyond_the_sources(self, plan):
        for job in _geo_jobs(plan)[:5]:
            for _t, (_d, rows, _v) in _files(plan, job).items():
                assert (rows["id_2"] == "").all()


class TestGeocodeRowsByConstruction:
    """The row rules on a source supply built by hand."""

    def _source(self):
        return pd.DataFrame({
            "cp_client_id": ["A", "B", "B", None, " ", "C"],
            "suburb": ["Ascot", "", "", "Belmont", "Belmont", None],
            "postcode": ["6104", "6053", "6053", "6104", "6104", None]})

    def test_distinct_records_null_and_blank_identifiers_written_nowhere(self):
        rows = lp.geocode_rows("geo-cp-clients", self._source(), ("cp_client_id",),
                               (2011, 2016), 0.0)
        assert list(rows["id_1"]) == ["A", "A", "B", "B", "C", "C"]
        assert list(rows["census_year"]) == [2011, 2016] * 3

    def test_placed_no_finer_than_the_present_address_columns(self):
        rows = lp.geocode_rows("geo-cp-clients", self._source(), ("cp_client_id",),
                               (2011,), 0.0)
        assert dict(zip(rows["id_1"], rows["match_level"])) == {
            "A": "suburb", "B": "postcode", "C": "not geocoded"}

    def test_the_geocoders_failures_are_whole_records(self):
        source = pd.DataFrame({"presentation_id": [f"P{i}" for i in range(4000)],
                               "postcode": ["6000"] * 4000})
        rows = lp.geocode_rows("geo-ed-presentations", source, ("presentation_id",),
                               (2011, 2016), 0.01)
        per = rows.groupby("id_1")["match_level"].nunique()
        assert (per == 1).all()
        share = (rows.groupby("id_1")["match_level"].first() == "not geocoded").mean()
        assert 0.005 <= share <= 0.015

    def test_the_year_changes_only_the_codes(self):
        assert lp.area_codes("geo-ed-presentations", "P1", 2011) == \
            lp.area_codes("geo-ed-presentations", "P1", 2011)
        assert lp.area_codes("geo-ed-presentations", "P1", 2011) != \
            lp.area_codes("geo-ed-presentations", "P1", 2016)


class TestThePlannedVerdict:
    def test_banded_by_the_share_checks_own_bands(self):
        from qa_tools.common import check_bands

        cat = check_bands.catalogue()

        def rows(n_not, n):
            return pd.DataFrame({"match_level": ["not geocoded"] * n_not + ["postcode"] * (n - n_not)})
        assert lp.planned_verdict("geo-ed-presentations", rows(5, 100), cat) == "green"
        assert lp.planned_verdict("geo-ed-presentations", rows(6, 100), cat) == "amber"
        assert lp.planned_verdict("geo-ed-presentations", rows(11, 100), cat) == "red"
        assert lp.planned_verdict("geo-ed-presentations", rows(0, 0), cat) == "green"

    def test_every_file_records_the_verdict_its_own_rows_plan(self, plan):
        from qa_tools.common import check_bands

        cat = check_bands.catalogue()
        for job in _geo_jobs(plan):
            for _t, (d, rows, verdict) in _files(plan, job).items():
                assert verdict == lp.planned_verdict(d, rows, cat)

    def test_an_ed_supply_missing_addresses_is_planned_amber_not_green(self, plan):
        verdicts = [v for j in _geo_jobs(plan) for _t, (d, _r, v) in _files(plan, j).items()
                    if d == "geo-ed-presentations"]
        assert "amber" in verdicts

    def test_targets_carry_every_planned_verdict_green_included(self, tmp_path):
        import json

        from generator import targets

        book = {"geo-ed-presentations": [{"period": "2017-Q2", "delivery": "d1",
                                          "planned": {"geo-ed-presentations": "amber"}},
                                         {"period": "2017-Q3", "delivery": "d2",
                                          "planned": {"geo-ed-presentations": "green"}}]}
        (tmp_path / "book.json").write_text(json.dumps(book))
        (tmp_path / "placed.json").write_text(json.dumps({"placements": []}))
        built = targets.written(tmp_path / "book.json", tmp_path / "placed.json")
        assert [(b.dataset_id, b.delivery, b.target) for b in built] == [
            ("geo-ed-presentations", "d1", "amber"), ("geo-ed-presentations", "d2", "green")]


def test_two_plans_build_the_same_geocodes(plan):
    again = lp.PROVIDER.plan()
    for job in _geo_jobs(plan):
        a, b = plan.state["geocoding"][job.slot_id], again.state["geocoding"][job.slot_id]
        assert (a is None) == (b is None)
        if a is not None:
            assert a[0] == b[0]
            for t in a[1]:
                assert a[1][t][1].equals(b[1][t][1]) and a[1][t][2] == b[1][t][2]


def test_the_received_window_is_inside_the_due_time_and_grace(plan):
    from qa_tools.common import slots

    job = next(j for j in _geo_jobs(plan) if _files(plan, j))
    at = plan.state["geocoding"][job.slot_id][0]
    for d in (d for _t, (d, _r, _v) in _files(plan, job).items()):
        slot = next(s for s in slots.slots_for_dataset(
            d, until=job.period.round_date + timedelta(days=1)) if s.period.name == job.period.name)
        assert at < slot.due_at
