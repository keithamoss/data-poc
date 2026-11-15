"""REQ-GEN-392 criterion 14: generator/dirty.py's presets size each fault
from the warn and fail bands of the checks it aims at, read through
check_bands at the frame's own row count, and plant exactly that count.

Every test here runs on a small frame built in the test, through the real
presets and the real committed check files - no bootstrap, no database.
They were seen failing against the literal per-row rates the presets
carried before this requirement (a Fail sex fault of ~66 rows where five is
derived, a Warn planting on single-tier rules, counts that moved with the
seed, a frame too small for its fault planted anyway).

The expected sizes are worked by hand from the committed bands, each in a
comment, so a test does not take its expectation from the code it tests:

- Birth Registrations' place_of_birth_facility nulls at 1,900 rows: dbt
  warns > 300 and fails > 600, Soda warns > 15% (286 rows) and fails > 35%,
  the contract fails >= 35% (665). Amber is 286..600; the first failure is
  601 (dbt). Warn = (286 + 600) // 2 = 443. A Fail preset first breaks five
  twin pairs, so it sizes at 1,895 rows: Soda warns from 285 (15.04%), amber
  is 285..600, and Fail = 601 + 316 = 917.
- Child Protection's client postcodes at 500 rows: dbt warns > 0 and fails
  > 15, Soda fails > 3% (16 rows), the contract fails >= 3% (15). Amber is
  1..14; the first failure is 15. Warn = 7; Fail = 15 + 14 = 29.
"""
from __future__ import annotations

from pathlib import Path

import pandas as pd
import pytest

from generator import dirty

VALID_POSTCODE = "6007"


# ---- frames ---------------------------------------------------------------

def _bdm_frame(n: int = 1900, pairs: int = 40) -> pd.DataFrame:
    """`n` clean rows, the first 2 * `pairs` of them real twin pairs."""
    rows = []
    for i in range(n):
        twin = i < 2 * pairs
        k = i // 2 if twin else i
        rows.append({
            "registration_number": f"BDM-{i:09d}",
            "sex": "M",
            "child_given_names": "Alex",
            "child_family_name": "Smith",
            "registering_parent_1_name": f"Parent {k}",
            "registering_parent_2_name": "Sam Smith",
            "date_of_birth": pd.Timestamp("2026-08-01") + pd.Timedelta(days=k % 20),
            "date_registered": pd.Timestamp("2026-09-01"),
            "extract_timestamp": pd.Timestamp("2026-09-01 12:00:00"),
            "place_of_birth_facility": f"Facility {k}",
            "place_of_birth_suburb": "Perth",
            "source_system_record_id": f"SRC-{i:09d}",
            "is_multiple_birth": twin,
        })
    return pd.DataFrame(rows)


def _clients(n: int = 500) -> pd.DataFrame:
    return pd.DataFrame({
        "cp_client_id": [f"CPS-{i:09d}" for i in range(n)],
        "given_name": ["Alex"] * n,
        "family_name": ["Smith"] * n,
        "date_of_birth": pd.to_datetime(["2015-01-01"] * n),
        "sex": ["M"] * n,
        "suburb": ["Perth"] * n,
        "postcode": [VALID_POSTCODE] * n,
        "case_opened_date": pd.to_datetime(["2024-01-01"] * n),
        "case_status": ["Open"] * n,
    })


def _workers(n: int = 60) -> pd.DataFrame:
    return pd.DataFrame({"worker_id": [f"CPS-STAFF-{i:05d}" for i in range(n)]})


def _notifications(clients, workers, n: int = 900) -> pd.DataFrame:
    return pd.DataFrame({
        "notification_id": [f"NOTIF-{i:08d}" for i in range(n)],
        "cp_client_id": clients["cp_client_id"].values[[i % len(clients) for i in range(n)]],
        "assigned_worker_id": workers["worker_id"].values[[i % len(workers) for i in range(n)]],
        "concern_type": ["Neglect"] * n,
        "source_type": ["School"] * n,
        "risk_rating": ["Low"] * n,
        "outcome": ["No further action"] * n,
    })


