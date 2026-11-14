"""REQ-GEN-298 criteria 3 and 4 against what the replay RECORDED: each named
geocoding scenario is the only fault in its supply.

The plan-side tests in test_geocoding_faults.py prove each scenario's quarter
carries one planted fault. They cannot see the other way a second fault
appears: a supply whose drift reference is a QUARTER BACK because the quarter
before it has no accepted supply (REQ-QAC-108's reference gap, flagged red by
Keith's 2026-10-04 rule). That red is the rule working; a scenario placed
straight after such a gap simply shows it beside its own fault. Found by the
2026-11-14 evidence walk-through ([14]): TS-107 after 2013-Q4's ED geocodes,
held for want of ED, and TS-111 after TS-110's refused empty file.

Reads the deployment's recorded history, never writes it."""
from __future__ import annotations

import json

import pytest

pytestmark = pytest.mark.asset("quarterly")


def _named_geocoding_supplies():
    """Every supply a geocoding injection (REQ-GEN-298) names, from the
    asset's recorded placements - so a scenario that moves is followed."""
    from generator import scenario_injection
    from qa_tools.common import scenario_map

    planted = {i.scenario_id for i in scenario_injection.INJECTIONS
               if i.dataset_id.startswith("geo-")}
    raw = json.loads(scenario_map.placements_path().read_text())
    records = raw.get("placements") if isinstance(raw, dict) else raw
    return {(r["scenario_id"], s) for r in records if r["scenario_id"] in planted
            for s in r["supplies"]}


def test_no_named_geocoding_scenario_is_judged_across_a_reference_gap(deployment_history):
    from qa_tools.common import supply_db

    named = _named_geocoding_supplies()
    assert len(named) >= 10, "the ten REQ-GEN-298 scenarios are placed"
    with supply_db.connect() as conn:
        # A placement names the ARRIVAL RUN (its run key); the run's own
        # supply_id is '<dataset>@<receipt>'.
        rows = conn.execute(
            """SELECT r.run_key, cr.check_id, cr.status, cr.extra->>'reference_gap'
                 FROM qa.check_result cr JOIN qa.run r USING (run_key)
                WHERE r.scope = 'arrival' AND NOT r.trial
                  AND r.run_key = ANY(?)""",
            ([s for _sid, s in named],)).fetchall()
    assert {r[0] for r in rows} == {s for _sid, s in named}, \
        "every named supply has recorded results"
    by_supply = dict((s, sid) for sid, s in named)
    gapped = sorted({f"{by_supply[s]} ({s}): {check} {status} across {gap}"
                     for s, check, status, gap in rows
                     if gap and status in ("fail", "warn")})
    assert not gapped, "a scenario sits straight after a quarter with no accepted supply:\n" + \
        "\n".join(gapped)
