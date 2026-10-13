"""Ordinary ambers built to land amber by construction (REQ-GEN-184
criteria 4-10, 13, 15; Keith, 2026-10-11).

Birth Registrations: one null-rate rule pushed into its band, rows of a
multiple-birth group never blanked, built at the top of the row-count draw and
never made stale. Child Protection: a few unrecognised client postcodes inside
REQ-QAC-187's band, nothing else of the delivery changed. Both kept out of any
`hold` amber-setting era, the count unchanged. Ordinary reds and cleans are as
drawn.
"""
from __future__ import annotations

from datetime import date

import numpy as np
import pandas as pd
import pytest

from generator import targeting
from generator.daily_batch import generate_daily_batch
from qa_tools.common import check_bands

BDM_ID = "birth-registrations"


@pytest.fixture(scope="module")
def cat():
    return check_bands.catalogue()


@pytest.fixture(scope="module")
def batch():
    return generate_daily_batch(date(2026, 9, 20), seed=1234, n_rows=2049, id_offset=100_000)


def _clients(n=527, seed=7):
    rng = np.random.default_rng(seed)
    valid = ["6007", "6008", "6014", "6018", "6019"]
    return pd.DataFrame({"cp_client_id": np.arange(n),
                         "postcode": rng.choice(valid, size=n),
                         "case_status": rng.choice(["Open", "Closed"], size=n)})


class TestABirthRegistrationsAmber:
    def test_one_null_rate_rule_lands_inside_its_band_clear_of_both_ends(self, batch, cat):
        out = targeting.bdm_amber(batch, seed=3, catalogue=cat)
        [column] = [c for c in batch.columns if not batch[c].equals(out[c])]
        rule = cat.rule("birth-registrations", column, "completeness")
        [(lo, hi)] = rule.amber(len(out))
        assert lo < int(out[column].isna().sum()) < hi

    def test_no_row_count_and_no_twin_is_touched(self, batch, cat):
        """Criteria 5 and 6."""
        out = targeting.bdm_amber(batch, seed=3, catalogue=cat)
        assert len(out) == len(batch)
        twins = batch["is_multiple_birth"].astype(bool)
        pd.testing.assert_frame_equal(out[twins], batch[twins])

    def test_the_same_seed_gives_the_same_rows(self, batch, cat):
        """Criterion 13."""
        pd.testing.assert_frame_equal(targeting.bdm_amber(batch, seed=9, catalogue=cat),
                                      targeting.bdm_amber(batch, seed=9, catalogue=cat))

    def test_no_room_in_any_band_is_refused_loudly(self, batch, cat):
        """Criterion 11."""
        full = batch.copy()
        for column in ("place_of_birth_facility", "registering_parent_1_name",
                       "registering_parent_2_name"):
            full[column] = pd.NA
        with pytest.raises(targeting.TargetError, match="no null-rate rule has room"):
            targeting.bdm_amber(full, seed=1, catalogue=cat)


class TestAChildProtectionAmber:
    def test_a_few_unrecognised_postcodes_inside_the_band(self, cat):
        clients = _clients()
        payload = {"cp_clients": clients, "cp_carers": pd.DataFrame({"carer_id": [1, 2]})}
        out = targeting.cp_amber(payload, seed=4, catalogue=cat)
        bad = out["cp_clients"]["postcode"].isin(targeting.UNRECOGNISED_POSTCODES)
        [(lo, hi)] = cat.rule("cp-clients", "postcode", "conformity").amber(len(clients))
        assert lo < int(bad.sum()) < hi

    def test_nothing_else_of_the_delivery_changes(self, cat):
        """Criterion 8."""
        clients = _clients()
        carers = pd.DataFrame({"carer_id": [1, 2]})
        out = targeting.cp_amber({"cp_clients": clients, "cp_carers": carers}, seed=4,
                                 catalogue=cat)
        assert out["cp_carers"] is carers
        pd.testing.assert_frame_equal(out["cp_clients"].drop(columns="postcode"),
                                      clients.drop(columns="postcode"))

    def test_every_value_is_four_numeric_characters(self):
        """Criterion 7 and REQ-QAC-187's decision: the staged column is a number."""
        assert all(len(v) == 4 and v.isdigit() for v in targeting.UNRECOGNISED_POSTCODES)


class TestOutOfTheHoldEra:
    def test_an_amber_in_the_hold_era_swaps_with_a_clean_period_outside_it(self):
        dates = [date(2026, 8, 30) + pd.Timedelta(days=i).to_pytimedelta() for i in range(8)]
        sevs = [None, None, None, "amber", None, "red", None, None]   # 2026-09-02 is held
        out = targeting.outside_hold(sevs, dates, "birth-registrations",
                                     keep_clean=frozenset({0, 7}))
        assert out.count("amber") == 1 and out.count("red") == 1
        assert out[3] is None and out[out.index("amber")] == "amber"
        assert dates[out.index("amber")] < date(2026, 9, 1) or \
            dates[out.index("amber")] >= date(2026, 9, 10)

    def test_no_clean_period_outside_it_is_refused(self):
        dates = [date(2026, 9, 2), date(2026, 9, 3)]
        with pytest.raises(targeting.TargetError, match="hold era"):
            targeting.outside_hold(["amber", None], dates, "birth-registrations")