# ---- counting what was planted -------------------------------------------

def _dup_keys(s: pd.Series) -> int:
    s = s.dropna()
    return int(s[s.duplicated(keep=False)].nunique())


def _orphan_twins(df: pd.DataFrame) -> int:
    twins = df[df["is_multiple_birth"].fillna(False).astype(bool)]
    sizes = twins.groupby(["date_of_birth", "place_of_birth_facility",
                           "registering_parent_1_name"], dropna=False).size()
    return int((sizes == 1).sum())


def _bdm_counts(out: pd.DataFrame) -> dict[str, int]:
    """{rule key: faulty rows} for every rule a Birth Registrations fault
    aims at, counted from the frame as a check would."""
    dob = pd.to_datetime(out["date_of_birth"], errors="coerce")
    counts = {
        "sex.conformity": int((out["sex"].notna() & ~out["sex"].isin(["M", "F", "X"])).sum()),
        "place_of_birth_facility.completeness": int(out["place_of_birth_facility"].isna().sum()),
        "source_system_record_id.uniqueness": _dup_keys(out["source_system_record_id"]),
        "registration_number.uniqueness": _dup_keys(out["registration_number"]),
        "Supply timestamp ordering": int((pd.to_datetime(out["extract_timestamp"])
                                          < pd.to_datetime(out["date_registered"])).sum()),
        "Multiple-birth sibling match": _orphan_twins(out),
        "place_of_birth_suburb.conformity": int(out["place_of_birth_suburb"]
                                                .isin(dirty._INVALID_SUBURB_POOL).sum()),
        "Date of birth in a plausible range": int((dob < pd.Timestamp("1900-01-01")).sum()),
        "source_system_record_id.conformity": int(out["source_system_record_id"]
                                                  .isin(dirty._MALFORMED_SRC_ID_POOL).sum()),
    }
    for col in ("child_given_names", "child_family_name", "registering_parent_1_name",
                "registering_parent_2_name"):
        counts[f"{col}.conformity"] = int(out[col].isin(dirty._JUNK_TEXT_POOL).sum())
    for col in ("date_of_birth", "date_registered", "is_multiple_birth", "extract_timestamp",
                "source_system_record_id", "registration_number"):
        counts[f"{col}.completeness"] = int(out[col].isna().sum())
    return counts


def _clients_counts(out: pd.DataFrame) -> dict[str, int]:
    dob = pd.to_datetime(out["date_of_birth"], errors="coerce")
    counts = {
        "postcode.conformity": int(out["postcode"].isin(dirty._INVALID_POSTCODE_POOL).sum()),
        "Date of birth in a plausible range": int((dob < pd.Timestamp("1900-01-01")).sum()),
        "cp_client_id.uniqueness": _dup_keys(out["cp_client_id"]),
        "sex.conformity": int((out["sex"].notna() & ~out["sex"].isin(["M", "F", "X"])).sum()),
    }
    for col in ("given_name", "family_name", "date_of_birth", "suburb", "case_opened_date"):
        counts[f"{col}.completeness"] = int(out[col].isna().sum())
    return counts


# ---- the catalogue, and a band changed in a check file --------------------

def _rule(dataset_id: str, key: str):
    from asset_model import check_bands
    from generator.targeting import rule_key

    found = [r for r in check_bands.catalogue().rules()
             if r.dataset_id == dataset_id and rule_key(r) == key]
    assert found, f"precondition: {key} is a rule on {dataset_id}"
    return found[0]


def _fails(rule, x, rows) -> bool:
    return any(c.fails(x, rows) for c in rule.checks)


def _warns(rule, x, rows) -> bool:
    return any(c.warns(x, rows) for c in rule.checks)


