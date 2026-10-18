"""The shared orchestrator's own rules, found by REQ-PIPE-243's post-build
critic (plans/post-build-review.md #220): the tenth Birth Registrations
difference, the refusal that must outlive a registry change, identity before
staging, a results file name every adapter must have, and the claim window
and dataset statistics driven for real against a third collection.
"""
from __future__ import annotations

import dataclasses
import sys
from datetime import date
from types import SimpleNamespace

import duckdb
import pytest

from qa_tools import collections
from qa_tools.collections.base import StatsSpec
from qa_tools.tools import legacy, orchestrate
from third_collection import FAKE_ID, FAKE_PREFIX, FAKE_TABLE


class TestTheTenthBirthRegistrationsDifference:
    """The old Birth Registrations orchestrator ALWAYS reconciled what the
    tools left out and always ran the full nothing-missing guard, even for a
    supply filed to no period; Child Protection's skips both for a run with
    no period. Keith, 2026-10-18: keep the old behaviour behind a flag."""

    def test_the_flag_is_known_and_declared_on_birth_registrations(self):
        assert "orchestrate.always_reconciles" in legacy.KNOWN
        bdm = collections.adapter(collections.by_id("civil-registration"))
        assert "orchestrate.always_reconciles" in bdm.legacy
        cp = collections.adapter(collections.by_id("child-protection"))
        assert "orchestrate.always_reconciles" not in cp.legacy

    def test_a_run_with_no_period_still_reconciles_under_the_flag(self, monkeypatch):
        monkeypatch.setattr(orchestrate, "_has_scope", lambda entry, run_id: False)
        entry = {"run_id": "run_x", "received_at": "2026-01-01T01:00:00+00:00"}
        assert orchestrate._reconciles(entry, "run_x", legacy=frozenset()) is False
        assert orchestrate._reconciles(entry, "run_x",
                                       legacy=frozenset({"orchestrate.always_reconciles"})) is True


class TestTheRefusalOutlivesTheRegistry:
    """steps() refuses a collection with no adapter by name - and keeps
    refusing after the registry changes, which a cached Steps did not."""

    def test_steps_refuses_after_the_adapter_disappears(self, monkeypatch):
        assert orchestrate.steps("child-protection") is not None
        monkeypatch.setattr(collections, "adapter",
                            lambda coll: (_ for _ in ()).throw(collections.NoAdapterError(coll.id)))
        with pytest.raises(collections.NoAdapterError, match="child-protection"):
            orchestrate.steps("child-protection")


class TestIdentityIsResolvedBeforeAnythingIsStaged:
    """run_single_file() with no run_by and no git identity must fail before
    it stages, or it leaves a trial table behind with nothing to clean it."""

    def test_a_missing_identity_stages_nothing(self, monkeypatch, tmp_path):
        from qa_tools.common import trial
        from qa_tools.tools import stage

        staged = []
        monkeypatch.setattr(stage, "stage_table", lambda *a, **k: staged.append(a))
        monkeypatch.setattr(orchestrate, "run_one", lambda *a, **k: [])

        def no_identity():
            raise RuntimeError("git identity is unset")
        monkeypatch.setattr(orchestrate, "get_run_by", no_identity)
        csv = tmp_path / "f.csv"
        csv.write_text("a\n1\n")
        with pytest.raises(RuntimeError, match="git identity"):
            orchestrate.run_single_file("civil-registration", trial.trial_run_id(),
                                        "birth_registrations", str(csv), "2026-01-02", None)
        assert staged == [], "the file was staged before the identity failure"


class TestEveryAdapterNamesItsResultsFile:
    """An adapter without results_json would fail at the very end of a whole
    batch, writing over the reports/ directory; the gate catches it first."""

    def test_the_collections_gate_refuses_an_empty_results_json(self, third_collection, tmp_path):
        from qa_tools.common import validate_collections as gate

        adapter = sys.modules["qa_tools.collections.fake_collection"]
        adapter.ADAPTER = dataclasses.replace(adapter.ADAPTER, results_json="")
        package = tmp_path / "package"
        package.mkdir(exist_ok=True)
        for module in ("civil_registration", "child_protection", "fake_collection"):
            (package / f"{module}.py").write_text("")
        problems = gate.config_problems(package)
        assert any("results_json" in p and FAKE_ID in p for p in problems), problems


class TestAThirdCollectionsStatsAndClaimWindowForReal:
    def test_a_non_empty_stats_spec_is_what_the_fake_collection_measures(self, third_collection):
        from qa_tools.tools import dataset_stats

        adapter = sys.modules["qa_tools.collections.fake_collection"]
        adapter.ADAPTER = dataclasses.replace(adapter.ADAPTER, stats=StatsSpec(
            aggregates={(FAKE_TABLE, "things"): {
                "kind": "categorical", "invalid_condition": "things NOT IN ('a', 'b')",
                "classification": "invalid code", "check_names": ["things.accepted_values"]}},
            value_counts={(FAKE_TABLE, "things"): ["a", "b"]}))
        conn = duckdb.connect(":memory:")
        conn.execute(f"CREATE TABLE {FAKE_TABLE} (fake_id VARCHAR, things VARCHAR, "
                     f"extract_timestamp TIMESTAMP)")
        conn.execute(f"INSERT INTO {FAKE_TABLE} VALUES ('F1', 'a', '2026-01-01 09:00:00'), "
                     "('F2', 'a', '2026-01-01 08:00:00'), ('F3', 'zz', '2026-01-01 08:30:00')")
        entry = {"run_id": f"{FAKE_PREFIX}001", "run_index": 1, "delivery": "fk-1",
                 "received_at": "2026-01-01T01:00:00+00:00"}

        stats = dataset_stats.compute_dataset_stats(FAKE_ID, conn, entry)

        assert stats["value_counts"]["things"] == [["a", 2], ["(invalid code)", 1]]
        assert stats["check_aggregates"][f"{FAKE_TABLE}.things"]["total_invalid"] == 1

    def test_the_claim_window_is_the_shortest_of_the_datasets_carried(self):
        from qa_tools.common import schedule

        on = date(2026, 1, 1)
        received = "2026-01-01T01:00:00+08:00"
        cp_only = SimpleNamespace(received_at=received, files_by_dataset={"cp-clients": "x"})
        assert orchestrate._claim_window("child-protection", cp_only) == \
            schedule.claim_window("cp-clients", on=on)
        bdm = SimpleNamespace(received_at=received, files_by_dataset={"birth-registrations": "x"})
        assert orchestrate._claim_window("civil-registration", bdm) == \
            schedule.claim_window("birth-registrations", on=on)
        # The adapter's dataset stands in only when the arrival names none.
        none_named = SimpleNamespace(received_at=received, files_by_dataset={})
        assert orchestrate._claim_window("child-protection", none_named) == \
            schedule.claim_window("cp-clients", on=on)
        two = SimpleNamespace(received_at=received,
                              files_by_dataset={"cp-clients": "x", "cp-case-workers": "y"})
        windows = [schedule.claim_window(d, on=on) for d in ("cp-clients", "cp-case-workers")]
        assert orchestrate._claim_window("child-protection", two) == min(windows)