class TestTheGeneratedHistory:
    @staticmethod
    def _bdm():
        from generator import generate_runs as g
        from generator.anchor_date import get_anchor_date
        from qa_tools.common import schedule

        periods = schedule.periods_for_dataset(g.DATASET_ID,
                                               until=get_anchor_date())[-g.N_DELIVERIES:]
        _r, by_period, suppressed, _q = g._plan_injections(periods)
        return g, periods, by_period, suppressed, g._ordinary_severities(
            periods, by_period, suppressed)

    def test_birth_registrations_ambers_land_where_they_can_be_generated(self):
        """Criterion 9: none in the hold era, none on a period an injected
        scenario owns or empties, and as many as were drawn."""
        from qa_tools.common import amber_setting, asset_time

        g, periods, by_period, suppressed, sevs = self._bdm()
        drawn = [s for _n, s in g.RUN_PLAN[:len(periods)]]
        assert sevs.count("amber") == drawn.count("amber")
        for p, sev in zip(periods, sevs):
            if sev != "amber":
                continue
            assert p.name not in by_period and p.name not in suppressed, p.name
            setting = amber_setting.resolve(g.DATASET_ID, asset_time.start_of_day(p.date))
            assert setting.value != amber_setting.HOLD, p.date

    def test_child_protection_ambers_avoid_injected_periods(self):
        from generator import generate_cp_runs as cp
        from generator.anchor_date import get_anchor_date
        from qa_tools.common import schedule

        periods = schedule.periods_for_dataset(cp.DATASET_ID,
                                               until=get_anchor_date())[-len(cp.RUN_PLAN):]
        _r, by_period = cp._plan_injections(periods)
        sevs = cp._ordinary_severities(periods, by_period)
        assert sevs.count("amber") == [s for _q, s in cp.RUN_PLAN].count("amber")
        assert not [p.name for p, s in zip(periods, sevs) if s == "amber" and p.name in by_period]

    def test_reds_are_where_they_were_drawn_and_only_ambers_moved(self):
        """Criterion 10."""
        g, periods, by_period, suppressed, sevs = self._bdm()
        drawn = [s for _n, s in g.RUN_PLAN[:len(periods)]]
        # REDS MOVE OUT OF THE SCENARIO STRETCH (REQ-GEN-185), the count
        # unchanged: their resends need ordinary days to land on. A red
        # already clear of it stays where it was drawn.
        claimed = [i for i, p in enumerate(periods) if p.name in by_period
                   or p.name in suppressed or p.name in g._built_green(by_period)]
        stretch = min(claimed) - g.RED_CLEARANCE
        assert sevs.count("red") == drawn.count("red")
        assert all(i < stretch for i, s in enumerate(sevs) if s == "red")
        assert all(sevs[i] == "red" for i, s in enumerate(drawn) if s == "red" and i < stretch)

    def test_an_amber_is_never_made_stale(self, monkeypatch):
        from generator import generate_runs as g

        monkeypatch.setattr(g, "inject_stale_delivery",
                            lambda df, seed: (_ for _ in ()).throw(AssertionError("stale")))
        day = date(2026, 9, 12)
        g.BirthRegistrationsProvider(amber_dates=frozenset({day})).generate(
            day, seed=1, n_rows=50, id_offset=0)

    def test_the_providers_never_reach_the_amber_preset(self, monkeypatch, batch, cat):
        from generator import generate_cp_runs as cp
        from generator import generate_runs as g

        monkeypatch.setattr(g, "apply_birth_registrations_presets",
                            lambda *a, **k: (_ for _ in ()).throw(AssertionError("preset")))
        g.BirthRegistrationsProvider().dirty(batch, "amber", seed=1, previous_row_count=None)
        monkeypatch.setattr(cp.dirty_mod, "apply_cp_clients_presets",
                            lambda *a, **k: (_ for _ in ()).throw(AssertionError("preset")))
        cp.ChildProtectionProvider({}).dirty({"cp_clients": _clients()}, "amber", seed=1,
                                             previous_row_count=None)


class TestTheRealToolsAgree:
    """Criterion 15: through the same trial path `mothman bdm qa --trial`
    uses, recording nothing."""

    def test_a_birth_registrations_amber_warns_and_fails_nothing(self, tmp_path, batch, cat):
        from cli import bdm

        ref = generate_daily_batch(date(2026, 9, 19), seed=1233, n_rows=2049, id_offset=0)
        ref_csv, amb_csv = tmp_path / "ref.csv", tmp_path / "amb.csv"
        ref.to_csv(ref_csv, index=False)
        amber = targeting.bdm_amber(batch, seed=0, catalogue=cat)
        amber.to_csv(amb_csv, index=False)
        results = bdm.run_check_local_file(str(amb_csv), str(ref_csv), "trial:not-recorded",
                                           keep=False)[0]
        statuses = {r["status"] for r in results}
        assert "fail" not in statuses and "warn" in statuses
        [column] = [c for c in batch.columns if not batch[c].equals(amber[c])]
        assert any(r["status"] == "warn" and r.get("column_name") == column for r in results)