@pytest.fixture
def cp_postcode_fails_above_ten(monkeypatch, tmp_path):
    """Child Protection's dbt postcode test with `error_if: ">10"` where the
    committed file says ">15" - a band changed IN A CHECK FILE, read through
    check_bands exactly as the committed one is."""
    from asset_model import check_bands, collections

    coll = collections.by_id("child-protection")
    real = Path(check_bands.ROOT / coll.dbt_schema)
    text = real.read_text()
    marker = ('check_id: quarterly.child-protection-family-support.child-protection.'
              'cp-clients.postcode.accepted_values_dbt')
    head, tail = text.split(marker, 1)
    assert 'error_if: ">15"' in tail.split("- name:", 1)[0], "precondition: the committed band"
    changed = head + marker + tail.replace('error_if: ">15"', 'error_if: ">10"', 1)
    copy = tmp_path / "schema.yml"
    copy.write_text(changed)
    original = check_bands.dbt_bounds

    def reading_the_changed_file(path):
        return original(copy if Path(path) == real else path)

    monkeypatch.setattr(check_bands, "dbt_bounds", reading_the_changed_file)


# ---- the tests ------------------------------------------------------------

@pytest.mark.asset("quarterly")
class TestABandChangedInACheckFileMovesTheFault:
    def test_the_fail_size_moves_with_the_band(self, cp_postcode_fails_above_ten):
        out = dirty.apply_cp_clients_presets(_clients(500), severity="red", seed=1)
        # first failure 11 (dbt > 10), amber 1..10, so 11 + 10.
        assert _clients_counts(out)["postcode.conformity"] == 21

    def test_the_warn_size_moves_with_the_band(self, cp_postcode_fails_above_ten):
        out = dirty.apply_cp_clients_presets(_clients(500), severity="amber", seed=1)
        assert _clients_counts(out)["postcode.conformity"] == (1 + 10) // 2

    def test_against_the_committed_band_the_sizes_are_the_committed_ones(self):
        red = dirty.apply_cp_clients_presets(_clients(500), severity="red", seed=1)
        amber = dirty.apply_cp_clients_presets(_clients(500), severity="amber", seed=1)
        assert _clients_counts(red)["postcode.conformity"] == 29
        assert _clients_counts(amber)["postcode.conformity"] == 7


@pytest.mark.asset("daily")
class TestBirthRegistrations:
    def test_a_fail_fault_lands_past_every_aimed_rules_fail_threshold(self):
        df = _bdm_frame()
        out = dirty.apply_birth_registrations_presets(df, severity="red", seed=3)
        counts = _bdm_counts(out)
        assert set(counts) == {k for keys in dirty.BIRTH_REGISTRATIONS_AIMS.values() for k in keys
                               if k != "(table).timeliness.drop"}
        for key, n in counts.items():
            rule = _rule("birth-registrations", key)
            assert _fails(rule, n, len(out)), f"{key}: {n} faulty rows do not fail it"
        assert counts["place_of_birth_facility.completeness"] == 917

    def test_a_single_tier_rule_gets_five_rows_from_a_fail_preset(self):
        counts = _bdm_counts(dirty.apply_birth_registrations_presets(
            _bdm_frame(), severity="red", seed=3))
        single = {k: v for k, v in counts.items() if k != "place_of_birth_facility.completeness"}
        assert single == {k: 5 for k in single}

    def test_a_warn_fault_lands_inside_its_amber_band_and_single_tier_rules_get_nothing(self):
        df = _bdm_frame()
        out = dirty.apply_birth_registrations_presets(df, severity="amber", seed=3)
        counts = _bdm_counts(out)
        facility = counts.pop("place_of_birth_facility.completeness")
        assert facility == 443
        rule = _rule("birth-registrations", "place_of_birth_facility.completeness")
        assert _warns(rule, facility, len(out)) and not _fails(rule, facility, len(out))
        assert counts == {k: 0 for k in counts}, "a single-tier rule was planted on by a Warn"

    def test_the_planted_count_is_exact_whatever_the_seed(self):
        seen = {tuple(sorted(_bdm_counts(dirty.apply_birth_registrations_presets(
            _bdm_frame(), severity="red", seed=s)).items())) for s in (1, 2, 3, 4)}
        assert len(seen) == 1

    def test_the_drop_against_the_previous_supply_is_derived_from_its_band(self):
        """Evidently's row drop warns > 0.1 and fails > 0.25 against the
        previous supply. Of 2,000 previous rows, 201..500 removed warns and
        501 fails: Warn removes the middle, 350; Fail removes 501 + 300."""
        df = _bdm_frame(1900)
        amber = dirty.apply_birth_registrations_presets(df, "amber", seed=1, previous_row_count=2000)
        red = dirty.apply_birth_registrations_presets(df, "red", seed=1, previous_row_count=2000)
        assert len(amber) == 2000 - 350
        # the sibling fault drops five more rows after the cut
        assert len(red) == 2000 - 801 - 5

    def test_the_same_seed_gives_the_same_bytes(self):
        a = dirty.apply_birth_registrations_presets(_bdm_frame(), "red", seed=9).to_csv(index=False)
        b = dirty.apply_birth_registrations_presets(_bdm_frame(), "red", seed=9).to_csv(index=False)
        assert a == b


