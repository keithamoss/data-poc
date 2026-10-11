"""Child Protection client postcodes tolerate a few unrecognised values
(REQ-QAC-187; Keith, 2026-10-11): the contract's rule fails at 3% or more,
matching Soda's fail bound, so a supply with a few bad postcodes reads amber -
datacontract-cli passes while Soda warns - and one past every bound reads red.

Against the real tools and this worker's own staged fixture delivery. Its own
module because it rewrites the fixture's staged client postcodes.
"""
from __future__ import annotations

import pytest

import qa_tools.cp.run_datacontract_cp as run_datacontract_cp
import qa_tools.cp.run_soda_cp as run_soda_cp
from fixture_ids import CP_REF_RUN_ID
from qa_tools.common import supply_db

CHECK = ("data-asset-1.child-protection-family-support.child-protection.cp-clients."
         "postcode.invalidValues_datacontract")
SODA = ("data-asset-1.child-protection-family-support.child-protection.cp-clients."
        "postcode.invalid_percent_soda")


@pytest.fixture
def clients(cp_duckdb_dir, monkeypatch):
    """(connection, schema-qualified staged clients table, its row count)."""
    monkeypatch.setattr(run_datacontract_cp, "write_qa_result", lambda *a, **k: None)
    monkeypatch.setattr(run_soda_cp, "write_qa_result", lambda *a, **k: None, raising=False)
    with supply_db.connect(label="test-postcode-tolerance") as conn:
        # THROUGH THE RUN'S OWN VIEW of the clients table, wherever it was
        # staged or promoted - the run reads exactly this.
        table = f'"qa_{CP_REF_RUN_ID}"."cp_clients"'
        conn.execute(f"CREATE TEMP TABLE kept AS SELECT * FROM {table}")
        n = conn.execute(f"SELECT count(*) FROM {table}").fetchall()[0][0]
        yield conn, table, n
        conn.execute(f"DELETE FROM {table}")
        conn.execute(f"INSERT INTO {table} SELECT * FROM kept")


def _spoil(conn, table, rows: int) -> None:
    conn.execute(f"UPDATE {table} SET postcode = 9999 WHERE cp_client_id IN "
                 f"(SELECT cp_client_id FROM {table} ORDER BY cp_client_id LIMIT {rows})")


def _datacontract():
    results = run_datacontract_cp.evaluate_datacontract_cp(CP_REF_RUN_ID,
                                                           "2026-01-01T09:00:00Z")
    [found] = [r for r in results if r["check_id"] == CHECK]
    return found


def test_a_few_unrecognised_postcodes_pass_the_contract_and_warn_in_soda(clients):
    """Criterion 6: amber - the contract passes, Soda warns."""
    conn, table, n = clients
    _spoil(conn, table, max(1, n // 100))
    assert _datacontract()["status"] == "pass"
    soda = [r for r in run_soda_cp.evaluate_soda_cp(CP_REF_RUN_ID, "2026-01-01T09:00:00Z")
            if r["check_id"] == SODA]
    assert [r["status"] for r in soda] == ["warn"]


def test_past_the_bound_the_contract_fails(clients):
    """Criterion 7."""
    conn, table, n = clients
    _spoil(conn, table, n * 5 // 100)
    assert _datacontract()["status"] == "fail"


def test_the_tolerance_is_recorded_rather_than_zero(clients):
    """Criterion 8: the dashboard shows the rule's own bound."""
    assert _datacontract()["fail_threshold"] == 3


def test_an_ordinary_child_protection_amber_reads_amber(clients):
    """REQ-GEN-184 criterion 15: the generator's own Child Protection amber,
    applied to this fixture delivery's clients, passes the contract and
    warns in Soda - amber, by construction."""
    import pandas as pd

    from generator import targeting

    conn, table, _n = clients
    rows = conn.execute(f"SELECT cp_client_id, postcode FROM {table}").fetchall()
    frame = pd.DataFrame(rows, columns=["cp_client_id", "postcode"]).astype({"postcode": str})
    out = targeting.cp_amber({"cp_clients": frame}, seed=5)["cp_clients"]
    changed = out[out["postcode"].isin(targeting.UNRECOGNISED_POSTCODES)]
    assert len(changed)
    for client_id, postcode in zip(changed["cp_client_id"], changed["postcode"]):
        conn.execute(f"UPDATE {table} SET postcode = ? WHERE cp_client_id = ?",
                     [int(postcode), client_id])
    assert _datacontract()["status"] == "pass"
    soda = [r for r in run_soda_cp.evaluate_soda_cp(CP_REF_RUN_ID, "2026-01-01T09:00:00Z")
            if r["check_id"] == SODA]
    assert [r["status"] for r in soda] == ["warn"]