class TestAnUnreachableAmberNamesItsPeriod:
    def test_the_chain_names_the_slot_date_and_the_target(self):
        """Criterion 11: '...naming the scenario or ordinary period'."""
        from generator import resupply

        class Provider:
            def generate(self, slot_date, seed, n_rows, id_offset):
                return pd.DataFrame({"x": [1]})

            def dirty(self, payload, severity, seed, previous_row_count):
                raise targeting.TargetError("no null-rate rule has room")

        chain = resupply.run_slot_chain(Provider(), date(2026, 9, 14), seed=1, id_offset=0,
                                        n_rows=1, first_severity="amber",
                                        previous_row_count=None)
        with pytest.raises(targeting.TargetError, match=r"2026-09-14.*amber.*no null-rate"):
            next(chain)


class TestTheCriticsSmallerGaps:
    """post-build-review #154."""

    def test_an_amber_is_trimmed_to_the_size_asked_keeping_every_twin(self, batch, cat):
        out = targeting.bdm_amber(batch, seed=2, catalogue=cat, rows=len(batch) - 40)
        assert len(out) == len(batch) - 40
        twins = batch["is_multiple_birth"].astype(bool)
        assert set(batch.index[twins]) <= set(out.index)

    def test_too_few_single_births_to_blank_is_refused(self, batch, cat):
        few = batch[batch["is_multiple_birth"].astype(bool) | (batch.index < 5)]
        with pytest.raises(targeting.TargetError, match="single-birth rows"):
            targeting.bdm_amber(few, seed=1, catalogue=cat)

    def test_no_postcode_band_is_refused(self, cat):
        with pytest.raises(targeting.TargetError, match="no amber band"):
            targeting.cp_amber({"cp_clients": _clients(n=1)}, seed=1, catalogue=cat)

    def test_too_few_postcodes_to_write_is_refused(self, cat):
        clients = _clients()
        clients.loc[clients.index[3:], "postcode"] = None
        with pytest.raises(targeting.TargetError, match="postcode"):
            targeting.cp_amber({"cp_clients": clients}, seed=1, catalogue=cat)

    def test_an_amber_on_an_injected_period_moves(self):
        dates = [date(2026, 8, 20) + pd.Timedelta(days=i).to_pytimedelta() for i in range(5)]
        out = targeting.outside_hold([None, "amber", None, None, None], dates,
                                     "birth-registrations", keep_clean=frozenset({0}),
                                     unavailable=frozenset({1}))
        assert out == [None, None, "amber", None, None]


# ---- part B: injected targets (criteria 1-5, 11, 12, 15) -----------------

def _nulls(df, column):
    return int(df[column].isna().sum())


class TestATarget:
    def test_only_the_three_verdicts(self):
        with pytest.raises(targeting.TargetError, match="one of green, amber, red"):
            targeting.Target("purple")

    def test_green_names_no_rules(self):
        with pytest.raises(targeting.TargetError, match="green target names no rules"):
            targeting.Target("green", ("place_of_birth_facility.completeness",))


class TestBirthRegistrationsTargets:
    def test_green_brings_every_lever_clear_of_its_first_warning(self, batch, cat):
        """Criterion 4, and the natural parent_2 warning a clean batch carries."""
        out, moved = targeting.bdm_target(batch, targeting.Target("green"), seed=1, catalogue=cat)
        levers, _ = targeting._levers(cat, out)
        for rule in levers:
            x = _nulls(out, rule.column)
            assert not any(c.warns(x, len(out)) or c.fails(x, len(out)) for c in rule.checks), \
                rule.column
        assert any(m["rule"] == "registering_parent_2_name.completeness" for m in moved)

    def test_amber_on_a_named_rule_lands_in_its_band_and_nothing_else_trips(self, batch, cat):
        key = "place_of_birth_facility.completeness"
        out, moved = targeting.bdm_target(batch, targeting.Target("amber", (key,)), seed=2,
                                          catalogue=cat)
        levers, _ = targeting._levers(cat, out)
        for rule in levers:
            x, n = _nulls(out, rule.column), len(out)
            if targeting.rule_key(rule) == key:
                [(lo, hi)] = rule.amber(n)
                assert lo < x < hi
            else:
                assert not any(c.warns(x, n) or c.fails(x, n) for c in rule.checks)
        assert [m for m in moved if m["rule"] == key][0]["to"] == "amber"

    def test_red_on_a_named_rule_fails_it(self, batch, cat):
        key = "registering_parent_1_name.completeness"
        out, _ = targeting.bdm_target(batch, targeting.Target("red", (key,)), seed=3,
                                      catalogue=cat)
        [rule] = [r for r in targeting._levers(cat, out)[0] if targeting.rule_key(r) == key]
        assert any(c.fails(_nulls(out, rule.column), len(out)) for c in rule.checks)

    def test_twins_are_never_touched_and_the_size_is_as_asked(self, batch, cat):
        """Criteria 4 and 5."""
        out, _ = targeting.bdm_target(batch, targeting.Target("amber"), seed=4, catalogue=cat,
                                      rows=len(batch) - 30)
        assert len(out) == len(batch) - 30
        twins = batch["is_multiple_birth"].astype(bool)
        pd.testing.assert_frame_equal(out.loc[batch.index[twins]], batch[twins])

    def test_a_rule_with_no_amber_band_is_refused_naming_what_closes_it(self, batch, cat):
        """Criterion 11."""
        with pytest.raises(targeting.TargetError, match="sex.*cannot be built"):
            targeting.bdm_target(batch, targeting.Target("amber", ("sex.conformity",)),
                                 seed=1, catalogue=cat, where="TS-99")

    def test_a_column_another_single_tier_check_reads_is_not_a_lever(self, batch, cat):
        """Criterion 5: a SQL check joining on the column makes it untouchable."""
        import dataclasses

        from qa_tools.common import check_bands as cb
        reader = cb.Check("a.b.c.birth-registrations.date_of_birth.join_soda", "soda",
                          BDM_ID, "date_of_birth", "consistency", "failed_rows", "f",
                          fail=(cb.Bound(">", 0, cb.ROWS),),
                          reads_columns=("birth_registrations.place_of_birth_facility",))
        poisoned = dataclasses.replace(cat, checks=[*cat.checks, reader])
        with pytest.raises(targeting.TargetError, match="join_soda"):
            targeting.bdm_target(batch, targeting.Target(
                "amber", ("place_of_birth_facility.completeness",)), seed=1, catalogue=poisoned)

    def test_the_same_seed_gives_the_same_rows(self, batch, cat):
        """Criterion 13."""
        t = targeting.Target("amber")
        a, _ = targeting.bdm_target(batch, t, seed=5, catalogue=cat)
        b, _ = targeting.bdm_target(batch, t, seed=5, catalogue=cat)
        pd.testing.assert_frame_equal(a, b)

    def test_what_was_moved_carries_no_row_data(self, batch, cat):
        """REQ-GEN-045 NFR 1: a rule and a count, never a value."""
        _out, moved = targeting.bdm_target(batch, targeting.Target("amber"), seed=6,
                                           catalogue=cat)
        assert moved and all(set(m) <= {"rule", "to", "nulls", "of_rows", "was"} for m in moved)