@pytest.mark.asset("quarterly")
class TestChildProtection:
    def test_a_fail_fault_lands_past_every_aimed_rules_fail_threshold(self):
        out = dirty.apply_cp_clients_presets(_clients(500), severity="red", seed=1)
        counts = _clients_counts(out)
        assert set(counts) == {k for keys in dirty.CP_CLIENTS_AIMS.values() for k in keys}
        for key, n in counts.items():
            assert _fails(_rule("cp-clients", key), n, len(out)), f"{key}: {n} rows do not fail"
        assert {k: v for k, v in counts.items() if k != "postcode.conformity"} == {
            k: 5 for k in counts if k != "postcode.conformity"}

    def test_a_warn_preset_plants_nothing_on_a_single_tier_rule(self):
        clients, workers = _clients(), _workers()
        df = _notifications(clients, workers)
        out = dirty.apply_cp_notifications_presets(df, clients, workers, severity="amber", seed=1)
        pd.testing.assert_frame_equal(out, df)

    def test_a_fail_preset_plants_five_rows_on_each_single_tier_rule(self):
        clients, workers = _clients(), _workers()
        df = _notifications(clients, workers)
        out = dirty.apply_cp_notifications_presets(df, clients, workers, severity="red", seed=1)
        assert len(out) == len(df) + 5
        assert _dup_keys(out["notification_id"]) == 5
        assert int((out["concern_type"] != "Neglect").sum()) == 5
        for col, clean in (("source_type", "School"), ("risk_rating", "Low"),
                           ("outcome", "No further action")):
            assert int((out[col] != clean).sum()) == 5, col
        for col, parent in (("cp_client_id", clients["cp_client_id"]),
                            ("assigned_worker_id", workers["worker_id"])):
            assert int(out[col].isna().sum()) == 5, col
            assert int((out[col].notna() & ~out[col].isin(set(parent))).sum()) == 5, col

    def test_the_planted_count_is_exact_whatever_the_seed(self):
        carers = pd.DataFrame({"carer_id": [f"CARER-{i:06d}" for i in range(300)]})
        assert {_dup_keys(dirty.apply_cp_carers_presets(carers, "red", seed=s)["carer_id"])
                for s in range(1, 6)} == {5}
        assert {_dup_keys(dirty.apply_cp_case_workers_presets(_workers(), "red", seed=s)
                          ["worker_id"]) for s in range(1, 6)} == {5}

    def test_a_frame_too_small_for_its_fault_is_refused(self):
        from generator.fault_sizing import FaultSizeError

        with pytest.raises(FaultSizeError) as err:
            dirty.apply_cp_case_workers_presets(_workers(3), "red", seed=1)
        text = str(err.value)
        assert "apply_cp_case_workers_presets" in text and "worker_id.uniqueness" in text
        assert "soda" in text and "3 rows" in text


