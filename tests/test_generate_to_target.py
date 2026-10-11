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
    def test_birth_registrations_ambers_are_outside_hold_and_at_the_top_of_the_draw(self):
        from generator import generate_runs as g
        from qa_tools.common import amber_setting, asset_time

        ambers = [(n, d) for (n, s), d in zip(g.RUN_PLAN, g.SCHEDULED_DATES) if s == "amber"]
        assert len(ambers) == round(g.N_DELIVERIES * g.AMBER_SHARE)
        for n, d in ambers:
            assert n == g.AMBER_ROWS
            setting = amber_setting.resolve(g.DATASET_ID, asset_time.start_of_day(d))
            assert setting.value != amber_setting.HOLD, d

    def test_reds_and_cleans_are_as_drawn(self):
        """Criterion 10: only the amber entries moved."""
        from generator import generate_runs as g

        drawn = g._build_run_plan(g.N_DELIVERIES, g._RUN_PLAN_SEED)
        assert [s for _n, s in drawn].count("red") == [s for _n, s in g.RUN_PLAN].count("red")
        for (n0, s0), (n1, s1) in zip(drawn, g.RUN_PLAN):
            if s0 == s1 == "red" or (s0 is None and s1 is None):
                assert n0 == n1

    def test_an_amber_is_never_made_stale(self, monkeypatch):
        from generator import generate_runs as g

        monkeypatch.setattr(g, "inject_stale_delivery",
                            lambda df, seed: (_ for _ in ()).throw(AssertionError("stale")))
        day = sorted(g.AMBER_DATES)[0]
        g.BirthRegistrationsProvider().generate(day, seed=1, n_rows=50, id_offset=0)

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
