"""datacontract-cli asked only for the rules its run records, through its
own `quality_ids` and `schema_name` options (REQ-PIPE-190).

Written before the code. As for dbt (tests/test_dbt_scoped.py), the bar
is identical records: the real tool runs twice over the same dirty
fixture, whole contract and scoped, and every in-scope record must match
field for field.
"""
from __future__ import annotations

import random
from pathlib import Path

import pytest

from fixture_ids import BDM_DIRTY_RUN_ID, CP_DIRTY_RUN_ID
from qa_tools.common import asked_for, check_lifecycle, config_yaml, left_out
from qa_tools.common import qa_results_writer, supply_db

ROOT = Path(__file__).resolve().parent.parent
CONTRACTS = ["contract/child-protection-contract.yaml",
             "contract/bdm-birth-registrations-contract.yaml"]
P = "data-asset-1.child-protection-family-support.child-protection"


def _rules(doc):
    for table in doc.get("schema") or []:
        for rule in table.get("quality") or []:
            yield table["name"], rule
        for prop in table.get("properties") or []:
            for rule in prop.get("quality") or []:
                yield table["name"], rule


def _check_id(rule) -> str:
    return {p["property"]: p["value"] for p in rule["customProperties"]}["check_id"]


class TestEveryRuleHasAnId:
    """Criteria 1 and 2."""

    @pytest.mark.parametrize("path", CONTRACTS)
    def test_its_id_is_its_check_id_with_colons(self, path):
        """ODCS forbids a '.' in an id (Keith, 2026-10-12: ':' for '.')."""
        doc = config_yaml.parse((ROOT / path).read_text())
        rules = list(_rules(doc))
        assert rules
        assert [(r.get("id"), _check_id(r)) for _, r in rules
                if r.get("id") != _check_id(r).replace(".", ":")] == []

    @pytest.mark.parametrize("mutate,match", [
        (lambda rule: rule.pop("id"), "no ODCS `id`"),
        (lambda rule: rule.update(id="something-else"), "something-else"),
    ])
    def test_the_gate_refuses_a_missing_or_different_id(self, mutate, match):
        doc = config_yaml.parse((ROOT / CONTRACTS[0]).read_text())
        _, rule = next(iter(_rules(doc)))
        mutate(rule)
        with pytest.raises(check_lifecycle.MissingCheckIdError, match=match) as caught:
            check_lifecycle._parse_contract_quality_rule(rule, CONTRACTS[0], "here")
        assert _check_id(rule) in str(caught.value)

    def test_the_id_is_not_part_of_what_a_rule_does(self):
        """A copy of the check id, so - like the check id - outside the
        config hash: adding it changed no check's definition."""
        doc = config_yaml.parse((ROOT / CONTRACTS[0]).read_text())
        _, rule = next(iter(_rules(doc)))
        with_id = check_lifecycle._parse_contract_quality_rule(dict(rule), "x", "y")[0]
        assert with_id.config_hash == check_lifecycle._config_hash(
            {k: v for k, v in rule.items() if k not in ("customProperties", "description", "id")})


@pytest.fixture
def _quiet(monkeypatch, cp_duckdb_dir, bdm_duckdb_dir):
    import qa_tools.bdm.run_datacontract_bdm as bdm
    import qa_tools.cp.run_datacontract_cp as cp

    for mod in (cp, bdm):
        monkeypatch.setattr(mod, "write_qa_result", lambda *a, **k: None)
        monkeypatch.setattr(mod.asked_for, "record", lambda *a, **k: None)


def _clone(source: str, table: str, **withheld) -> str:
    from conftest import clone_run_views

    run_id = f"{table}__{random.randrange(10**17, 10**18)}"
    with supply_db.connect(label="test-dc-scoped") as conn:
        clone_run_views(conn, source, run_id, **withheld)
    return run_id


def _evaluate(evaluate, run_id, monkeypatch, *, scoped):
    monkeypatch.setattr(asked_for, "SCOPED",
                        frozenset({"datacontract"}) if scoped else frozenset())
    got = evaluate(run_id, "2026-04-01T09:00:00Z")
    left_out.take(run_id)
    return got


class TestTheSameVerdicts:
    """Criteria 3, 5, 6 and the bar."""

    @pytest.mark.parametrize("table", ["cp_notifications", "cp_placements", "cp_carers"])
    def test_child_protection(self, table, _quiet, monkeypatch):
        import qa_tools.cp.run_datacontract_cp as cp

        run_id = _clone(CP_DIRTY_RUN_ID, table)
        whole = _evaluate(cp.evaluate_datacontract_cp, run_id, monkeypatch, scoped=False)
        scoped = _evaluate(cp.evaluate_datacontract_cp, run_id, monkeypatch, scoped=True)
        in_scope = qa_results_writer.scope_of_run(run_id)
        want = {r["check_id"]: r for r in whole if in_scope(r["check_id"])}
        assert want
        assert {r["check_id"]: r for r in scoped} == want

    def test_birth_registrations(self, _quiet, monkeypatch):
        import qa_tools.bdm.run_datacontract_bdm as bdm

        run_id = _clone(BDM_DIRTY_RUN_ID, "birth_registrations")
        whole = _evaluate(bdm.evaluate_datacontract_bdm, run_id, monkeypatch, scoped=False)
        scoped = _evaluate(bdm.evaluate_datacontract_bdm, run_id, monkeypatch, scoped=True)
        assert whole and {r["check_id"]: r for r in scoped} == \
            {r["check_id"]: r for r in whole}