@pytest.mark.asset("quarterly")
class TestTheDerivationRefusesAnUnreachableBand:
    def test_no_check_failing_within_the_frame_is_refused(self):
        from asset_model import check_bands as cb
        from generator import fault_sizing

        only = cb.Check("q.a.c.cp-clients.postcode.accepted_values_dbt", "dbt", "cp-clients",
                        "postcode", "conformity", "accepted_values", "x.yml",
                        warn=(cb.Bound(">", 0, cb.ROWS),), fail=(cb.Bound(">", 600, cb.ROWS),))
        with pytest.raises(fault_sizing.FaultSizeError, match="no check of it fails"):
            fault_sizing.size(cb.Catalogue([only]), "cp-clients", ("postcode.conformity",),
                              "red", 500, "a test preset, postcode_invalid")

    def test_an_empty_intersection_is_refused(self):
        from asset_model import check_bands as cb
        from generator import fault_sizing

        def check(col, lo, hi):
            return cb.Check(f"q.a.c.cp-clients.{col}.accepted_values_dbt", "dbt", "cp-clients",
                            col, "conformity", "accepted_values", "x.yml",
                            warn=(cb.Bound(">", lo, cb.ROWS),), fail=(cb.Bound(">", hi, cb.ROWS),))

        cat = cb.Catalogue([check("postcode", 0, 10), check("sex", 20, 30)])
        with pytest.raises(fault_sizing.FaultSizeError, match="do not meet"):
            fault_sizing.size(cat, "cp-clients", ("postcode.conformity", "sex.conformity"),
                              "amber", 500, "a test preset, two_rules")


@pytest.mark.asset("quarterly")
def test_population_keeps_its_own_literal_rates_and_reads_no_bands(monkeypatch):
    """Criterion 9 (QC): `mothman population --dirty` runs with no asset
    selected, so its presets are literal exploratory defaults in
    synthetic_data_generator/, reading no check file."""
    from asset_model import check_bands
    from synthetic_data_generator import dirty_presets

    monkeypatch.setattr(check_bands, "catalogue",
                        lambda: (_ for _ in ()).throw(AssertionError("read the bands")))
    clients, workers = _clients(), _workers()
    out = dirty_presets.apply_birth_registrations_presets(_bdm_frame(400), "red", seed=1)
    assert len(out) > 0
    notes = dirty_presets.apply_cp_notifications_presets(
        _notifications(clients, workers), clients, workers, "red", seed=1)
    assert len(notes) > 900


@pytest.mark.asset("daily")
class TestTheRealToolsReadTheSizesAsAimed:
    """The derived sizes on a real generated batch, through the trial path
    `mothman bdm qa --trial` uses, recording nothing: every rule a Fail
    preset aims at fails in at least one tool, and a Warn preset fails
    nothing."""

    @staticmethod
    def _trial(tmp_path, df, ref):
        from cli.collection_cli import of as _cli_of

        ref_csv, csv = tmp_path / "ref.csv", tmp_path / "supply.csv"
        ref.to_csv(ref_csv, index=False)
        df.to_csv(csv, index=False)
        return _cli_of("bdm").run_check_local_file(str(csv), str(ref_csv), "trial:not-recorded",
                                                   keep=False)[0]

    @staticmethod
    def _batches():
        from datetime import date

        from generator.daily_batch import generate_daily_batch

        ref = generate_daily_batch(date(2026, 9, 19), seed=1233, n_rows=1900, id_offset=0)
        today = generate_daily_batch(date(2026, 9, 20), seed=1234, n_rows=1900,
                                     id_offset=100_000)
        return ref, today

    def test_every_aimed_rule_of_a_fail_preset_fails(self, tmp_path):
        from asset_model import check_bands
        from generator.targeting import rule_key

        ref, today = self._batches()
        red = dirty.apply_birth_registrations_presets(today, "red", seed=7,
                                                      previous_row_count=len(ref))
        results = self._trial(tmp_path, red, ref)
        failed = {r["check_id"] for r in results if r["status"] == "fail"}
        rules = {rule_key(r): r for r in check_bands.catalogue().rules()
                 if r.dataset_id == "birth-registrations"}
        missed = [k for keys in dirty.BIRTH_REGISTRATIONS_AIMS.values() for k in keys
                  if not {c.check_id for c in rules[k].checks} & failed]
        assert not missed, f"aimed at Fail and no tool failed: {missed}"

    def test_a_warn_preset_fails_nothing(self, tmp_path):
        ref, today = self._batches()
        amber = dirty.apply_birth_registrations_presets(today, "amber", seed=7,
                                                        previous_row_count=len(ref))
        results = self._trial(tmp_path, amber, ref)
        failing = sorted(r["check_id"] for r in results if r["status"] == "fail")
        assert not failing
        assert any(r["status"] == "warn" for r in results)


