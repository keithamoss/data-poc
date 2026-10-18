"""REQ-GEN-246: one generator driver, a provider per collection.

Driven for real through a third collection wherever a site was rewired
(criterion 9): the shared driver writing a fake collection's deliveries,
receipts and bookkeeping; generated_into() running it in hierarchy order;
scenario_injection.generated_periods(), generator/targeting.py and
generator/targets.py reading its provider; and the refusals - a seed out of
range, overlapping ranges, a target trial asked of a collection without
one, a scenario naming a dataset no provider makes.
"""
from __future__ import annotations

import json
import subprocess
import sys
import types
from datetime import date
from types import SimpleNamespace

import pytest

from generator import collections as providers
from generator import driver
from generator.collections.base import Job, Plan, Provider
from generator.output import redirect
from third_collection import FAKE_DATASET, FAKE_ID, FAKE_PREFIX, PROVIDER_MODULE


class _Writing(Provider):
    """A fake collection's provider that really writes: two daily slots,
    one one-file delivery each."""

    collection_id = FAKE_ID
    dataset_id = FAKE_DATASET
    seed_ranges = ((900_000, 901_000),)
    target_datasets = (FAKE_DATASET,)
    amber_dataset = FAKE_DATASET
    days = (date(2026, 1, 5), date(2026, 1, 6))
    at = ("09:00", "09:30")

    def seed_schedule(self):
        return [(f"fk_slot_{i}", 900_000 + i, 900_000 + i + 10) for i in (1, 2)]

    def generated_periods(self):
        return [SimpleNamespace(name=d.isoformat(), date=d) for d in self.days]

    def plan(self):
        return Plan(jobs=[Job(f"fk_slot_{i}", 900_000 + i, None, p)
                          for i, p in enumerate(self.generated_periods(), start=1)])

    def slot(self, plan, job):
        from generator.resupply import Delivery

        return [Delivery(received_date=job.period.date, severity=None, payload=None)]

    def entries(self, plan, job, deliveries, run_index_start):
        return [{"run_id": f"{FAKE_PREFIX}{run_index_start + n:03d}", "slot_id": job.slot_id,
                 "period": job.period.name, "received_at": None, "seed": job.seed}
                for n, _ in enumerate(deliveries, start=1)]

    def received_at(self, plan, job, n, delivery_obj, entry):
        from qa_tools.common import asset_time

        i = self.days.index(job.period.date)
        return asset_time.isoformat(asset_time.wall_clock(delivery_obj.received_date, self.at[i]))

    def files(self, plan, job, n, delivery_obj, entry, name):
        from qa_tools.common import asset_time

        return ({f"fake_things_{job.period.name}.csv": "fake_id,things\nF1,a\n"},
                asset_time.parse_instant(entry["received_at"], entry["run_id"]))


@pytest.fixture
def writing(third_collection, monkeypatch, tmp_path):
    """The third collection with a provider that writes, everything under
    tmp_path/out."""
    module = types.ModuleType(PROVIDER_MODULE)
    module.PROVIDER = _Writing()
    monkeypatch.setitem(sys.modules, PROVIDER_MODULE, module)
    out = tmp_path / "out"
    undo = redirect(out)
    yield module.PROVIDER, out
    undo()


class TestOneDriverForEveryCollection:
    """Criterion 1: the slot loop, bookkeeping, delivery and receipt writing
    are the driver's - a third collection gets them by being a provider."""

    def test_a_third_collections_history_is_written_by_the_shared_driver(self, writing):
        provider, out = writing
        manifest = driver.generate(FAKE_ID)

        assert [e["run_id"] for e in manifest] == [f"{FAKE_PREFIX}001", f"{FAKE_PREFIX}002"]
        book = json.loads((out / "generator_bookkeeping.json").read_text())
        assert [e["delivery"] for e in book[FAKE_DATASET]] == [e["delivery"] for e in manifest]
        for entry in manifest:
            delivered = out / "deliveries" / entry["delivery"]
            assert [f.name for f in delivered.iterdir()] == [f"fake_things_{entry['period']}.csv"]
        assert len(list((out / "receipts").iterdir())) == 2

    def test_a_regeneration_overwrites_rather_than_accumulates(self, writing):
        _provider, out = writing
        driver.generate(FAKE_ID)
        driver.generate(FAKE_ID)
        assert len(list((out / "deliveries").iterdir())) == 2

    def test_two_arrivals_at_one_instant_are_refused(self, writing, monkeypatch):
        provider, _out = writing
        monkeypatch.setattr(provider, "at", ("09:00", "09:00"))
        provider.days = (date(2026, 1, 5), date(2026, 1, 5))
        with pytest.raises(ValueError, match="both claim receipt instant"):
            driver.generate(FAKE_ID)


class TestTheSeedSchedule:
    """Criteria 2 and 3."""

    def test_a_seed_outside_the_declared_range_is_refused_before_anything_is_written(
            self, writing, monkeypatch):
        provider, out = writing
        monkeypatch.setattr(provider, "seed_schedule",
                            lambda: [("fk_slot_1", 900_001, 900_011), ("fk_slot_2", 905_000, 905_000)])
        with pytest.raises(providers.base.SeedOutOfRange, match=f"{FAKE_ID}.*905000.*fk_slot_2"):
            driver.generate(FAKE_ID)
        assert not out.exists(), "a refused seed must leave nothing written"

    def test_the_real_providers_derive_only_seeds_they_declare(self):
        found = providers.providers()
        assert [p.collection_id for p in found] == ["civil-registration", "child-protection"]
        for provider in found:
            assert provider.seed_schedule(), provider.collection_id
            provider.check_seeds()

    def test_overlapping_ranges_fail_the_gate_naming_both(self, third_collection, monkeypatch):
        from generator import validate_providers

        fake = sys.modules[PROVIDER_MODULE].PROVIDER
        assert validate_providers.problems() == []
        monkeypatch.setattr(fake, "seed_ranges", ((1500, 1600),))
        monkeypatch.setattr(fake, "seed_schedule", lambda: [("fk", 1550, 1550)])
        problems = validate_providers.problems()
        assert len(problems) == 1
        assert "civil-registration" in problems[0] and FAKE_ID in problems[0]
        assert validate_providers.main() == 1


