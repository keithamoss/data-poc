"""Characterization pin for arrival/as-of semantics (REQ-PIPE-048).

WRITTEN BEFORE THE REFACTOR, DELIBERATELY. That requirement's own NFR
asks for exactly this and says why: the current behaviour is correct by
COINCIDENCE in at least one place - clipDatasetToAsOf() compares date
STRINGS, which gives end-of-day semantics by accident rather than by
design - so "did the refactor change anything" cannot be answered by
reading the new code. It has to be measured against what the old code
actually produced.

tests/fixtures/arrival_semantics_golden.json is that measurement: every
run in committed history, with its arrival instant and its
early/onTime/late verdict. Regenerate it ONLY when the committed
history is legitimately rebuilt, never to make a failing test pass - a
diff here after a timezone change is the finding, not the noise.

REGENERATED ONCE, 2026-09-23, for REQ-GEN-042's rebuild, which renamed
every run_id. Checked rather than assumed before accepting it: the
verdict distribution came back IDENTICAL across the rebuild - 131
onTime, 16 early, 3 late over the same 150 arrivals and 7 datasets - so
the regeneration changed identity and vocabulary and nothing else,
which is exactly what that requirement claims.

WHAT 048 DELIBERATELY DOES CHANGE, so it is not mistaken for a
regression: a timestamp with no offset currently gets silently treated
as UTC (pipeline/cadence.py's own `if ... tzinfo is None` branch, whose
docstring admits it). Criterion 4 makes that a loud failure. The
verdicts below must not move; the handling of a naked value must.
"""
from __future__ import annotations

import json
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

import pytest

from pipeline import cadence

def _instant_as_written_before_048(value) -> datetime | None:
    """One stored arrival as an instant, under the pre-048 reading.

    A value with no offset is taken as UTC - which is exactly what
    classify_arrival() used to do silently, and exactly what this
    requirement stops. It survives HERE, in one test, for the single
    purpose of proving that the values written the new way mean the same
    thing the old ones did.
    """
    if value in (None, "None"):
        return None
    parsed = datetime.fromisoformat(str(value).replace(" ", "T"))
    return parsed.replace(tzinfo=timezone.utc) if parsed.tzinfo is None else parsed


ROOT = Path(__file__).resolve().parent.parent
GOLDEN = Path(__file__).parent / "fixtures" / "arrival_semantics_golden.json"

_REPORTS = {
    "birth_registrations_dashboard.json": None,
    "child_protection_dashboard.json": None,
}


def _built_datasets():
    """Every real dataset from the built dashboard JSON, keyed by id.

    Skips rather than fails when the reports are absent - they are
    gitignored build output, and a fresh clone has not built them yet.
    """
    out = {}
    for name in _REPORTS:
        path = ROOT / "reports" / name
        if not path.exists():
            pytest.skip(f"{name} not built - run `mothman dashboard build-data`")
        doc = json.loads(path.read_text())
        for ds in (doc["datasets"] if "datasets" in doc else [doc]):
            out[ds["id"]] = ds
    return out