@pytest.mark.asset("daily")
class TestTheSizeIsTheTotalNotAnAddition:
    """post-build-review #381 (critic, wip/gen-392 at f09e46c0): the derived
    size is the number of faulty rows a check reads, so faults the clean
    frame already carries count towards it - as targeting._set_nulls sizes
    a total. A real batch carries ~50 null facilities of its own."""

    @staticmethod
    def _with_natural_nulls(n_null: int) -> pd.DataFrame:
        df = _bdm_frame()
        singles = df.index[~df["is_multiple_birth"]][:n_null]
        df.loc[singles, "place_of_birth_facility"] = None
        return df

    def test_a_warn_lands_on_the_middle_counting_the_frames_own_nulls(self):
        out = dirty.apply_birth_registrations_presets(self._with_natural_nulls(53), "amber", seed=3)
        assert int(out["place_of_birth_facility"].isna().sum()) == 443

    def test_a_fail_lands_on_its_size_counting_the_frames_own_nulls(self):
        out = dirty.apply_birth_registrations_presets(self._with_natural_nulls(53), "red", seed=3)
        assert int(out["place_of_birth_facility"].isna().sum()) == 917

    def test_a_frame_already_past_the_aimed_band_is_refused(self):
        from generator.fault_sizing import FaultSizeError

        with pytest.raises(FaultSizeError, match="place_of_birth_facility.completeness"):
            dirty.apply_birth_registrations_presets(self._with_natural_nulls(700), "amber",
                                                    seed=3)


@pytest.mark.asset("quarterly")
def test_a_single_tier_fail_counts_the_frames_own_faults():
    """#381 on Child Protection: two clients already without a given name,
    so a Fail plants three more to make the five."""
    df = _clients(500)
    df.loc[[10, 20], "given_name"] = None
    out = dirty.apply_cp_clients_presets(df, "red", seed=1)
    assert int(out["given_name"].isna().sum()) == 5


@pytest.mark.asset("quarterly")
def test_the_closed_case_hygiene_count_is_exact_whatever_the_seed():
    """post-build-review #382 (critic): a reopened investigation could then
    have its client repointed to one that does not exist by the dangling
    fault, and the hygiene rule's join to clients dropped it - five planted,
    three or four read in about one seed in five."""
    n = 181
    clients = pd.DataFrame({"cp_client_id": [f"CPS-{i:09d}" for i in range(60)],
                            "case_status": ["Closed" if i < 30 else "Open" for i in range(60)]})
    notifications = pd.DataFrame({"notification_id": [f"NOTIF-{i:08d}" for i in range(n)]})
    workers = _workers()
    investigations = pd.DataFrame({
        "investigation_id": [f"INV-{i:06d}" for i in range(n)],
        "notification_id": notifications["notification_id"].values,
        "cp_client_id": clients["cp_client_id"].values[[i % 60 for i in range(n)]],
        "start_date": pd.to_datetime(["2025-01-01"] * n),
        "end_date": pd.to_datetime(["2025-06-01"] * n),
        "lead_worker_id": workers["worker_id"].values[[i % 60 for i in range(n)]],
    })
    closed = set(clients.loc[clients["case_status"] == "Closed", "cp_client_id"])
    seen = set()
    for seed in range(40):
        out = dirty.apply_cp_investigations_presets(investigations, clients, notifications,
                                                    workers, "red", seed=seed)
        seen.add(int((out["end_date"].isna() & out["cp_client_id"].isin(closed)).sum()))
    assert seen == {5}


