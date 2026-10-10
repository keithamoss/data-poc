"""The delivery agreement as the system computes it, captured to a file -
REQ-PIPE-110's behaviour-preserving pin (NFR 3 and 4).

The move of the agreement into contract/calendar.yaml is the one commit the
freeze gate cannot see, so this pin is its only guard: every dataset's
periods (owed or not, and why), and every slot's due, late-after,
claim-opening and closing instants, as the configuration in force on the
day of the move produced them. Captured BEFORE the move and committed;
tests/test_calendar_move_pin.py compares the system's answer with it.

Run directly to re-capture - which is only ever right before the move,
never to make a failing comparison pass.
"""
from __future__ import annotations

import json
import sys
from datetime import date
from pathlib import Path

PIN = Path(__file__).parent / "fixtures" / "calendar_move_pin.json"
#: Far enough ahead to cover every authored date, and two years of the daily rule.
UNTIL = date(2028, 12, 31)


def capture() -> dict:
    from qa_tools.common import hierarchy, schedule, slots

    out: dict[str, dict] = {}
    for entry in hierarchy.all_datasets():
        ds = entry.dataset_id
        record: dict = {"no_calendar": schedule.no_calendar(ds)}
        if record["no_calendar"]:
            out[ds] = record
            continue
        record["periods"] = [
            [p.name, p.date.isoformat(), p.expected, p.not_expected_reason]
            for p in schedule.periods_for_dataset(ds, until=UNTIL)]
        record["slots"] = [
            [s.name, s.due_at.isoformat(), s.late_after.isoformat(),
             s.claim_opens_at.isoformat(), s.closes_at.isoformat() if s.closes_at else None]
            for s in slots.slots_for_dataset(ds, until=UNTIL)]
        out[ds] = record
    return out


if __name__ == "__main__":
    sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
    PIN.write_text(json.dumps(capture(), indent=1) + "\n")
    print(f"captured {PIN}")