class TestChildProtectionTargets:
    def test_red_is_refused_naming_why(self, cat):
        with pytest.raises(targeting.TargetError, match="no lever"):
            targeting.cp_target({"cp_clients": _clients()}, targeting.Target("red"), seed=1,
                                catalogue=cat)

    def test_amber_is_the_postcode_lever(self, cat):
        out, moved = targeting.cp_target({"cp_clients": _clients()},
                                         targeting.Target("amber"), seed=1, catalogue=cat)
        assert moved[0]["rule"] == "postcode.conformity" and moved[0]["values"] > 0


class TestTargetsAgainstTheRealTools:
    """Criterion 15: an amber and a green target on Birth Registrations,
    through the trial path `mothman bdm qa --trial` uses, recording nothing."""

    def _run(self, tmp_path, df):
        from cli import bdm

        ref = generate_daily_batch(date(2026, 9, 19), seed=1233, n_rows=2049, id_offset=0)
        ref_csv, csv = tmp_path / "ref.csv", tmp_path / "supply.csv"
        ref.to_csv(ref_csv, index=False)
        df.to_csv(csv, index=False)
        return bdm.run_check_local_file(str(csv), str(ref_csv), "trial:not-recorded",
                                        keep=False)[0]

    def test_a_green_target_passes_everything(self, tmp_path, batch, cat):
        out, _ = targeting.bdm_target(batch, targeting.Target("green"), seed=7, catalogue=cat)
        results = self._run(tmp_path, out)
        assert [r["check_id"] for r in results if r["status"] != "pass"] == []

    def test_an_amber_target_warns_on_its_rule_alone(self, tmp_path, batch, cat):
        key = "registering_parent_1_name.completeness"
        out, _ = targeting.bdm_target(batch, targeting.Target("amber", (key,)), seed=8,
                                      catalogue=cat)
        results = self._run(tmp_path, out)
        off = [r for r in results if r["status"] != "pass"]
        assert off and all(r["status"] == "warn" for r in off), off
        assert all(".registering_parent_1_name." in r["check_id"] for r in off), off


class TestAnInjectedTargetEndToEnd:
    """Criteria 1, 4 and 12 through the real generator: an injected
    arrival naming a target is built to it, at the size of the supply
    before it, and the placement records what was moved for the map."""

    KEY = "place_of_birth_facility.completeness"

    @pytest.fixture(scope="class")
    def generated(self, tmp_path_factory):
        import json

        from generator import generate_runs as g
        from generator import scenario_injection as si
        from generator.output import redirect

        root = tmp_path_factory.mktemp("targeted")
        # THE ORDINARY PLAN IS DRAWN ALL CLEAN HERE: the real history is
        # sized for its own scenarios, and a test injection that claims more
        # leaves its ordinary ambers and reds nowhere to go - which the
        # generator refuses, correctly. This tests the injection, not them.
        drawn = g.RUN_PLAN
        g.RUN_PLAN = [(n, None) for n, _sev in drawn]
        extra = si.Injection(
            scenario_id="TS-TARGET", dataset_id=g.DATASET_ID, anchor=-52,
            config="a test injection",
            arrivals=(si.ExtraArrival(0, "14:00", target=targeting.Target("amber", (self.KEY,)),
                                      note="built to amber"),))
        original = si.INJECTIONS
        si.INJECTIONS = (*original, extra)
        restore = redirect(g, root)
        try:
            g.main()
            book = json.loads(g.BOOKKEEPING_PATH.read_text())[g.DATASET_ID]
            placements = json.loads(si.PLACEMENTS_PATH.read_text())
            deliveries = g.DELIVERIES_DIR
        finally:
            restore()
            si.INJECTIONS = original
            g.RUN_PLAN = drawn
        return book, placements, deliveries

    def _record(self, placements):
        records = placements if isinstance(placements, list) else placements.get(
            "placements", placements)
        if isinstance(records, dict):
            records = list(records.values())
        [r] = [r for r in records if r.get("scenario_id") == "TS-TARGET"]
        return r

    def test_the_supply_is_amber_on_the_named_rule_at_the_size_before_it(self, generated, cat):
        book, placements, deliveries = generated
        record = self._record(placements)
        ordered = sorted(book, key=lambda e: e["run_index"])
        [mine] = [e for e in ordered if e["delivery"] == record_delivery(record, book)]
        before = ordered[ordered.index(mine) - 1]
        [csv] = list((deliveries / mine["delivery"]).glob("*.csv"))
        df = pd.read_csv(csv)
        assert len(df) == before["n_rows_generated"]
        [(lo, hi)] = cat.rule(BDM_ID, "place_of_birth_facility", "completeness").amber(len(df))
        assert lo < int(df["place_of_birth_facility"].isna().sum()) < hi

    def test_the_placement_records_the_target_and_what_moved(self, generated):
        _book, placements, _d = generated
        [target] = self._record(placements)["targets"]
        assert target["built_to"] == "amber" and target["rules"] == [self.KEY]
        assert any(m["rule"] == self.KEY and m["to"] == "amber" for m in target["moved"])
        assert "verdict" not in {k for m in target["moved"] for k in m}

    def test_the_scenario_map_says_what_it_was_built_to(self, generated):
        from qa_tools.common import scenario_map

        [target] = self._record(generated[1])["targets"]
        text = scenario_map._target_text(target)
        assert text.startswith(f"amber on {self.KEY} (") and "14:00 arrival" in text