@pytest.mark.asset("quarterly")
class TestEveryRefusalNamesTheBands:
    """post-build-review #383 (critic, criterion 7): three refusal paths named
    neither the bands nor, for broken twins, the rule."""

    def test_too_few_eligible_rows(self):
        from generator.fault_sizing import FaultSizeError

        with pytest.raises(FaultSizeError) as err:
            dirty.apply_cp_case_workers_presets(_workers(8), "red", seed=1)
        assert "worker_id.uniqueness" in str(err.value) and "soda warn" in str(err.value)

    def test_too_small_a_value_pool(self):
        from generator.fault_sizing import FaultSizeError

        carers = pd.DataFrame({"carer_id": [f"CARER-{i:06d}" for i in range(50)]})
        p = dirty._Planter(carers, "cp_carers", "red", "a test preset",
                           {"one_value": ("carer_id.uniqueness",)})
        with pytest.raises(FaultSizeError) as err:
            p.values("one_value", "carer_id", ["X"], seed=1, distinct=True)
        assert "carer_id.uniqueness" in str(err.value) and "soda warn" in str(err.value)

    @pytest.mark.asset("daily")
    def test_too_few_twin_pairs(self):
        from generator.fault_sizing import FaultSizeError

        with pytest.raises(FaultSizeError) as err:
            dirty.apply_birth_registrations_presets(_bdm_frame(400, pairs=2), "red", seed=1)
        assert "Multiple-birth sibling match" in str(err.value)
        assert "dbt warn" in str(err.value)


@pytest.mark.asset("quarterly")
class TestTheDerivationsOtherShapes:
    def test_a_measure_it_cannot_plant_is_refused(self):
        """post-build-review #384 (critic, criterion 2): any measure but bad
        rows was read as a proportional drop, so dbt's count of ROWS IN
        DUPLICATED GROUPS would have been sized as a share of the frame."""
        from generator import fault_sizing

        with pytest.raises(fault_sizing.FaultSizeError, match="cannot plant"):
            fault_sizing.size(fault_sizing.catalogue(), "cp-notifications",
                              ("notification_id.uniqueness.rows in duplicated groups",),
                              "red", 900, "a probe")

    def test_the_drop_is_still_sized_as_a_proportion(self):
        from generator import fault_sizing

        cat = fault_sizing.catalogue()
        assert fault_sizing.size(cat, "cp-clients", ("(table).timeliness.drop",), "red", 2000,
                                 "a probe") == 801

    def test_a_fail_aimed_at_two_rules_takes_the_larger_size(self):
        """J3: postcode warns > 0 and fails > 10 (11 + 10 = 21); sex warns
        > 0 and fails > 20 (21 + 20 = 41)."""
        from asset_model import check_bands as cb
        from generator import fault_sizing

        def check(col, hi):
            return cb.Check(f"q.a.c.cp-clients.{col}.accepted_values_dbt", "dbt", "cp-clients",
                            col, "conformity", "accepted_values", "x.yml",
                            warn=(cb.Bound(">", 0, cb.ROWS),), fail=(cb.Bound(">", hi, cb.ROWS),))

        cat = cb.Catalogue([check("postcode", 10), check("sex", 20)])
        assert fault_sizing.size(cat, "cp-clients", ("postcode.conformity", "sex.conformity"),
                                 "red", 500, "two rules") == 41


#: The data asset this module acts for unless a class says otherwise (C11).
pytestmark = pytest.mark.asset("quarterly")