class TestImportingAProviderCostsNoToolImport:
    """Criterion 7: declarations are read without pandas or numpy."""

    def test_every_provider_module_imports_without_pandas_or_numpy(self):
        found = providers.providers()
        assert found
        names = [type(p).__module__ for p in found]
        code = ("import importlib, sys\n"
                f"for name in {names!r}:\n"
                "    importlib.import_module(name)\n"
                "import generator.driver, generator.collections\n"
                "from generator import validate_providers\n"
                "assert validate_providers.problems() == []\n"
                "print(sorted(m for m in ('pandas', 'numpy') if m in sys.modules))\n")
        out = subprocess.run([sys.executable, "-c", code], capture_output=True, text=True,
                             check=True)
        assert out.stdout.strip() == "[]", out.stdout + out.stderr


class TestTheTargetTrialIsTheProvidersToDeclare:
    """Criteria 5 and 6."""

    def test_a_trial_asked_of_a_collection_without_one_is_refused_naming_it(
            self, writing, monkeypatch):
        from cli import pipeline

        planned = []
        monkeypatch.setattr(driver, "generate", lambda cid: planned.append(cid))
        for collection_id in (FAKE_ID, "child-protection"):
            with pytest.raises(pipeline.TargetTrialUnavailable, match=collection_id):
                pipeline.generate_collection(collection_id, trial=True)
        assert planned == [], "the refusal comes before anything is generated"

    def test_the_cli_and_the_bootstrap_read_the_providers_declaration(self, third_collection):
        from cli import pipeline

        assert pipeline.has_target_trial("civil-registration") is True
        assert pipeline.has_target_trial("child-protection") is False
        assert pipeline.has_target_trial(FAKE_ID) is False
        assert pipeline.target_datasets(FAKE_ID) == (FAKE_DATASET,)
        assert pipeline.generated_collections() == ["civil-registration", "child-protection",
                                                    FAKE_ID]

    def test_the_adapters_carry_no_generator_pointer_any_more(self):
        from qa_tools import collections

        for adapter in collections.adapters():
            assert not hasattr(adapter, "generator") and not hasattr(adapter, "target_datasets")

    def test_a_target_on_a_collection_without_levers_is_refused_naming_it(self, third_collection):
        from generator import targeting

        with pytest.raises(targeting.TargetError, match=f"{FAKE_ID} declares no target levers"):
            targeting.check_target(targeting.Target("amber", ("x.completeness",)), FAKE_DATASET,
                                   "TS-FAKE")

    def test_the_built_record_reads_each_collections_own_ambers(self, third_collection, tmp_path):
        from generator import targets

        book = tmp_path / "book.json"
        book.write_text(json.dumps({FAKE_DATASET: [
            {"period": "2026-01-05", "delivery": "d1", "dirty_severity": "amber",
             "run_id": "fk_run_001"}]}))
        sys.modules[PROVIDER_MODULE].PROVIDER.amber_dataset = FAKE_DATASET
        [built] = targets.written(book, tmp_path / "none.json")
        assert (built.dataset_id, built.delivery, built.target) == (FAKE_DATASET, "d1", "amber")

    def test_a_record_for_a_dataset_no_provider_makes_is_refused(self, without_adapter, tmp_path):
        from generator import targets

        book = tmp_path / "book.json"
        book.write_text(json.dumps({"bare-things": []}))
        with pytest.raises(ValueError, match="bare-things"):
            targets.written(book, tmp_path / "none.json")


class TestTheRegistryRoutesTheRest:
    """Criterion 8."""

    def test_generated_periods_come_from_the_datasets_provider(self, writing):
        from generator import scenario_injection

        assert [p.name for p in scenario_injection.generated_periods(FAKE_DATASET)] == \
            ["2026-01-05", "2026-01-06"]

    def test_a_dataset_with_no_provider_has_no_generated_periods(self, without_adapter):
        from generator import scenario_injection

        with pytest.raises(scenario_injection.CannotPlace, match="bare-things"):
            scenario_injection.generated_periods("bare-things")

    def test_a_scenario_naming_an_unprovided_dataset_stops_generation_before_any_write(
            self, without_adapter, monkeypatch, tmp_path):
        from generator import scenario_injection as si

        stray = si.Injection(scenario_id="TS-STRAY", dataset_id="bare-things", anchor=-1,
                             config="a test", arrivals=(si.ExtraArrival(0, "09:00"),))
        monkeypatch.setattr(si, "INJECTIONS", (*si.INJECTIONS, stray))
        undo = redirect(tmp_path / "out")
        try:
            with pytest.raises(si.CannotPlace, match="TS-STRAY names bare-things"):
                driver.generate(FAKE_ID)
        finally:
            undo()
        assert not (tmp_path / "out").exists()

    def test_generated_into_runs_every_provider_in_hierarchy_order(self, third_collection,
                                                                   monkeypatch, tmp_path):
        from generator.output import generated_into

        ran = []
        monkeypatch.setattr(driver, "generate",
                            lambda cid: ran.append((cid, str(driver.DELIVERIES_DIR))))
        with generated_into(tmp_path):
            pass
        assert [cid for cid, _ in ran] == ["civil-registration", "child-protection", FAKE_ID]
        assert all(where == str(tmp_path / "deliveries") for _, where in ran)