def record_delivery(record, book):
    """The delivery the placement's targeted arrival went into."""
    dates = {t["date"] for t in record["targets"]}
    [entry] = [e for e in book if e["period"] == record["period"]
               and e["received_at"][:10] in dates]
    return entry["delivery"]


class TestATargetReplacesTheSeverity:
    def test_naming_both_is_refused(self):
        from generator import scenario_injection as si

        with pytest.raises(si.CannotPlace, match="one or the other"):
            si.ExtraArrival(0, "14:00", severity="red", target=targeting.Target("amber"))


class TestRefusedBeforeAnythingIsWritten:
    """Criterion 11: '...SHALL NOT emit the history' - a target naming a rule
    that cannot be moved stops generation before the first write."""

    def test_an_unmovable_rule_stops_the_generator_with_nothing_written(self, tmp_path):
        from generator import generate_runs as g
        from generator import scenario_injection as si
        from generator.output import redirect

        bad = si.Injection(
            scenario_id="TS-BAD", dataset_id=g.DATASET_ID, anchor=-52, config="test",
            arrivals=(si.ExtraArrival(0, "14:00", target=targeting.Target(
                "amber", ("sex.conformity",))),))
        original = si.INJECTIONS
        si.INJECTIONS = (*original, bad)
        restore = redirect(g, tmp_path)
        try:
            # A HISTORY ALREADY ON DISK SURVIVES THE REFUSAL: refused before
            # the old one is cleared, not after.
            si.INJECTIONS = original
            g.main()
            before = sorted(p.name for p in (tmp_path / "deliveries").iterdir())
            si.INJECTIONS = (*original, bad)
            with pytest.raises(targeting.TargetError, match="TS-BAD.*sex.conformity"):
                g.main()
            assert sorted(p.name for p in (tmp_path / "deliveries").iterdir()) == before
        finally:
            restore()
            si.INJECTIONS = original

    def test_child_protection_red_is_refused_up_front_too(self):
        from generator import generate_cp_runs as cp
        from generator import scenario_injection as si
        from generator.anchor_date import get_anchor_date
        from qa_tools.common import schedule

        bad = si.Injection(
            scenario_id="TS-CPRED", dataset_id="cp-clients", anchor=-10, config="test",
            arrivals=(si.ExtraArrival(0, "14:00", target=targeting.Target("red")),))
        original = si.INJECTIONS
        # ALONE: the refusal is the point, not where the planted ones sit.
        si.INJECTIONS = (bad,)
        try:
            periods = schedule.periods_for_dataset(cp.DATASET_ID,
                                                   until=get_anchor_date())[-len(cp.RUN_PLAN):]
            with pytest.raises(targeting.TargetError, match="TS-CPRED.*lead-in"):
                cp._plan_injections(periods)
        finally:
            si.INJECTIONS = original


# ---- post-build-review #155: the critic's findings on part B, each failing first ----

def _unmatched_twins(df):
    twins = df[df["is_multiple_birth"].astype(bool)]
    keys = ["date_of_birth", "place_of_birth_facility", "registering_parent_1_name"]
    sizes = twins.fillna({k: "<null>" for k in keys}).groupby(keys)["registration_number"] \
        .transform("count")
    return int((sizes < 2).sum())