class TestEveryCommittedArrivalKeepsItsVerdict:
    """The pin proper. 150 real arrivals across 7 datasets."""

    def test_the_golden_covers_every_dataset_and_run_that_exists_now(self):
        """A pin that silently stops covering things is worse than none -
        it goes green by measuring less. Guards both directions."""
        golden = json.loads(GOLDEN.read_text())
        built = _built_datasets()
        assert set(golden) == set(built), "the golden and the built reports disagree about which datasets exist"
        for ds_id, runs in golden.items():
            on_page = {a["run_id"] for a in built[ds_id].get("arrivalHistory") or []}
            assert set(runs) == on_page, f"{ds_id}: the golden and the built history disagree about run ids"

    def test_no_arrival_changed_its_verdict(self):
        golden = json.loads(GOLDEN.read_text())
        built = _built_datasets()
        moved = []
        for ds_id, runs in golden.items():
            actual = {a["run_id"]: a for a in built[ds_id].get("arrivalHistory") or []}
            for run_id, expected in runs.items():
                got = actual[run_id]
                if got.get("arrivalStatus") != expected["arrivalStatus"]:
                    moved.append(f"{ds_id}/{run_id}: {expected['arrivalStatus']} -> {got.get('arrivalStatus')}")
        assert moved == [], "arrival verdicts moved:\n  " + "\n  ".join(moved)

    def test_no_arrival_instant_changed(self):
        """Separate from the verdict deliberately. A verdict can stay
        put while the instant behind it shifts by eight hours, and that
        is precisely the bug this requirement exists to prevent.

        Compared as INSTANTS rather than as strings, because REQ-PIPE-048
        deliberately changes the REPRESENTATION: the golden was captured
        when an arrival was stored as "2026-09-01 10:00:00" and read as
        UTC by whoever got to it, and it is now stored as
        "2026-09-01T10:00:00+00:00" and says so. Those are the same
        moment, and a string comparison would report the fix as the
        regression. The golden's own naked values are read here under
        the rule that was in force when they were written - which is the
        one place in this repo that rule still applies, and only because
        it is being used to prove it was preserved."""
        golden = json.loads(GOLDEN.read_text())
        built = _built_datasets()
        moved = []
        for ds_id, runs in golden.items():
            actual = {a["run_id"]: a for a in built[ds_id].get("arrivalHistory") or []}
            for run_id, expected in runs.items():
                was = _instant_as_written_before_048(expected["arrivedAt"])
                now_ = _instant_as_written_before_048(actual[run_id].get("arrivedAt"))
                if was != now_:
                    moved.append(f"{ds_id}/{run_id}: {expected['arrivedAt']} -> {actual[run_id].get('arrivedAt')}")
        assert moved == [], "arrival instants moved:\n  " + "\n  ".join(moved)

    def test_the_distribution_is_the_one_that_was_measured(self):
        """A blunt backstop for the two tests above, readable without a
        diff: 131 on time, 16 early, 3 late, measured 2026-09-23."""
        golden = json.loads(GOLDEN.read_text())
        counts: dict[str, int] = {}
        for runs in golden.values():
            for a in runs.values():
                counts[a["arrivalStatus"]] = counts.get(a["arrivalStatus"], 0) + 1
        assert counts == {"onTime": 131, "early": 16, "late": 3}


class TestTheClassificationBoundaries:
    """The RULE, stated as boundary cases rather than inferred from the
    150 real arrivals above - those happen to cluster, and none of them
    sits on a boundary. Written against aware instants only, since that
    is the half 048 must not move."""

    CADENCE = {"type": "daily", "weekday": None, "anchor_months": None,
               "day_of_month": None, "expected_time": "14:00", "latency_minutes": 60}

    def _expected(self, run_date):
        return cadence.expected_moment(self.CADENCE, cadence.cycle_start(self.CADENCE, run_date))

    @pytest.mark.parametrize("delta,verdict", [
        (timedelta(seconds=-1), "early"),
        (timedelta(0), "onTime"),
        (timedelta(minutes=60), "onTime"),
        (timedelta(minutes=60, seconds=1), "late"),
    ])
    def test_the_grace_window_is_closed_at_both_ends(self, delta, verdict):
        run_date = date(2026, 9, 1)
        arrived = self._expected(run_date) + delta
        assert cadence.classify_arrival(self.CADENCE, run_date, arrived) == verdict

    def test_the_expected_moment_is_the_wall_clock_time_in_the_assets_own_zone(self):
        """14:00 in Perth is 06:00 UTC the same day. Pinned as a real
        instant rather than as an offset arithmetic step, so the
        refactor from a hardcoded UTC+8 to a named zone has something
        to be judged against."""
        assert self._expected(date(2026, 9, 1)) == datetime(2026, 9, 1, 6, 0, tzinfo=timezone.utc)

    def test_an_arrival_the_day_before_is_early_not_late(self):
        """The wrap case the generator's own comment calls out: an AWST
        expected_time before 08:00 lands on the PREVIOUS UTC day, which
        made "on time" structurally unreachable once before."""
        run_date = date(2026, 9, 1)
        arrived = self._expected(run_date) - timedelta(hours=12)
        assert cadence.classify_arrival(self.CADENCE, run_date, arrived) == "early"