class TestWhatTheToolIsHanded:
    """Criteria 3, 5 and 6: its own options, the contract unchanged."""

    @pytest.fixture
    def handed(self, monkeypatch):
        import datacontract.data_contract as dc_module

        calls = []
        real = dc_module.DataContract

        def spy(*args, **kwargs):
            calls.append(kwargs)
            return real(*args, **kwargs)
        monkeypatch.setattr("datacontract.data_contract.DataContract", spy)
        return calls

    def test_a_run_naming_no_table_gets_neither_option(self, _quiet, monkeypatch, handed):
        import qa_tools.cp.run_datacontract_cp as cp

        run_id = _clone(CP_DIRTY_RUN_ID, "cp_whole_dc")
        monkeypatch.setattr(asked_for, "SCOPED", frozenset({"datacontract"}))
        cp.evaluate_datacontract_cp(run_id, "2026-04-01T09:00:00Z")
        (kwargs,) = handed
        assert "quality_ids" not in kwargs and "schema_name" not in kwargs

    def test_one_model_narrows_by_schema_name(self, _quiet, monkeypatch, handed):
        """A placements run has no datacontract readers, so every rule it
        asks for sits on cp_placements."""
        import qa_tools.cp.run_datacontract_cp as cp

        run_id = _clone(CP_DIRTY_RUN_ID, "cp_placements")
        monkeypatch.setattr(asked_for, "SCOPED", frozenset({"datacontract"}))
        cp.evaluate_datacontract_cp(run_id, "2026-04-01T09:00:00Z")
        (kwargs,) = handed
        assert kwargs["schema_name"] == "cp_placements"
        assert kwargs["quality_ids"] == {c.replace(".", ":") for c in asked_for.for_run(
            run_id, "child-protection", "datacontract")}

    def test_the_contract_text_is_the_committed_one_plus_the_server(self, _quiet, monkeypatch,
                                                                    handed):
        import yaml

        import qa_tools.cp.run_datacontract_cp as cp

        run_id = _clone(CP_DIRTY_RUN_ID, "cp_notifications")
        monkeypatch.setattr(asked_for, "SCOPED", frozenset({"datacontract"}))
        cp.evaluate_datacontract_cp(run_id, "2026-04-01T09:00:00Z")
        (kwargs,) = handed
        sent = yaml.safe_load(kwargs["data_contract_str"])
        committed = config_yaml.parse((ROOT / CONTRACTS[0]).read_text())
        sent["servers"] = [s for s in sent["servers"] if s["server"] != "warehouse"]
        assert sent == committed


class TestAnUnknownRuleRefuses:
    """Criterion 7: never a fallback to the whole contract."""

    def test_an_id_the_contract_does_not_hold_refuses_the_run(self, _quiet, monkeypatch):
        import qa_tools.cp.run_datacontract_cp as cp
        from qa_tools.common import datacontract_common

        run_id = _clone(CP_DIRTY_RUN_ID, "cp_clients")
        monkeypatch.setattr(asked_for, "SCOPED", frozenset({"datacontract"}))
        monkeypatch.setattr(asked_for, "for_run",
                            lambda *a, **k: [f"{P}.cp-clients.no_such_datacontract"])
        with pytest.raises(datacontract_common.SelectionRefused, match="no_such"):
            cp.evaluate_datacontract_cp(run_id, "2026-04-01T09:00:00Z")


class TestAnUnreadableTable:
    """Criterion 8, as today."""

    def test_a_scoped_rule_reading_it_is_left_out_and_reported(self, _quiet, monkeypatch):
        import qa_tools.cp.run_datacontract_cp as cp

        run_id = _clone(CP_DIRTY_RUN_ID, "cp_placements", absent={"cp_carers"})
        monkeypatch.setattr(asked_for, "SCOPED", frozenset({"datacontract"}))
        got = cp.evaluate_datacontract_cp(run_id, "2026-04-01T09:00:00Z")
        noted = left_out.take(run_id).get("datacontract", set())
        assert noted and noted.isdisjoint({r["check_id"] for r in got})
        assert got
        in_scope = qa_results_writer.scope_of_run(run_id)
        assert all(in_scope(c) for c in noted)


class TestNothingAsked:

    def test_an_empty_ask_invokes_nothing_and_says_so(self, cp_duckdb_dir, monkeypatch):
        import qa_tools.cp.run_datacontract_cp as cp

        run_id = _clone(CP_DIRTY_RUN_ID, "cp_case_workers")
        monkeypatch.setattr(cp.asked_for, "record", lambda *a, **k: None)
        monkeypatch.setattr(asked_for, "SCOPED", frozenset({"datacontract"}))
        monkeypatch.setattr(asked_for, "for_run", lambda *a, **k: [])
        monkeypatch.setattr(cp, "run_against_warehouse",
                            lambda *a, **k: pytest.fail("invoked with nothing asked"))
        written = []
        monkeypatch.setattr(cp, "write_qa_result", lambda *a, **k: written.append((a[4], a[5])))
        assert cp.evaluate_datacontract_cp(run_id, "2026-04-01T09:00:00Z") == []
        assert written == [("datacontract", {"asked": []})]