class TestFindings155:
    def test_a_targeted_resend_keeps_every_twin(self):
        """Finding 1: the resend is churned before it is targeted."""
        from generator import generate_runs as g
        from generator import scenario_injection as si

        inj = si.Injection(scenario_id="TS-X", dataset_id=g.DATASET_ID, anchor=-20,
                           config="t", arrivals=(
                               si.ExtraArrival(0, "14:00", target=targeting.Target("amber")),
                               si.ExtraArrival(0, "16:00", target=targeting.Target("green"))))
        period = type("P", (), {"date": date(2026, 9, 3), "name": "2026-09-03"})()
        for seed in range(8):
            # A targeted period is never made stale (main() puts it in
            # amber_dates), and a stale batch splits twins by design.
            provider = g.BirthRegistrationsProvider(amber_dates=frozenset({period.date}))
            out = g._injected_chain(provider, inj, period, 1000 + seed, 0, 2000, 2050)
            assert [_unmatched_twins(d.payload) for d in out] == [0, 0], seed

    def test_the_twin_flag_is_never_a_lever(self, batch, cat):
        """Finding 2: blanking it crashed mid-generation."""
        with pytest.raises(targeting.TargetError, match="is_multiple_birth"):
            targeting.check_target(targeting.Target("red", ("is_multiple_birth.completeness",)),
                                   BDM_ID, "TS-X")
        for seed in range(40):
            targeting.bdm_target(batch, targeting.Target("red"), seed=seed, catalogue=cat)

    def test_a_uniqueness_check_on_the_column_takes_it_away(self, batch, cat):
        """Finding 3: a fill draws from the column's own values, which a
        uniqueness check fails."""
        import dataclasses

        from qa_tools.common import check_bands as cb
        uniq = cb.Check("a.b.c.birth-registrations.place_of_birth_facility.unique_x_dbt",
                        "dbt", BDM_ID, "place_of_birth_facility", "uniqueness", "unique", "f",
                        fail=(cb.Bound(">", 0, cb.ROWS),))
        poisoned = dataclasses.replace(cat, checks=[*cat.checks, uniq])
        with pytest.raises(targeting.TargetError, match="unique_x_dbt"):
            targeting.bdm_target(batch, targeting.Target(
                "amber", ("place_of_birth_facility.completeness",)), seed=1, catalogue=poisoned)

    def test_a_same_column_check_reading_other_columns_takes_it_away(self, batch, cat):
        import dataclasses

        from qa_tools.common import check_bands as cb
        cross = cb.Check("a.b.c.birth-registrations.place_of_birth_facility.ordering_x_soda",
                         "soda", BDM_ID, "place_of_birth_facility", "consistency",
                         "failed_rows", "f", fail=(cb.Bound(">", 0, cb.ROWS),),
                         reads_columns=("birth_registrations.place_of_birth_facility",
                                        "birth_registrations.date_registered"))
        poisoned = dataclasses.replace(cat, checks=[*cat.checks, cross])
        with pytest.raises(targeting.TargetError, match="ordering_x_soda"):
            targeting.bdm_target(batch, targeting.Target(
                "amber", ("place_of_birth_facility.completeness",)), seed=1, catalogue=poisoned)

    def test_green_leaves_every_lever_a_margin(self, batch, cat):
        """Finding 6: 550 nulls against dbt's > 550 passed with none."""
        edge = batch.copy()
        singles = edge.index[~edge["is_multiple_birth"].astype(bool)]
        edge["registering_parent_2_name"] = "Someone"
        edge.loc[singles[:550], "registering_parent_2_name"] = pd.NA
        out, _ = targeting.bdm_target(edge, targeting.Target("green"), seed=1, catalogue=cat)
        for rule in targeting._levers(cat, out)[0]:
            trip = targeting._first(rule, len(out), lambda c, x, r: c.warns(x, r) or c.fails(x, r))
            if trip:
                assert _nulls(out, rule.column) <= (trip - 1) * 9 // 10, rule.column

    def test_the_record_says_built_to_and_was_is_the_original_count(self, batch, cat):
        """Finding 7: never a key called `verdict`."""
        t = targeting.Target("amber", ("registering_parent_2_name.completeness",))
        assert "verdict" not in t.as_record() and t.as_record()["built_to"] == "amber"
        _out, moved = targeting.bdm_target(batch, t, seed=1, catalogue=cat)
        [m] = [m for m in moved if m["rule"] == "registering_parent_2_name.completeness"]
        assert m["was"] == _nulls(batch, "registering_parent_2_name")

    def test_an_ordinary_amber_refusal_leaves_the_last_history_standing(self, tmp_path,
                                                                        monkeypatch):
        """Finding 5."""
        from generator import generate_runs as g
        from generator.output import redirect

        restore = redirect(g, tmp_path)
        try:
            g.main()
            before = sorted(p.name for p in (tmp_path / "deliveries").iterdir())

            def refuse(*a, **k):
                raise targeting.TargetError("refused")
            monkeypatch.setattr(targeting, "outside_hold", refuse)
            with pytest.raises(targeting.TargetError):
                g.main()
            assert sorted(p.name for p in (tmp_path / "deliveries").iterdir()) == before
        finally:
            restore()


# ---- REQ-GEN-185: lead-ins and the period after --------------------------

class TestLeadIns:
    def _periods(self, n=10):
        from datetime import timedelta
        start = date(2026, 9, 1)
        return [type("P", (), {"date": start + timedelta(days=i),
                               "name": (start + timedelta(days=i)).isoformat()})()
                for i in range(n)]

    def _inj(self, sid="TS-X", anchor=5, lead_in=2, target=True):
        from generator import scenario_injection as si
        return si.Injection(scenario_id=sid, dataset_id=BDM_ID, anchor=anchor, config="t",
                            lead_in=lead_in, arrivals=(si.ExtraArrival(
                                0, "14:00",
                                target=targeting.Target("amber") if target else None),))

    def test_a_targeted_anchor_claims_its_lead_in_and_the_period_after(self):
        """Criteria 1 and 3, and the default of two."""
        from generator import scenario_injection as si
        pl = si.resolve(self._inj(), self._periods())
        assert pl.lead_in == ("2026-09-04", "2026-09-05") and pl.follow == ("2026-09-07",)

    def test_the_lead_in_is_configurable(self):
        from generator import scenario_injection as si
        assert si.resolve(self._inj(lead_in=1), self._periods()).lead_in == ("2026-09-05",)

    def test_an_untargeted_scenario_claims_neither(self):
        from generator import scenario_injection as si
        pl = si.resolve(self._inj(target=False), self._periods())
        assert pl.lead_in == () and pl.follow == ()

    def test_a_lead_in_before_the_history_is_refused(self):
        from generator import scenario_injection as si
        with pytest.raises(si.CannotPlace, match="lead-in"):
            si.resolve(self._inj(anchor=1), self._periods())

    def test_another_scenario_on_a_lead_in_fails_naming_both(self):
        """Criterion 5."""
        from generator import scenario_injection as si
        other = self._inj(sid="TS-Y", anchor=4, target=False)
        with pytest.raises(si.CannotPlace, match="TS-(X|Y).*TS-(X|Y)"):
            si.no_two_scenarios_share_a_period([self._inj(), other],
                                               {BDM_ID: self._periods()})

    def test_a_suppressed_day_on_the_following_period_fails_too(self):
        from generator import scenario_injection as si
        other = si.Injection(scenario_id="TS-Y", dataset_id=BDM_ID, anchor=8, config="t",
                             suppress=(-2,))
        with pytest.raises(si.CannotPlace, match="TS-(X|Y).*TS-(X|Y)"):
            si.no_two_scenarios_share_a_period([self._inj(), other],
                                               {BDM_ID: self._periods()})


class TestLeadInsEndToEnd:
    """Criteria 1-4 through the real generator: two green lead-ins, a
    targeted anchor with a churned green resend, and a green period after,
    all measured against what the generator built."""

    @pytest.fixture(scope="class")
    def generated(self, tmp_path_factory):
        import json

        from generator import generate_runs as g
        from generator import scenario_injection as si
        from generator.output import redirect

        root = tmp_path_factory.mktemp("leadin")
        # THE ORDINARY PLAN IS DRAWN ALL CLEAN HERE: the real history is
        # sized for its own scenarios, and a test injection that claims more
        # leaves its ordinary ambers and reds nowhere to go - which the
        # generator refuses, correctly. This tests the injection, not them.
        drawn = g.RUN_PLAN
        g.RUN_PLAN = [(n, None) for n, _sev in drawn]
        extra = si.Injection(
            scenario_id="TS-LEAD", dataset_id=g.DATASET_ID, anchor=-52, config="a test",
            arrivals=(si.ExtraArrival(0, "14:00", target=targeting.Target("amber")),
                      si.ExtraArrival(0, "16:00", target=targeting.Target("green"))))
        original = si.INJECTIONS
        si.INJECTIONS = (*original, extra)
        restore = redirect(g, root)
        try:
            g.main()
            book = json.loads(g.BOOKKEEPING_PATH.read_text())[g.DATASET_ID]
            records = json.loads(si.PLACEMENTS_PATH.read_text())
            deliveries = g.DELIVERIES_DIR
        finally:
            restore()
            si.INJECTIONS = original
            g.RUN_PLAN = drawn
        if isinstance(records, dict):
            records = records.get("placements", records)
        if isinstance(records, dict):
            records = list(records.values())
        [record] = [r for r in records if r["scenario_id"] == "TS-LEAD"]
        return book, record, deliveries

    def _rows(self, deliveries, entry):
        [csv] = list((deliveries / entry["delivery"]).glob("*.csv"))
        return pd.read_csv(csv)

    def test_each_lead_in_and_the_period_after_is_one_on_time_green_supply(self, generated):
        book, record, deliveries = generated
        for name in (*record["lead_in"], *record["follow"]):
            mine = [e for e in book if e["period"] == name]
            assert len(mine) == 1 and mine[0]["dirty_severity"] is None, name
            # ON TIME, which the old assertion never checked (post-build-
            # review #156: 09-16 arrived 16:55 and was recorded late).
            from qa_tools.common import asset_time, slots
            due = slots.slot_instants(BDM_ID, date.fromisoformat(name))
            got = asset_time.parse_instant(mine[0]["received_at"], "received_at")
            assert due.due_at <= got <= due.due_at + due.grace, (name, got)
            assert _unmatched_twins(self._rows(deliveries, mine[0])) == 0

    def test_the_targeted_supplies_are_the_size_of_the_last_lead_in(self, generated):
        """Criteria 2 and 4: the resend too, though churned."""
        book, record, _d = generated
        [lead] = [e for e in book if e["period"] == record["lead_in"][-1]]
        anchor = [e for e in book if e["period"] == record["period"]]
        assert len(anchor) == 2
        assert {e["n_rows_generated"] for e in anchor} == {lead["n_rows_generated"]}

    def test_the_period_after_is_the_same_size(self, generated):
        """Criterion 3: no compounding into the next supply."""
        book, record, _d = generated
        [lead] = [e for e in book if e["period"] == record["lead_in"][-1]]
        [after] = [e for e in book if e["period"] == record["follow"][0]]
        assert after["n_rows_generated"] == lead["n_rows_generated"]

    def test_no_other_periods_arrival_lands_on_a_lead_in(self, generated):
        book, record, _d = generated
        for name in record["lead_in"]:
            landed = [e for e in book if e["received_at"][:10] == name and e["period"] != name]
            assert not landed, name



# ---- post-build-review #156: REQ-GEN-185's untested refusals and eras ----

class TestRefusals156:
    def test_a_red_with_nowhere_before_the_scenarios_is_refused(self):
        from generator import generate_runs as g
        with pytest.raises(targeting.TargetError, match="ordinary red"):
            g._reds_clear_of_scenarios([None, "red", "red", None, None],
                                       frozenset({4}))

    def test_with_nothing_claimed_reds_stay_where_drawn(self):
        from generator import generate_runs as g
        drawn = [None, "red", None, "red", None]
        assert g._reds_clear_of_scenarios(drawn, frozenset()) == drawn

    def test_a_resend_pushed_past_the_history_is_refused(self):
        from datetime import timedelta

        from generator import generate_runs as g
        from generator import scenario_injection as si
        from generator.resupply import Delivery
        last = date(2026, 9, 22)
        d = Delivery(received_date=last, severity=None, payload=None)
        with pytest.raises(si.CannotPlace, match="after the history ends"):
            g._away_from_suppressed([d], {last.isoformat(),
                                          (last + timedelta(days=1)).isoformat()},
                                    set(), last_day=last)

    def test_a_targeted_anchor_at_the_history_end_is_refused(self):
        from generator import scenario_injection as si
        periods = TestLeadIns()._periods(6)
        with pytest.raises(si.CannotPlace, match="history ends there"):
            si.resolve(TestLeadIns()._inj(anchor=5), periods)

    def test_a_scenario_suppressing_its_own_lead_in_is_refused(self):
        """Edge the critic found: the shared-period check skips a scenario's
        own keys, so the lead-in would silently go missing."""
        from generator import scenario_injection as si
        inj = si.Injection(scenario_id="TS-X", dataset_id=BDM_ID, anchor=5, config="t",
                           suppress=(-1,), arrivals=(si.ExtraArrival(
                               0, "14:00", target=targeting.Target("amber")),))
        with pytest.raises(si.CannotPlace, match="its own lead-in"):
            si.no_two_scenarios_share_a_period([inj], {BDM_ID: TestLeadIns()._periods()})

    def test_a_child_protection_targeted_injection_is_refused_up_front(self):
        """Lead-ins are built for Birth Registrations only (finding 8)."""
        from generator import generate_cp_runs as cp
        from generator import scenario_injection as si
        from generator.anchor_date import get_anchor_date
        from qa_tools.common import schedule
        bad = si.Injection(scenario_id="TS-CPAMB", dataset_id="cp-clients", anchor=-10,
                           config="t", arrivals=(si.ExtraArrival(
                               0, "09:00", target=targeting.Target("amber")),))
        original = si.INJECTIONS
        # ALONE: the refusal is the point, not where the planted ones sit.
        si.INJECTIONS = (bad,)
        try:
            periods = schedule.periods_for_dataset(cp.DATASET_ID,
                                                   until=get_anchor_date())[-len(cp.RUN_PLAN):]
            with pytest.raises(targeting.TargetError, match="TS-CPAMB.*lead-in"):
                cp._plan_injections(periods)
        finally:
            si.INJECTIONS = original


class TestEachPlantedScenarioSitsInItsEra:
    """Finding 7: the anchors are relative to ANCHOR_DATE and the setting eras
    are fixed dates, so a re-anchor would slide a scenario out of the era it
    demonstrates - silently for TS-44 and TS-46."""

    ERAS = {"TS-43": ("amber", "hold"), "TS-44": ("amber", "promote-and-acknowledge"),
            "TS-45": ("amber", "promote-and-acknowledge"), "TS-46": ("replacement", "green")}

    def test_each_anchor_falls_under_the_setting_it_needs(self):
        from generator import generate_runs as g
        from generator import scenario_injection as si
        from generator.anchor_date import get_anchor_date
        from qa_tools.common import amber_setting, asset_time, replacement_setting, schedule
        periods = schedule.periods_for_dataset(g.DATASET_ID,
                                               until=get_anchor_date())[-g.N_DELIVERIES:]
        for inj in si.for_dataset(g.DATASET_ID):
            if inj.scenario_id not in self.ERAS:
                continue
            kind, want = self.ERAS[inj.scenario_id]
            at = asset_time.start_of_day(si.resolve(inj, periods).period_date)
            got = (amber_setting if kind == "amber" else replacement_setting).resolve(
                g.DATASET_ID, at).value
            assert got == want, (inj.scenario_id, got)

    def test_every_scripted_decision_comes_after_the_rule_has_decided(self):
        """Finding 11: the scripted promotion and acknowledgement only follow
        the rule because the rule decides within the claim window."""
        from qa_tools.common import schedule, scripted_decisions
        window = schedule.claim_window(BDM_ID).total_seconds() / 3600
        for s in scripted_decisions.load():
            if s.dataset_id == BDM_ID and s.operation in ("promote", "acknowledge"):
                assert s.after_hours > window, (s.scenario, s.after_hours, window)
